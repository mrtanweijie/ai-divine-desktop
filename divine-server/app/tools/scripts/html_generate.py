"""通用 HTML 页面保存工具。

与 ux_html.py 的分工：
- ``ux_html``   —— UX 交互原型 / 产品界面设计稿，绑定 ux 意图，视觉规范更严（组件级指标）。
- ``html_generate`` —— 其余一切"要产出一个 HTML 文件"的场景：分析报告、数据看板、
  仪表盘、落地页、简历、文档网页版、活动页等。工具常驻注入，不按意图裁剪。

两者共用同一套 token 基座与静态校验（见 ux_html 模块），区别只在：
1. style **可选**，用户没指定风格时由模型按内容性质自选，不再强制用户明确选择；
2. 保存目录默认 ``html``，文件名回退用"页面"而非"UX交互原型"；
3. 校验回传文案指向 html_generate 自身。
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

# 复用 ux_html 的基座与校验：同一套视觉基线，避免两套规范漂移。
# 脚本以 `python <script_path>` 由子进程执行，脚本所在目录在同目录 import 可达；
# PyInstaller frozen 下走包路径，故两种都试。
try:  # pragma: no cover - 取决于执行方式
    from app.tools.scripts.ux_html import (  # type: ignore
        ALLOWED_STYLES,
        derive_title,
        inject_scaffold,
        lint_html,
    )
except ImportError:  # pragma: no cover
    from ux_html import (  # type: ignore  # noqa: E402
        ALLOWED_STYLES,
        derive_title,
        inject_scaffold,
        lint_html,
    )

from app.tools.scripts.file_utils import unique_output_path  # noqa: E402

# style 是"建议"而非"约束"：用户没指定时模型自选型，落到这里若不在白名单
# 则回落默认风格，不再报错中断任务（ux_html 才强制要求用户明确选择）。
DEFAULT_STYLE = "Notion"


def resolve_style(style: str) -> str:
    return style if style in ALLOWED_STYLES else DEFAULT_STYLE


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    output_root = Path(data.get("output_dir") or workspace).resolve()
    params = data.get("params") or {}
    requested_style = str(params.get("style") or "").strip()
    style = resolve_style(requested_style)
    content = str(params.get("content") or "").strip()

    if not content:
        print(
            json.dumps(
                {"success": False, "message": "content 不能为空，请传入完整 HTML 页面源码"},
                ensure_ascii=False,
            )
        )
        return
    lowered = content.lower()
    if "<html" not in lowered and "<!doctype html" not in lowered:
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

    # lint 跑在**原始** content 上：注入基座的色值会污染 hex 计数。
    final_content, scaffolded = inject_scaffold(content, style)
    warnings = lint_html(content, scaffolded=scaffolded)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = unique_output_path(output_dir, title, "页面", ".html")
    output_path.write_text(final_content, encoding="utf-8")

    message = "HTML 页面已生成"
    if requested_style and requested_style not in ALLOWED_STYLES:
        message += f"（style 取值 {requested_style} 无效，已回落 {DEFAULT_STYLE}）"
    elif scaffolded:
        message += f"（已注入 {style} 风格 token 基座，你自定义的 :root 与样式会覆盖基座）"
    if warnings:
        # 文件已落盘（不阻断流程），把问题回传给模型，促其自纠后重新生成。
        message += "；静态校验发现以下问题，请修正后重新调用 html_generate 覆盖保存：\n- " + "\n- ".join(
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
                    "style_fallback": bool(
                        requested_style and requested_style not in ALLOWED_STYLES
                    ),
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
