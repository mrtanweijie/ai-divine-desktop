import asyncio
import re

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


def test_travel_template_skeleton_matches_handbook_pages():
    from app.pdf_theme_manager import travel_template_skeleton

    skeleton = travel_template_skeleton()
    # 不含样式、注释、页脚
    assert "<style" not in skeleton
    assert "page-footer" not in skeleton
    assert "<!--" not in skeleton
    # 保留页面映射总表
    assert "页面映射总表" in skeleton
    # 每种核心页面类型的代表结构都在
    for token in (
        "cover-band",
        "cover-title",
        "route-map",
        "route-table",
        "route-stop",
        "day-title",
        "time-table",
        "day-section",
        "feature-title",
        "risk-table",
        "highlight-box",
    ):
        assert token in skeleton, token
    # 每日行程只保留 1 个示例页（P3 单日页，其余重复日页已从模板删除）
    assert skeleton.count('class="day-title"') == 1
    page_blocks = re.split(r'(?=<div class="page)', skeleton)
    assert sum(
        'class="day-title"' in block for block in page_blocks
    ) == 1
    # 可选特色页只保留游牧文化体验专页 1 个（专题/城市读本/预算/链接已从模板删除）
    assert skeleton.count('class="feature-title"') == 1
    assert "游牧文化" in skeleton
    assert "小众观察" not in skeleton
    assert "快车核心日" not in skeleton
    assert "city-title" not in skeleton
    assert "budget-table" not in skeleton
    assert "links-group" not in skeleton
    # 骨架里没有任何模板外的类名
    assert "feature-header" not in skeleton
    assert "feature-section" not in skeleton
    assert 'class="arrow"' not in skeleton


def test_travel_system_prompt_embeds_template_skeleton():
    recipe = TravelRecipe()
    intent = PDFIntent(
        title="测试攻略",
        topic="中亚",
        style="travel",
        color_scheme="teal",
        meta={"destination": "中亚", "days": 5, "route": ["阿拉木图", "希瓦"]},
    )
    prompt = recipe.content_system_prompt(intent)
    # 骨架被嵌入 prompt
    assert "travel_template.html" in prompt
    assert 'class="day-title"' in prompt
    assert 'class="risk-table"' in prompt
    assert "页面映射总表" in prompt
    # 明确要求只用模板中的类名、禁止自创类名
    assert "不要自创类名" in prompt
    assert "不要用 feature-header" in prompt
    # 正确的特色页类名在 prompt 中
    assert "feature-title" in prompt
    # 可选扩展类名作为规则说明存在（不再有骨架示例）
    assert "budget-table" in prompt
    assert "links-group" in prompt
    # 元信息注入
    assert "阿拉木图" in prompt


def test_travel_prompt_fallback_appends_risk_page():
    prompt = """生成一份攻略
- Day1 上海：外滩与老城厢
  - 上午：豫园
- Day2 杭州：西湖
【美食清单】
- 生煎
"""
    html = travel_prompt_to_html(prompt)
    assert 'class="risk-table"' in html
    assert 'class="highlight-box"' in html
    assert 'class="route-map"' in html
    # 核心收尾页只有行李/风险页，预算/链接不再强制补全
    assert 'class="budget-table"' not in html
    assert 'class="links-group"' not in html
    assert html.count('class="risk-table"') == 1


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


def test_travel_derive_palette_from_primary_color():
    from app.pdf_theme_manager import derive_travel_palette

    palette = derive_travel_palette("#E74C3C")
    assert palette is not None
    # 5 个核心变量齐全
    for var in (
        "--color-primary",
        "--color-accent",
        "--color-accent-light",
        "--bg-highlight",
        "--bg-cover",
    ):
        assert var in palette
    # 主色压深到可放白字的深度，且配套色有序
    assert palette["--color-accent"] != palette["--color-primary"]
    assert palette["--bg-cover"] != palette["--color-primary"]
    # 颜色名、色值、rgb() 三种写法解析一致
    assert derive_travel_palette("红色") == derive_travel_palette("#E74C3C")
    assert derive_travel_palette("rgb(42, 90, 91)") == derive_travel_palette(
        "#2A5A5B"
    )
    assert derive_travel_palette("青绿") == derive_travel_palette("#2A5A5B")
    assert derive_travel_palette("不存在的颜色") is None


def test_travel_color_overrides_single_primary_color():
    # 只传主色，配套色自动派生（不再残留 teal 默认值）
    overrides = travel_color_overrides(
        "teal", {"--color-primary": "#E74C3C"}
    )
    assert overrides["--color-primary"] == "#E74C3C"
    assert overrides["--color-accent"] != "#3a8a8b"
    assert overrides["--bg-cover"] != "#2a3e3e"
    # 显式传入的配套色优先级最高
    explicit = travel_color_overrides(
        "teal",
        {"--color-primary": "#E74C3C", "--color-accent": "#123456"},
    )
    assert explicit["--color-accent"] == "#123456"


def test_travel_color_overrides_color_name_scheme():
    # color_scheme 直接传颜色名/色值也能派生整套色调
    assert travel_color_overrides("红色") == travel_color_overrides("#E74C3C")
    # 无效颜色名兜底回 teal
    assert travel_color_overrides("not-a-color") == travel_color_overrides(
        "teal"
    )


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
    assert "cover-body" not in html
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
    assert 'class="risk-table"' in content
    # 模板已精简：预算/链接不再作为兜底页输出
    assert 'class="budget-table"' not in content


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
        overrides=None,
        extra_css=None,
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
    assert html.count('<div class="page"><h2 class="day-title">') == 3
    assert "day-block" not in html
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
