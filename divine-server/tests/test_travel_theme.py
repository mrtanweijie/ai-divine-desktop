import asyncio

from app.pdf_theme_manager import (
    build_cover_html,
    load_theme_css,
    travel_color_overrides,
)
from app.pdf_tool.base import PDFIntent
from app.pdf_tool.content import generate_content
from app.pdf_tool.engine import (
    PDFTool,
    _looks_like_generic_travel_fallback,
    _route_from_markdown,
    _summary_from_markdown,
    _title_from_markdown,
)
from app.pdf_tool.recipes import TravelRecipe
from app.pdf_tool.travel_html import (
    travel_markdown_to_html,
    travel_prompt_to_html,
)


def test_travel_theme_css_uses_handbook_style():
    css = load_theme_css("travel")
    assert ".cover-title" in css
    assert ".day-title" in css
    assert ".route-table" in css
    assert ".page.day-block" in css
    assert "--color-primary: #2A5A5B" in css


def test_travel_color_overrides_switch_palette():
    blue_css = load_theme_css(
        "travel", overrides=travel_color_overrides("blue")
    )
    assert "--color-primary: #2f5b9e" in blue_css
    custom_css = load_theme_css(
        "travel",
        overrides=travel_color_overrides(
            "teal", {"--color-primary": "#123456"}
        ),
    )
    assert "--color-primary: #123456" in custom_css


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
    assert "class=\"cover-band\"" in html
    assert "class=\"cover-body\"" in html
    assert "cover-hero" not in html
    assert "12天11晚" in html


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
    assert "D1" in content
    assert 'class="time-table"' in content
    assert 'class="day-section"' in content
    assert 'class="check-list"' in content
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
    assert 'class="day-title">D1' in html
    assert 'class="day-section"' in html
    assert 'class="check-list"' in html
    assert 'class="budget-table"' in html


def test_travel_title_comes_from_markdown_heading():
    title = _title_from_markdown(
        "# 国庆 7 天广西旅游攻略（10.1-10.7）\n\n## 方案 C：桂林"
    )
    assert title == "国庆 7 天广西旅游攻略（10.1-10.7）"


def test_travel_cover_meta_comes_from_markdown():
    markdown = """# 马来西亚 7 日旅行手册

西马人文经典线：**吉隆坡 → 马六甲 → 槟城**，兼顾城市人文与美食。

## 逐日行程
"""
    assert "吉隆坡" in _summary_from_markdown(markdown)
    assert _route_from_markdown(markdown)[0] == "吉隆坡"


def test_travel_generic_fallback_is_detected():
    assert _looks_like_generic_travel_fallback(
        '<div class="page"><h2 class="day-title">D1｜第 1 天</h2></div>'
    )


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
    assert html.count('class="day-title">D') == 3
    assert html.count('<div class="page day-block"><h2 class="day-title">') == 3
    assert "D1" in html
    assert "D2" in html
    assert "D3" in html


def test_travel_code_timeline_becomes_route_map():
    markdown = """# 马来西亚

## 城市时间轴

```
D1 ── D2 ── D3
吉隆坡 ─ 马六甲 ─ 槟城
```
"""
    html = travel_markdown_to_html(markdown)
    assert 'class="route-map"' in html
    assert "吉隆坡" in html
    assert "<pre>" not in html


def test_travel_chinese_day_headings_and_route_overview():
    markdown = """# 马来西亚

## 路线概览

吉隆坡 → 马六甲 → 槟城

## 逐日行程

### 第 1 天 抵达吉隆坡
- 上午：逛 KLCC
- 晚上：阿罗街夜市
"""
    html = travel_markdown_to_html(markdown)
    assert 'class="day-title">D1' in html
    assert 'class="route-map"' in html
    assert 'class="time-table"' in html


def test_travel_prompt_with_day_lines_builds_template():
    prompt = """生成一份攻略

- Day1 上海·外滩与老城厢：抵达上海
  - 上午：豫园
  - 晚上：外滩
- Day2 杭州·西湖：上午高铁

【美食清单】
- 上海：生煎
"""
    html = travel_prompt_to_html(prompt)
    assert 'class="day-title">D1' in html
    assert 'class="time-table"' in html
    assert 'class="check-list"' in html
    assert "生煎" in html


def test_travel_generates_pdf_without_html_output(tmp_path, monkeypatch):
    markdown = """# 国庆 7 天广西旅游攻略

## Day 1（10.1）抵达桂林

- 落地桂林
"""

    class FakeLLM:
        async def stream(self, messages):
            yield {
                "type": "message",
                "content": '<div class="page"><h2 class="day-title">Day 1</h2></div>',
            }

    monkeypatch.setattr(
        "app.pdf_tool.engine.build_llm", lambda: FakeLLM()
    )

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
