"""测试封面模块：6 种风格渲染、场景映射、travel 隔离。"""

import asyncio

from app.pdf_theme_manager import build_cover_html, load_theme_css
from app.pdf_tool.design_rules import resolve_design


def test_all_cover_styles_render():
    styles = [
        "left-aligned",
        "centered",
        "split",
        "minimal",
        "hero-graphic",
        "terminal",
    ]
    data = {
        "badge": "Q2 2026",
        "author": "算法团队",
        "meta": {"作者": "算法团队", "周期": "2026 Q2"},
        "highlight": {
            "value": "99.99%",
            "label": "可用性 SLA",
            "stats": [{"label": "P99", "value": "42ms"}],
        },
        "issue_no": "Vol. 03 · 2026",
        "doc_type": "Weekly Report",
        "info": {"团队": "后端组"},
        "cta_text": "→ 详见第 3 页",
        "prompt": "cat README.md",
        "output_lines": [{"type": "ok", "text": "HEALTHY"}],
    }
    style_class = {
        "left-aligned": "cover-left",
        "centered": "cover-centered",
        "split": "cover-split",
        "minimal": "cover-minimal",
        "hero-graphic": "cover-hero",
        "terminal": "cover-terminal",
    }
    for style in styles:
        html = build_cover_html(
            "universal", "报告标题", "副标题", {**data, "cover_style": style}
        )
        assert style_class[style] in html, style
        assert "报告标题" in html, style


def test_long_cover_title_is_forced_to_wrap_inside_page():
    title = "摄影/摄像类商户画像数据分析报告"
    for style in (
        "left-aligned",
        "centered",
        "split",
        "minimal",
        "hero-graphic",
        "terminal",
    ):
        html = build_cover_html(
            "universal",
            title,
            "副标题",
            {"cover_style": style},
        )
        assert "white-space:normal" in html, style
        assert "max-width:100%" in html, style
        assert "overflow-wrap:break-word;word-break:break-word" in html, style


def test_cover_data_escaped():
    # title/subtitle 由调用方预先转义；cover_data 内字段由模板函数转义
    html = build_cover_html(
        "universal",
        "标题",
        "副标题",
        {
            "cover_style": "left-aligned",
            "badge": "<b>x</b>",
            "meta": {"作者": "<i>a</i>"},
        },
    )
    assert "<script>" not in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html
    assert "&lt;i&gt;a&lt;/i&gt;" in html


def test_split_cover_fallback_without_highlight():
    html = build_cover_html(
        "universal",
        "季度汇报",
        "副标题",
        {
            "cover_style": "split",
            "badge": "季度汇报",
            "author": "AI Divine",
            "meta": {"周期": "2026 Q2"},
        },
    )
    assert 'class="right-panel"' in html  # 无 highlight 也有右侧面板兜底
    assert "highlight-num" in html
    assert "AI Divine" in html


def test_travel_cover_unaffected():
    html = build_cover_html(
        "travel",
        "日本攻略",
        "深度游",
        {"destination": "日本", "days": 5, "cover_style": "split"},
    )
    assert "cover-split" not in html
    assert "cover-band" in html


def test_theme_css_contains_cover_styles():
    css = load_theme_css("universal")
    for token in (".cover-left", ".cover-centered", ".cover-split", ".cover-hero", ".cover-terminal"):
        assert token in css, token


def test_scene_maps_to_cover_style():
    assert resolve_design("做一份季度汇报", recipe_name="report").cover_style == "split"
    assert resolve_design("写一篇行业洞察", recipe_name="report").cover_style == "centered"
    assert resolve_design("给客户的技术方案", recipe_name="report").cover_style == "left-aligned"
    assert resolve_design("我的个人作品集", recipe_name="report").cover_style == "hero-graphic"
    assert resolve_design("本周工作周报", recipe_name="report").cover_style == "minimal"


def test_travel_decision_has_no_cover_style():
    d = resolve_design("做一份日本攻略", recipe_name="travel")
    assert d.cover_style is None


def test_engine_injects_cover_style(monkeypatch, tmp_path):
    import app.pdf_renderer.renderer as renderer_module

    captured: dict[str, object] = {}

    def fake_render(
        markdown, output, title, style, color_scheme, paper_size,
        cover, toc, base_dir, theme, cover_data,
    ):
        captured["cover_data"] = cover_data
        output.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(renderer_module, "_render_with_weasyprint", fake_render)
    monkeypatch.setattr(renderer_module, "_weasyprint_available", lambda: True)

    from app.pdf_tool.engine import PDFTool

    async def run():
        return await PDFTool().run(
            prompt="做一份 Q2 季度汇报给老板",
            output=tmp_path / "r.pdf",
            kind="report",
            content="# 标题\n\n## 章节\n\n正文",
        )

    meta = asyncio.run(run())
    assert meta["design"]["cover_style"] == "split"
    cover_data = captured["cover_data"] or {}
    assert cover_data.get("cover_style") == "split"
    assert cover_data.get("badge") == "季度汇报"


def test_title_from_markdown_only_h1():
    from app.pdf_tool.engine import _title_from_markdown

    assert _title_from_markdown("# 文档标题\n\n## 章节") == "文档标题"
    # ## 章节名不再被误认为文档标题
    assert _title_from_markdown("## 核心指标\n\n正文") == ""


def test_hero_stat_extraction_for_split_cover():
    from app.pdf_tool.engine import _hero_stat_from_markdown

    md = """| 指标 | 数值 | 变化 |
| --- | --- | --- |
| DAU | 2.4M | +34% |
| 留存率 | 42% | +8% |
{: .hero-stat}

正文
"""
    hl = _hero_stat_from_markdown(md)
    assert hl is not None
    assert hl["value"] == "2.4M"
    assert hl["label"] == "DAU"
    assert len(hl["stats"]) == 1
    assert hl["stats"][0]["label"] == "留存率"

    assert _hero_stat_from_markdown("没有表格\n") is None
