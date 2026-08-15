import asyncio

from app.pdf_theme_manager import (
    build_cover_html,
    load_theme_css,
)
from app.pdf_tool.base import PDFIntent
from app.pdf_tool.content import generate_content
from app.pdf_tool.engine import PDFTool, _title_from_markdown
from app.pdf_tool.recipes import TravelRecipe
from app.pdf_tool.travel_html import travel_markdown_to_html


def test_travel_theme_css_uses_handbook_style():
    css = load_theme_css("travel")
    assert ".cover-title" in css
    assert ".day-title" in css
    assert ".route-table" in css
    assert ".page.day-block" in css
    assert "--color-primary: #b8743a" in css


def test_travel_cover_builds_route_tags_and_meta():
    html = build_cover_html(
        "travel",
        "中亚陆路旅行手册",
        "AI Divine 生成文档",
        {
            "countries": "中国 × 哈萨克斯坦",
            "route": ["阿拉木图", "希瓦", "布哈拉"],
            "duration": "12天11晚",
            "travelers": 2,
        },
    )
    assert "class=\"cover-title\"" in html
    assert "阿拉木图" in html
    assert "12天11晚" in html
    assert html.count("cover-tag") == 3


def test_travel_fallback_content_keeps_handbook_structure():
    recipe = TravelRecipe()
    assert recipe.css_template == "travel"
    assert recipe.content_format == "html"
    intent = PDFIntent(
        title="测试攻略",
        topic="中亚",
        style="travel",
        color_scheme="warm",
        sections=[],
        meta={"destination": "中亚", "days": 3},
    )
    content = recipe.fallback_content(intent)
    assert '<div class="page">' in content
    assert '<span class="day-badge">D1</span>' in content
    assert 'class="time-row morning"' in content
    assert 'class="budget-table"' in content
    assert 'class="risk-table"' in content


def test_travel_render_forces_cover_on_and_toc_off(monkeypatch, tmp_path):
    import app.pdf_renderer.renderer as renderer_module

    captured: dict[str, bool] = {}

    def fake_render(
        markdown,
        output,
        title,
        style,
        color_scheme,
        paper_size,
        cover,
        toc,
        base_dir,
        theme,
        cover_data,
    ):
        captured["cover"] = cover
        captured["toc"] = toc
        output.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(
        renderer_module, "_render_with_weasyprint", fake_render
    )
    monkeypatch.setattr(renderer_module, "_weasyprint_available", lambda: True)
    renderer_module.render_markdown_to_pdf(
        "## 章节",
        tmp_path / "out.pdf",
        theme="travel",
        toc=True,
    )
    assert captured["cover"] is True
    assert captured["toc"] is False


def test_travel_generate_content_accepts_html_body():
    class FakeLLM:
        async def stream(self, messages):
            yield {
                "type": "message",
                "content": '<div class="page"><h2 class="day-title">Day 1</h2></div>',
            }

    recipe = TravelRecipe()
    intent = PDFIntent(
        title="测试攻略",
        topic="中亚",
        style="travel",
        color_scheme="warm",
    )
    content = asyncio.run(generate_content(intent, recipe, FakeLLM()))
    assert 'class="day-title"' in content
    assert "Day 1" in content


def test_travel_markdown_is_converted_to_template_html():
    markdown = """# 广西旅行

## 路线总览

桂林 → 阳朔 → 崇左

## Day 1（10.1）抵达桂林

✦ 落地桂林
🏠 宿：市区

**吃什么**：桂林米粉
**交通与预订**：提前买票

## 预算清单

| 项目 | 经济型 | 舒适型 |
| --- | --- | --- |
| 交通 | 700 | 1100 |
"""
    html = travel_markdown_to_html(markdown)
    assert '<div class="page">' in html
    assert '<span class="day-badge">D1</span>' in html
    assert 'class="plain-list"' in html
    assert 'class="budget-table"' in html


def test_travel_title_comes_from_markdown_heading():
    title = _title_from_markdown(
        "# 国庆 7 天广西旅游攻略（10.1-10.7）\n\n## 方案 C：桂林"
    )
    assert title == "国庆 7 天广西旅游攻略（10.1-10.7）"


def test_travel_plan_subtitle_stays_on_overview_page():
    markdown = """# 国庆 7 天广西旅游攻略

## 方案 C：桂林山水 + 崇左德天跨国瀑布

**路线总览**：桂林 → 崇左

## Day 1（10.1）抵达桂林

- 落地桂林
"""
    html = travel_markdown_to_html(markdown)
    assert html.count('<h2 class="section-title">路线总览</h2>') == 1
    assert 'class="section-subtitle"' in html
    assert "方案 C" in html


def test_travel_converts_every_day_heading_to_own_page():
    markdown = """# 哈尔滨攻略

## 每日详细行程

### D1 抵达哈尔滨
- 抵达太平机场

### D2 哈尔滨市区
- 冰雪大世界

### D3 哈尔滨 → 亚布力
- 抵达滑雪场
"""
    html = travel_markdown_to_html(markdown)
    assert html.count('<span class="day-badge">') == 3
    assert html.count('<div class="page day-block"><h2 class="day-title">') == 3
    assert "D1" in html
    assert "D2" in html
    assert "D3" in html


def test_travel_generates_pdf_without_html_output(tmp_path):
    markdown = """# 国庆 7 天广西旅游攻略

## Day 1（10.1）抵达桂林

- 落地桂林
"""
    async def run():
        return await PDFTool().run(
            prompt="生成旅行手册 PDF",
            output=tmp_path / "guide.pdf",
            kind="travel",
            theme="travel",
            content=markdown,
        )

    meta = asyncio.run(run())
    assert meta["renderer"] == "weasyprint"
    assert (tmp_path / "guide.pdf").exists()
    assert "html_filepath" not in meta
