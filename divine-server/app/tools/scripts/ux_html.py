from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.tools.scripts.file_utils import unique_output_path  # noqa: E402


def safe_name(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "_", name).strip("._")
    if not cleaned:
        cleaned = fallback
    if not cleaned.endswith(".html"):
        cleaned += ".html"
    return cleaned


def derive_title(title: str, content: str) -> str:
    candidate = (title or "").strip()
    if candidate:
        return candidate
    match = re.search(r"<title[^>]*>(.*?)</title>", content, re.IGNORECASE | re.DOTALL)
    if match:
        value = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        if value:
            return value[:80]
    match = re.search(r"<h1[^>]*>(.*?)</h1>", content, re.IGNORECASE | re.DOTALL)
    if match:
        value = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        if value:
            return value[:80]
    return "UX交互原型"


ALLOWED_STYLES = {"Notion", "Linear", "Apple", "PlainText", "Obsidian", "Custom"}

# ---------------------------------------------------------------------------
# 设计 token 基座
#
# 模型偶尔会漏写 :root 或把色值散落在组件里，光靠 prompt 约束只能降低概率。
# 这里在保存前把所选风格的变量层 + 极简 reset **前置**注入到 <head> 最前面：
# CSS 层叠中后定义的同名规则胜出，所以模型自己写的 :root 或组件样式天然覆盖
# 基座，定制自由不受影响；模型漏写时基座兜底，页面不会崩成裸 HTML。
#
# 用 Python 常量而非外部 .css 文件：本脚本在 PyInstaller frozen 环境下经
# --run-script 由子进程执行，读外部资源路径不可靠。
# ---------------------------------------------------------------------------
_RESET = """*,*::before,*::after{box-sizing:border-box}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
font-size:14px;line-height:1.7;background:var(--bg);color:var(--text)}
h1,h2,h3,h4,p{margin:0}
button{font:inherit;color:inherit;cursor:pointer}
input,select,textarea{font:inherit;color:inherit}
a{color:var(--primary);text-decoration:none}
table{border-collapse:collapse}"""

_TOKENS: dict[str, str] = {
    "Notion": """--bg:#FFFFFF;--surface:#FFFFFF;--surface-2:#F7F7F5;--border:#E9E9E7;--border-strong:#DFDFDC;
--text:#37352F;--text-2:#787774;--text-3:#9B9A97;
--primary:#2383E2;--primary-weak:#E7F3F8;--primary-ink:#FFFFFF;
--ok:#0F7B6C;--ok-weak:#DDF2ED;--warn:#CB912F;--warn-weak:#FBF3DB;--danger:#D64545;--danger-weak:#FBE9E9;
--radius-sm:6px;--radius-md:12px;--radius-lg:16px""",
    "Linear": """--bg:#F9F9FB;--surface:#FFFFFF;--surface-2:#F4F4F6;--border:#E6E6EB;--border-strong:#D4D4DA;
--text:#08090A;--text-2:#6E6D77;--text-3:#8A8F98;
--primary:#5E6AD2;--primary-weak:#EEF0FD;--primary-ink:#FFFFFF;
--ok:#0F7B6C;--ok-weak:#DDF2ED;--warn:#CB912F;--warn-weak:#FBF3DB;--danger:#D64545;--danger-weak:#FBE9E9;
--radius-sm:6px;--radius-md:12px;--radius-lg:16px""",
    "Apple": """--bg:#F5F5F7;--surface:#FFFFFF;--surface-2:#F5F5F7;--border:#D2D2D7;--border-strong:#B9B9BF;
--text:#1D1D1F;--text-2:#6E6E73;--text-3:#86868B;
--primary:#0071E3;--primary-weak:#E8F2FD;--primary-ink:#FFFFFF;
--ok:#0F7B6C;--ok-weak:#DDF2ED;--warn:#CB912F;--warn-weak:#FBF3DB;--danger:#D64545;--danger-weak:#FBE9E9;
--radius-sm:8px;--radius-md:16px;--radius-lg:20px""",
    "PlainText": """--bg:#FFFFFF;--surface:#FFFFFF;--surface-2:#FAFAFA;--border:#DDDDDD;--border-strong:#C4C4C4;
--text:#111111;--text-2:#555555;--text-3:#888888;
--primary:#111111;--primary-weak:#F0F0F0;--primary-ink:#FFFFFF;
--ok:#0F7B6C;--ok-weak:#DDF2ED;--warn:#CB912F;--warn-weak:#FBF3DB;--danger:#D64545;--danger-weak:#FBE9E9;
--radius-sm:4px;--radius-md:8px;--radius-lg:12px""",
    # 暖白纸张（浅色默认层）。深色层见 _DARK_TOKENS——深浅同源，换光线不换皮肤。
    "Obsidian": """--bg:#FAF7F1;--surface:#FFFDF8;--surface-2:#F0EBE0;--border:#E5DECE;--border-strong:#D2C8B4;
--text:#3D3730;--text-2:#756D5F;--text-3:#A89F8F;
--primary:#0E6E63;--primary-weak:#E1EFEB;--primary-ink:#FFFFFF;
--ok:#4A704F;--ok-weak:#E6EFE5;--warn:#8A5E17;--warn-weak:#F5EBD6;--danger:#B8445A;--danger-weak:#F9E6E9;
--radius-sm:6px;--radius-md:12px;--radius-lg:16px""",
}
# Custom 没有固定色值：用中性兜底 token，模型按 style_note 自己覆盖即可
_TOKENS["Custom"] = _TOKENS["Notion"]

# ---------------------------------------------------------------------------
# 深浅同源风格的深色层（暖棕·冷锚）
#
# 浅色层为默认；深色层经 @media(prefers-color-scheme:dark) 注入，跟随系统
# 深色模式自动切换。media query 不影响 specificity，模型在后写的普通 :root
# 仍可整体覆盖基座（想强制浅色/深色时写自己的 :root 即可），兜底与自由兼得。
# 只覆盖颜色变量——圆角不随深浅变，从浅色层继承。
# ---------------------------------------------------------------------------
_DARK_TOKENS: dict[str, str] = {
    "Obsidian": """--bg:#262322;--surface:#2E2A28;--surface-2:#38332F;--border:#3E3833;--border-strong:#544B43;
--text:#CFC7BD;--text-2:#948D83;--text-3:#7E7669;
--primary:#6DB3A3;--primary-weak:#28423C;--primary-ink:#10312B;
--ok:#8FBF94;--ok-weak:#2C3B2C;--warn:#C99B5E;--warn-weak:#3B3222;--danger:#D97F8D;--danger-weak:#432B30""",
    # Apple 官方深色语言：纯黑底/灰卡分层、#F5F5F7 正文、#2997FF 亮蓝链接、iOS 系统语义色。
    # 注意 --primary-ink 用深墨而非白字：#2997FF 上白字仅 3.02:1，深墨 6.27:1。
    "Apple": """--bg:#000000;--surface:#1D1D1F;--surface-2:#2C2C2E;--border:#38383A;--border-strong:#48484A;
--text:#F5F5F7;--text-2:#86868B;--text-3:#6E6E73;
--primary:#2997FF;--primary-weak:#0E2A44;--primary-ink:#04121F;
--ok:#30D158;--ok-weak:#0B2A16;--warn:#FF9F0A;--warn-weak:#2E2306;--danger:#FF453A;--danger-weak:#33110E""",
}

_HEAD_RE = re.compile(r"<head[^>]*>", re.IGNORECASE)
_HTML_RE = re.compile(r"<html[^>]*>", re.IGNORECASE)
_BODY_RE = re.compile(r"<body[^>]*>", re.IGNORECASE)


def inject_scaffold(content: str, style: str) -> tuple[str, bool]:
    """把风格的 token 层 + reset 前置注入到 <head> 最前面。

    返回 (新内容, 是否注入)。注入点在模型自身 <style> 之前，因此模型的任何
    同名声明都会覆盖基座；模型漏写 :root 时基座兜底。
    找不到 head/html/body 时返回原内容（不注入），避免破坏畸形文档。
    """
    tokens = _TOKENS.get(style)
    if not tokens:
        return content, False
    block = f'<style id="divine-scaffold">:root{{{tokens}}}\n'
    dark = _DARK_TOKENS.get(style)
    if dark:
        block += f"@media(prefers-color-scheme:dark){{:root{{{dark}}}}}\n"
    block += f"{_RESET}\n</style>\n"
    for pattern in (_HEAD_RE, _HTML_RE):
        match = pattern.search(content)
        if match:
            return content[: match.end()] + "\n" + block + content[match.end() :], True
    body = _BODY_RE.search(content)
    if body:
        return content[: body.start()] + block + content[body.start() :], True
    return content, False

# 间距/尺寸白名单：边框、细线、微调偏移允许不是 4 的倍数
_SPACING_ALLOWLIST = {0, 1, 2, 3}
_HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")
_FONT_SIZE_RE = re.compile(r"font-size\s*:\s*(\d+(?:\.\d+)?)px")
_SPACING_RE = re.compile(
    r"\b(?:padding|margin|gap|padding-top|padding-bottom|padding-left|padding-right"
    r"|margin-top|margin-bottom|margin-left|margin-right|row-gap|column-gap)"
    r"\s*:\s*([^;}]+)"
)
_HARD_FAILS = (
    # (正则, 提示) — 命中会导致预览脚本崩溃或成品明显不合格，必须修。
    # CDN/外部字体/图片已放宽（允许国内可访问源），不再列为硬伤，只保留真硬伤。
    (re.compile(r"\b(?:localStorage|sessionStorage|document\.cookie)\b"), "使用了 localStorage/sessionStorage/cookie，预览 iframe 无 same-origin，脚本会抛异常崩溃，请改用 JS 变量"),
    (re.compile(r"\{\{|\blorem ipsum\b|示例文本|待补充", re.I), "存在未替换的占位内容（{{}} / lorem ipsum / 示例文本 / 待补充），请换成真实中文内容"),
)

# 外部资源国内可访问性：CDN 已放宽，但 Google Fonts 被墙、常见国外 CDN 不稳定。
_GOOGLE_FONTS_RE = re.compile(r"fonts\.googleapis\.com|fonts\.gstatic\.com", re.I)
_UNSTABLE_CDN_RE = re.compile(r"jsdelivr\.net|unpkg\.com|cdnjs\.cloudflare\.com", re.I)
_MAX_WARNINGS = 6


def lint_html(content: str, scaffolded: bool = False, mobile: bool = False) -> list[str]:
    """静态校验生成的 HTML，返回可读的问题列表（按严重度排序，最多 6 条）。

    content 应传**模型原始输出**（注入基座前），否则基座的色值会污染 hex 计数。
    scaffolded 表示本次是否会注入 token 基座：已注入时不再提示"未定义 :root"，
    因为基座已经兜住，提示模型重写属于噪音。
    mobile=True 时切换移动端 App 原型规则：字号档数放宽到 10（iOS type scale 层级多）、
    间距只禁奇数（6/10/14 是移动端合理紧凑档）、色值上限放宽到 30（瀑布流封面色块多）。

    只做高信噪比检查：硬伤（localStorage 崩溃 / 占位残留）必须修，其余是美观度与
    可访问性信号（token 缺失、字号失控、间距破档、Google Fonts 被墙、国外 CDN 不稳定）。
    不做 AST 解析，纯正则，宁可漏报不可误报——误报会让模型反复重写浪费轮次。
    """
    issues: list[str] = []
    for pattern, message in _HARD_FAILS:
        if pattern.search(content):
            issues.append(message)

    soft: list[str] = []
    has_root = ":root" in content
    if not has_root:
        # 基座已兜底时不再提示，否则模型会被迫重复生成一遍 :root
        if not scaffolded:
            soft.append("未定义 :root 设计 token，色值会散落在组件里，请补齐变量层")
    else:
        hex_count = len(set(_HEX_RE.findall(content)))
        hex_limit = 30 if mobile else 20
        if hex_count > hex_limit:
            soft.append(
                f"检测到 {hex_count} 种硬编码色值，超过 token 合理数量，请把色值收敛到 :root 变量"
            )
    if _GOOGLE_FONTS_RE.search(content):
        soft.append("引用了 Google Fonts（fonts.googleapis/gstatic），国内无法访问会导致字体异常，请改用系统字体或国内可访问的字体源")
    if _UNSTABLE_CDN_RE.search(content):
        soft.append("引用了国外 CDN（jsdelivr/unpkg/cdnjs），国内访问不稳定，建议换 BootCDN(cdn.bootcdn.net) 或 staticfile(cdn.staticfile.org) 等国内源")

    size_limit = 10 if mobile else 6
    sizes = sorted({float(v) for v in _FONT_SIZE_RE.findall(content)})
    if len(sizes) > size_limit:
        preview = "/".join(f"{int(s)}" if s.is_integer() else f"{s:g}" for s in sizes[:12])
        hint = (
            f"移动端核心阶梯 28/20/17/15/13/11 + 组件变体，全页 ≤{size_limit} 档，禁止 0.5px 值"
            if mobile
            else f"排版阶梯只允许 {size_limit} 档，请收敛"
        )
        soft.append(f"字号出现 {len(sizes)} 种（{preview}），{hint}")
    offenders: set[int] = set()
    for declaration in _SPACING_RE.findall(content):
        for token in re.split(r"[\s]+", declaration.strip()):
            match = re.fullmatch(r"(\d+)px", token)
            if not match:
                continue
            value = int(match.group(1))
            if mobile:
                # 移动端取偶数档（6/10/14 是合理紧凑间距），只抓奇数手调值
                if value % 2 == 1 and value not in _SPACING_ALLOWLIST:
                    offenders.add(value)
            elif value % 4 and value not in _SPACING_ALLOWLIST:
                offenders.add(value)
    if len(offenders) >= 3:
        shown = sorted(offenders)[:6]
        hint = (
            "移动端间距取偶数档：4/6/8/10/12/16/20/24，禁止奇数手调值"
            if mobile
            else "请对齐 4/8/12/16/24/32/48/64 档位"
        )
        soft.append(
            "间距出现手调数值（" + "/".join(f"{v}px" for v in shown) + f"），{hint}"
        )
    issues.extend(soft)
    return issues[:_MAX_WARNINGS]


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    output_root = Path(data.get("output_dir") or workspace).resolve()
    params = data.get("params") or {}
    style = str(params.get("style") or "").strip()
    style_note = str(params.get("style_note") or "").strip()
    canvas = str(params.get("canvas") or "desktop").strip().lower()
    mobile = canvas == "mobile"
    content = str(params.get("content") or "").strip()
    if style not in ALLOWED_STYLES:
        print(
            json.dumps(
                {
                    "success": False,
                    "message": "style 必须由用户明确选择：Notion/Linear/Apple/PlainText/Obsidian/Custom",
                },
                ensure_ascii=False,
            )
        )
        return
    if style == "Custom" and not style_note:
        print(
            json.dumps(
                {"success": False, "message": "选择 Custom 时必须提供 style_note 描述用户偏好"},
                ensure_ascii=False,
            )
        )
        return
    if not content:
        print(
            json.dumps(
                {"success": False, "message": "content 不能为空，请传入完整 HTML 页面源码"},
                ensure_ascii=False,
            )
        )
        return
    if "<html" not in content.lower() and "<!doctype html" not in content.lower():
        print(
            json.dumps(
                {
                    "success": False,
                    "message": "content 必须是完整 HTML 页面源码，应包含 DOCTYPE 或 <html>；不要传入需求文档正文",
                },
                ensure_ascii=False,
            )
        )
        return

    title = derive_title(str(params.get("title") or ""), content)
    output_dir = output_root / "html"
    raw_path = str(params.get("path") or "").strip()
    if raw_path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = workspace / candidate
        output_dir = candidate.resolve()
        try:
            output_dir.relative_to(workspace)
        except ValueError:
            print(
                json.dumps(
                    {"success": False, "message": f"保存路径越界: {output_dir}"},
                    ensure_ascii=False,
                )
            )
            return
    if output_dir.exists() and not output_dir.is_dir():
        print(
            json.dumps(
                {"success": False, "message": f"保存路径不是目录: {output_dir}"},
                ensure_ascii=False,
            )
        )
        return
    # lint 在**原始** content 上跑：注入基座的色值会污染 hex 计数。
    # 基座先注入，落盘的是注入后的内容；模型漏写 :root 时由基座兜底。
    final_content, scaffolded = inject_scaffold(content, style)
    warnings = lint_html(content, scaffolded=scaffolded, mobile=mobile)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = unique_output_path(output_dir, title, "UX交互原型", ".html")
    output_path.write_text(final_content, encoding="utf-8")

    message = "UX 交互 HTML 页面已生成"
    if scaffolded:
        message += f"（已注入 {style} 风格 token 基座，你自定义的 :root 与样式会覆盖基座）"
    if warnings:
        # 文件已落盘（不阻断流程），但把问题回传给模型，促其自纠后重新生成。
        message += "；静态校验发现以下问题，请修正后重新调用 ux_html 覆盖保存：\n- " + "\n- ".join(
            warnings
        )

    print(
        json.dumps(
            {
                "success": True,
                "message": message,
                "file_name": output_path.name,
                "filepath": str(output_path),
                "warnings": warnings,
                "data": {
                    "title": title,
                    "style": style,
                    "canvas": canvas,
                    "scaffold_injected": scaffolded,
                    "size": output_path.stat().st_size,
                    "generated_at": time.strftime("%Y-%m-%d %H:%M"),
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
