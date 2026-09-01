"""测试设计决策层：场景分类、风格词覆盖解析、决策解析与引擎接入。"""

import asyncio

from app.docgen.pdf.base import PDFIntent
from app.docgen.pdf.design_enforcer import enforce_design
from app.docgen.pdf.design_rules import (
    DesignDecision,
    classify_scene,
    parse_cover_style,
    parse_override,
    resolve_design,
)
from app.docgen.pdf.recipes import ReportRecipe, TravelRecipe


# ---------------------------------------------------------------------------
# 场景分类
# ---------------------------------------------------------------------------

def test_classify_all_scenes():
    assert classify_scene("帮我写一下这周的工作周报") == "weekly"
    assert classify_scene("做一份 2026 Q2 季度汇报给 VP") == "quarterly"
    assert classify_scene("给客户的数据平台迁移方案") == "proposal"
    assert classify_scene("写一份 PRD，验收标准要写清楚") == "prd"
    assert classify_scene("我的个人作品集展示") == "portfolio"
    assert classify_scene("一篇关于 AI Agent 的行业洞察长文") == "editorial"


def test_classify_priority_proposal_over_quarterly():
    # 提案（客户/方案）优先级高于季度汇报（CTO/高管）
    assert classify_scene("给 CTO 的技术架构提案") == "proposal"
    assert classify_scene("给老板的季度总结汇报") == "quarterly"


def test_classify_returns_none_for_unmatched():
    assert classify_scene("帮我写一篇关于咖啡的文章") is None


# ---------------------------------------------------------------------------
# 风格词覆盖解析
# ---------------------------------------------------------------------------

def test_parse_override_theme_and_color():
    theme, color, cover, toc = parse_override("用商务风格，蓝色主题")
    assert theme == "universal"
    assert color == "blue"
    assert cover is None
    assert toc is None


def test_parse_override_cover_toc():
    theme, color, cover, toc = parse_override("要封面，加个目录")
    assert theme is None
    assert color is None
    assert cover is True
    assert toc is True


def test_parse_override_no_cover():
    theme, color, cover, toc = parse_override("不要封面，不加目录")
    assert cover is False
    assert toc is False


def test_parse_cover_style_aliases():
    assert parse_cover_style("左对齐经典") == "left-aligned"
    assert parse_cover_style("居中杂志") == "centered"
    assert parse_cover_style("左右分屏") == "split"
    assert parse_cover_style("极简文字") == "minimal"
    assert parse_cover_style("大色块图形") == "hero-graphic"
    assert parse_cover_style("终端风格") == "terminal"
    assert parse_cover_style("普通报告") is None


def test_resolve_no_cover_word_beats_scene():
    # 用户明确"不要封面"优先于场景默认封面
    d = resolve_design("不要封面的季度汇报", recipe_name="report")
    assert d.cover is False
    assert d.scene == "quarterly"
    assert d.cover_source == "override"


def test_resolve_cover_style_beats_scene():
    # 用户明确"左对齐经典"优先于行业洞察场景默认的居中封面
    d = resolve_design(
        "摄影摄像类商户画像数据分析报告，左对齐经典",
        recipe_name="report",
    )
    assert d.scene == "editorial"
    assert d.cover_style == "left-aligned"


def test_resolve_explicit_cover_style_param_wins():
    d = resolve_design(
        "行业洞察报告，居中杂志",
        recipe_name="report",
        cover_style="left-aligned",
    )
    assert d.cover_style == "left-aligned"


# ---------------------------------------------------------------------------
# 决策解析：显式 > 风格词 > 场景 > 配方默认
# ---------------------------------------------------------------------------

def test_resolve_scene_defaults():
    d = resolve_design("写一份第三季度业务总结", recipe_name="report")
    assert d.theme == "universal"
    assert d.color_scheme == "blue"
    assert d.cover is True
    assert d.toc is True
    assert d.scene == "quarterly"
    assert d.theme_source == "scene"


def test_resolve_weekly_scene():
    d = resolve_design("本周工作周报", recipe_name="report")
    assert d.theme == "minimal"
    assert d.cover is True  # 默认加封面
    assert d.toc is False


def test_resolve_override_beats_scene():
    # 风格词优先于场景分类
    d = resolve_design("用商务风做个季度汇报", recipe_name="report")
    assert d.theme == "universal"
    assert d.theme_source == "override"
    assert d.color_scheme == "blue"

    d2 = resolve_design("周报要正式一点", recipe_name="report")
    assert d2.theme == "universal"

    d3 = resolve_design("极简黑白风格的季度汇报", recipe_name="report")
    assert d3.theme == "minimal"


def test_resolve_explicit_param_wins():
    d = resolve_design(
        "写一份周报", recipe_name="report", theme="modern"
    )
    assert d.theme == "modern"
    assert d.theme_source == "explicit"


def test_resolve_style_param_maps_to_theme():
    d = resolve_design("随便写点东西", recipe_name="report", style="academic")
    assert d.theme == "academic"
    assert d.theme_source == "explicit-style"


def test_resolve_cover_toc_words():
    d = resolve_design("带封面和目录的行业分析", recipe_name="report")
    assert d.cover is True
    assert d.toc is True
    assert d.theme == "academic"


def test_resolve_recipe_fallback():
    from app.docgen.pdf.recipes import BookRecipe

    recipe = BookRecipe()
    d = resolve_design(
        "一篇关于咖啡的文章",
        recipe_name="book",
        recipe_theme=recipe.css_template,
        recipe_color=recipe.color_scheme,
    )
    assert d.theme == "academic"  # book 配方默认主题
    assert d.scene is None
    assert d.theme_source == "recipe"
    assert d.cover is True  # 默认加封面
    assert d.toc is False


def test_resolve_travel_passthrough():
    # 旅行走独立主题体系，场景/风格词均不适用
    d = resolve_design(
        "做一份旅游方案", recipe_name="travel", recipe_theme="travel"
    )
    assert d.theme == "travel"
    assert d.scene is None

    d2 = resolve_design(
        "做一份杂志风的旅行攻略",
        recipe_name="travel",
        theme="travel_mag",
        recipe_theme="travel",
    )
    assert d2.theme == "travel_mag"


# ---------------------------------------------------------------------------
# 决策校验
# ---------------------------------------------------------------------------

def test_enforce_unknown_theme_falls_back():
    d = DesignDecision(
        theme="nonexistent",
        style="",
        color_scheme="blue",
        cover=False,
        toc=False,
    )
    out = enforce_design(d, ReportRecipe())
    assert out.theme == "universal"  # report 配方默认
    assert out.color_scheme == "blue"


def test_enforce_travel_consistency():
    d = DesignDecision(
        theme="travel_mag",
        style="",
        color_scheme="teal",
        cover=False,
        toc=True,
    )
    out = enforce_design(d, TravelRecipe())
    assert out.cover is True
    assert out.toc is False


# ---------------------------------------------------------------------------
# 引擎接入（PDFTool.run）
# ---------------------------------------------------------------------------

def _patch_render(monkeypatch, tmp_path):
    import app.docgen.pdf.renderer.renderer as renderer_module

    captured: dict[str, object] = {}

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
        captured["theme"] = theme
        captured["cover"] = cover
        captured["toc"] = toc
        captured["color_scheme"] = color_scheme
        captured["overrides"] = overrides
        output.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(renderer_module, "_render_with_weasyprint", fake_render)
    monkeypatch.setattr(renderer_module, "_weasyprint_available", lambda: True)
    return captured


def test_engine_applies_scene_theme(monkeypatch, tmp_path):
    from app.docgen.pdf.engine import PDFTool

    captured = _patch_render(monkeypatch, tmp_path)

    async def run():
        return await PDFTool().run(
            prompt="帮我写一份第三季度业务汇报",
            output=tmp_path / "report.pdf",
            kind="report",
            content="# 季度汇报\n\n## 数据\n\n- 增长 34%",
        )

    meta = asyncio.run(run())
    assert meta["theme"] == "universal"
    assert meta["design"]["scene"] == "quarterly"
    assert captured["theme"] == "universal"
    assert captured["cover"] is True
    assert captured["toc"] is True


def test_engine_override_wins_over_scene(monkeypatch, tmp_path):
    from app.docgen.pdf.engine import PDFTool

    captured = _patch_render(monkeypatch, tmp_path)

    async def run():
        return await PDFTool().run(
            prompt="极简版季度汇报",
            output=tmp_path / "report.pdf",
            kind="report",
            content="# 汇报\n\n## 数据\n\n- a",
        )

    meta = asyncio.run(run())
    assert meta["theme"] == "minimal"
    assert captured["theme"] == "minimal"


def test_engine_explicit_theme_wins(monkeypatch, tmp_path):
    from app.docgen.pdf.engine import PDFTool

    captured = _patch_render(monkeypatch, tmp_path)

    async def run():
        return await PDFTool().run(
            prompt="写一份周报",
            output=tmp_path / "report.pdf",
            kind="report",
            theme="modern",
            content="# 周报\n\n## 完成\n\n- x",
        )

    meta = asyncio.run(run())
    assert meta["theme"] == "modern"
    assert meta["design"]["theme_source"] == "explicit"
    assert captured["theme"] == "modern"
