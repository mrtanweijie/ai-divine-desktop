"""测试 ux_html 的视觉质量防线：token 基座注入、静态校验、prompt 一致性。

被测的 inject_scaffold() 与 lint_html() 都是纯字符串函数，不触碰文件系统，
因此整套测试不需要 tmp_path（当前沙箱下 tmp_path fixture 有权限问题，能避开就避开）。

最后一组是防漂移测试：prompt 里的风格速查表与工具实际注入的 _TOKENS 必须一致，
否则模型"看到的色值"和"拿到的色值"会对不上。
"""

import re

from app.agent.core.prompt_sections import _UX_HTML_RULES
from app.tools.scripts.ux_html import (
    ALLOWED_STYLES,
    _DARK_TOKENS,
    _TOKENS,
    inject_scaffold,
    lint_html,
)

_HEAD_DOC = (
    "<!DOCTYPE html><html><head><title>t</title>"
    "<style>.a{color:var(--text);padding:16px}</style>"
    '</head><body><div class="a">x</div></body></html>'
)


# ---------------------------------------------------------------------------
# inject_scaffold：注入位置与覆盖语义
# ---------------------------------------------------------------------------


def test_scaffold_injected_before_model_style():
    """基座必须排在模型 <style> 之前，否则模型无法靠层叠顺序覆盖。"""
    out, ok = inject_scaffold(_HEAD_DOC, "Linear")
    assert ok
    assert out.index('id="divine-scaffold"') < out.index("<style>.a{")


def test_scaffold_keeps_model_root_override():
    """模型自定义的 :root 排在基座之后，同名变量由模型胜出。"""
    doc = (
        "<html><head><style>:root{--primary:#FF0000}"
        ".a{color:var(--primary)}</style></head><body>x</body></html>"
    )
    out, ok = inject_scaffold(doc, "Linear")
    assert ok
    assert out.index("--primary:#FF0000") > out.index("--primary:#5E6AD2")


def test_scaffold_falls_back_to_html_when_no_head():
    """没有 <head> 时退化到 <html> 之后注入，且仍早于 body。"""
    doc = "<html><body><style>.a{padding:8px}</style></body></html>"
    out, ok = inject_scaffold(doc, "Notion")
    assert ok
    assert 'id="divine-scaffold"' in out
    assert out.index('id="divine-scaffold"') < out.index("<body>")


def test_scaffold_skips_malformed_document():
    """找不到 head/html/body 时不注入，避免破坏畸形文档。"""
    doc = '<div class="a">x</div>'
    out, ok = inject_scaffold(doc, "Linear")
    assert not ok
    assert out == doc


def test_scaffold_unknown_style_is_noop():
    out, ok = inject_scaffold(_HEAD_DOC, "NoSuchStyle")
    assert not ok
    assert out == _HEAD_DOC


def test_scaffold_injects_style_specific_token():
    for style, token in (
        ("Linear", "--primary:#5E6AD2"),
        ("Notion", "--primary:#2383E2"),
        ("Apple", "--primary:#0071E3"),
        ("PlainText", "--primary:#111111"),
        ("Obsidian", "--primary:#0E6E63"),
    ):
        out, ok = inject_scaffold(_HEAD_DOC, style)
        assert ok
        assert token in out, f"{style} 未注入 {token}"


def test_dark_light_style_injects_prefers_color_scheme():
    """深浅同源风格（Obsidian、Apple）：浅色默认层 + 深色 media query 层，其他风格不受影响。"""
    out, ok = inject_scaffold(_HEAD_DOC, "Obsidian")
    assert ok
    assert "--bg:#FAF7F1" in out  # 浅色默认层（暖白纸张）
    assert "@media(prefers-color-scheme:dark)" in out
    assert "--bg:#262322" in out  # 深色层（暖棕·冷锚）
    assert "--primary:#6DB3A3" in out

    # Apple 深色层：官方深色语言（纯黑底/亮蓝链接）
    apple_out, apple_ok = inject_scaffold(_HEAD_DOC, "Apple")
    assert apple_ok
    assert "--bg:#F5F5F7" in apple_out and "--bg:#0071E3" not in apple_out  # 浅色默认层
    assert "--bg:#000000" in apple_out and "--primary:#2997FF" in apple_out
    assert "@media(prefers-color-scheme:dark)" in apple_out

    # 其他风格不注入深色层
    notion_out, _ = inject_scaffold(_HEAD_DOC, "Notion")
    assert "prefers-color-scheme" not in notion_out

    # media query 在浅色 :root 之后、模型 style 之前（后写覆盖语义依然成立）
    assert out.find(":root{") < out.find("@media(prefers-color-scheme:dark)")
    assert out.find("@media(prefers-color-scheme:dark)") < out.find("<style>.a{")


def test_dark_layer_covers_all_color_variables():
    """深色层必须覆盖全部颜色变量（radius 不随深浅变，从浅色层继承）。"""
    radius = {"--radius-sm", "--radius-md", "--radius-lg"}
    color_vars = {v for v in REQUIRED_VARS if v not in radius}
    for style, dark in _DARK_TOKENS.items():
        names = set(re.findall(r"(--[a-z0-9-]+):", dark))
        missing = color_vars - names
        assert not missing, f"{style} 深色层缺少变量: {missing}"


# ---------------------------------------------------------------------------
# _TOKENS：变量集完整，且四套风格变量名一致
# ---------------------------------------------------------------------------

REQUIRED_VARS = (
    "--bg", "--surface", "--surface-2", "--border", "--border-strong",
    "--text", "--text-2", "--text-3",
    "--primary", "--primary-weak", "--primary-ink",
    "--ok", "--ok-weak", "--warn", "--warn-weak", "--danger", "--danger-weak",
    "--radius-sm", "--radius-md", "--radius-lg",
)


def _names(style):
    return {m for m in re.findall(r"(--[a-z0-9-]+):", _TOKENS[style])}


def test_every_style_defines_full_token_set():
    for style in ALLOWED_STYLES:
        missing = [v for v in REQUIRED_VARS if v not in _TOKENS[style]]
        assert not missing, f"{style} 缺少变量: {missing}"


def test_all_styles_share_same_variable_names():
    """四套风格变量名必须一致，否则换风格会让 var() 取空值。"""
    base = _names("Linear")
    for style in ALLOWED_STYLES:
        assert _names(style) == base, f"{style} 变量集与 Linear 不一致"


def test_custom_style_falls_back_to_a_real_token_set():
    """Custom 没有固定色值，必须复用一整套真实 token 而不是空壳。"""
    assert _TOKENS["Custom"] == _TOKENS["Notion"]


# ---------------------------------------------------------------------------
# lint_html：硬伤、美观信号、误报
# ---------------------------------------------------------------------------

CLEAN_DOC = """<!DOCTYPE html><html><head><style>
:root{--bg:#FFFFFF;--surface:#FFFFFF;--surface-2:#F7F7F5;--border:#E9E9E7;
--text:#37352F;--text-2:#787774;--text-3:#9B9A97;--primary:#2383E2;--primary-weak:#E7F3F8}
body{background:var(--bg);color:var(--text);font-size:14px;line-height:1.7;margin:0}
.card{padding:24px;border-radius:12px;gap:16px}
h1{font-size:32px}h2{font-size:24px}h3{font-size:18px}
</style></head><body><div class="card">你好</div></body></html>"""


def test_clean_document_has_no_warnings():
    """宁可漏报不可误报：合规文档必须零告警。"""
    assert lint_html(CLEAN_DOC) == []


def test_detects_blocked_google_fonts_and_unstable_cdn():
    """放宽 CDN 后：Google Fonts（被墙）与国外 CDN（不稳定）应提示换国内源。"""
    doc = (
        '<html><head><script src="https://cdn.jsdelivr.net/npm/vue"></script>'
        '<link href="https://fonts.googleapis.com/css?family=Inter" rel="stylesheet">'
        "</head><body>x</body></html>"
    )
    issues = lint_html(doc)
    assert any("Google Fonts" in i for i in issues)
    assert any("国外 CDN" in i for i in issues)


def test_domestic_cdn_is_clean():
    """国内可访问的 CDN（BootCDN/staticfile）不应触发 CDN 告警。"""
    doc = (
        '<html><head>'
        '<script src="https://cdn.bootcdn.net/ajax/libs/echarts/5/echarts.min.js"></script>'
        "</head><body>x</body></html>"
    )
    issues = lint_html(doc)
    assert not any("CDN" in i for i in issues)
    assert not any("字体" in i for i in issues)


def test_detects_storage_api_and_placeholders():
    doc = (
        "<html><head></head><body>{{title}}<p>lorem ipsum</p>"
        "<script>localStorage.setItem('a',1)</script></body></html>"
    )
    issues = lint_html(doc)
    assert any("localStorage" in i for i in issues)
    assert any("占位" in i for i in issues)


def test_detects_font_size_proliferation():
    doc = (
        "<html><head><style>"
        + "".join(f".c{i}{{font-size:{s}px}}" for i, s in enumerate([11, 13, 15, 17, 19, 21, 22]))
        + "</style></head><body>x</body></html>"
    )
    assert any("字号" in i for i in lint_html(doc))


def test_six_font_sizes_stay_clean():
    """排版阶梯是 6 档，正好 6 种字号不应触发告警。"""
    doc = (
        "<html><head><style>"
        + "".join(f".c{i}{{font-size:{s}px}}" for i, s in enumerate([12, 14, 15, 18, 24, 32]))
        + "</style></head><body>x</body></html>"
    )
    assert not any("字号" in i for i in lint_html(doc))


def test_detects_off_grid_spacing():
    doc = (
        "<html><head><style>.a{padding:7px}.b{gap:13px}.c{margin:18px}"
        "</style></head><body>x</body></html>"
    )
    assert any("间距" in i for i in lint_html(doc))


def test_mobile_mode_relaxes_type_and_spacing_rules():
    """移动端 App 原型规则：字号 ≤10 档、间距只禁奇数（6/10px 是合理紧凑档）。"""
    # 8 种字号 + 6/10px 偶数间距：桌面会报字号，移动端应全部放过
    doc = (
        "<html><head><style>:root{--bg:#fff}"
        + "".join(f".f{i}{{font-size:{s}px}}" for i, s in enumerate([11, 13, 15, 17, 20, 22, 26, 28]))
        + ".a{padding:6px}.b{gap:10px}.c{margin:12px}"
        + "</style></head><body>x</body></html>"
    )
    mobile_issues = lint_html(doc, scaffolded=True, mobile=True)
    assert not any("字号" in i for i in mobile_issues)
    assert not any("间距" in i for i in mobile_issues)
    # 同一文档桌面模式仍报字号（确认分支真实存在，不是全局放宽）
    assert any("字号" in i for i in lint_html(doc, scaffolded=True))

    # 11 种字号：移动端也报（防失控，不是无限放宽）
    doc11 = (
        "<html><head><style>"
        + "".join(f".g{i}{{font-size:{s}px}}" for i, s in enumerate([10, 11, 12, 13, 14, 15, 16, 17, 18, 20, 28]))
        + "</style></head><body>x</body></html>"
    )
    assert any("字号" in i for i in lint_html(doc11, scaffolded=True, mobile=True))

    # 奇数间距 ≥3 处：移动端仍报（5/7/9/11 手调值在哪都是失控）
    doc_odd = (
        "<html><head><style>:root{--bg:#fff}"
        ".a{padding:7px}.b{gap:9px}.c{margin:11px}</style></head><body>x</body></html>"
    )
    assert any("间距" in i for i in lint_html(doc_odd, scaffolded=True, mobile=True))


def test_mobile_mode_allows_more_content_colors():
    """瀑布流封面色块多：mobile 色值上限放宽到 30（桌面 20）。"""
    colors = [f"#{i:02x}4050" for i in range(25)]  # 25 种不同色值
    style = ":root{" + ";".join(f"--c{i}:{c}" for i, c in enumerate(colors)) + "}"
    doc = f"<html><head><style>{style}</style></head><body>x</body></html>"
    assert not any("硬编码色值" in i for i in lint_html(doc, scaffolded=True, mobile=True))
    assert any("硬编码色值" in i for i in lint_html(doc, scaffolded=True))


def test_border_widths_are_not_spacing_offenders():
    """1px/2px/3px 是边框与微调，不应被算作破档间距。"""
    doc = "<html><head><style>.a{border:1px solid #ccc;padding:1px 2px 3px}</style></head><body>x</body></html>"
    assert not any("间距" in i for i in lint_html(doc))


def test_scaffolded_suppresses_missing_root_hint():
    """基座已兜底时不应再提示未定义 :root，否则模型会被迫重复生成一遍变量。"""
    doc = "<html><head><style>.a{color:var(--text)}</style></head><body>x</body></html>"
    assert any(":root" in i for i in lint_html(doc, scaffolded=False))
    assert not any(":root" in i for i in lint_html(doc, scaffolded=True))


def test_warnings_capped_at_six():
    """告警最多 6 条，避免刷屏淹没重点。"""
    doc = (
        '<html><head><script src="https://x.com/a.js"></script>'
        '<link href="https://x.com/a.css" rel="stylesheet">'
        "<style>@import url(https://x.com/b.css);"
        ".a{font-size:11px}.b{font-size:13px}.c{font-size:15px}.d{font-size:17px}"
        ".e{font-size:19px}.f{font-size:21px}.g{font-size:22px}"
        ".h{padding:7px}.i{gap:13px}.j{margin:18px}</style></head>"
        '<body>{{t}} lorem ipsum<script>localStorage.setItem("a",1)</script></body></html>'
    )
    assert len(lint_html(doc)) <= 6


# ---------------------------------------------------------------------------
# 防漂移：prompt 速查表 ↔ 工具注入的 token
# ---------------------------------------------------------------------------

# 速查表的列顺序（见 _UX_HTML_RULES【1】）
SWATCH_ORDER = (
    "--bg", "--surface", "--surface-2", "--border",
    "--text", "--text-2", "--text-3",
    "--primary", "--primary-weak",
)


def _prompt_swatch(style):
    """从 _UX_HTML_RULES 的速查表里取出某风格的色值列表。"""
    line = next(
        l for l in _UX_HTML_RULES.splitlines() if l.strip().startswith(style + " ")
    )
    return re.findall(r"#[0-9A-Fa-f]{6}", line)


def _token_map(style):
    return dict(re.findall(r"(--[a-z0-9-]+):(#[0-9A-Fa-f]{6})", _TOKENS[style]))


def test_prompt_swatch_matches_injected_tokens():
    """prompt 速查表与工具注入的 token 必须一致。

    只改一侧会让模型拿到的色值和它以为的不一样，且这种漂移不会报错，
    只能靠这条测试兜住。
    """
    for style in ("Notion", "Linear", "Apple", "PlainText", "Obsidian"):
        swatch = _prompt_swatch(style)
        assert len(swatch) == len(SWATCH_ORDER), (
            f"{style} 速查表应 {len(SWATCH_ORDER)} 个色值，实际 {len(swatch)}"
        )
        mapping = _token_map(style)
        for var, color in zip(SWATCH_ORDER, swatch):
            assert mapping[var].upper() == color.upper(), (
                f"{style} {var} 不一致：prompt={color} token={mapping[var]}"
            )


def test_prompt_documents_scaffold_injection():
    """prompt 必须告知模型基座的存在，否则模型会重复输出一遍 token。"""
    assert "自动前置注入" in _UX_HTML_RULES


def test_prompt_documents_industry_profiles():
    """行业感知层：9 行业 + 兜底必须齐全，防后续编辑误删。"""
    for kw in (
        "行业感知",
        "社交内容",
        "电商零售",
        "金融支付",
        "效率工具",
        "生活出行",
        "健康运动",
        "教育学习",
        "媒体娱乐",
        "企业 B 端",
        "未明确命中",
    ):
        assert kw in _UX_HTML_RULES, f"行业感知缺 {kw}"
