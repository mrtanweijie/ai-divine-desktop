"""设计决策层（DesignSpec / 色板派生 / 扩展配色）测试。"""

from app.docgen.pdf.renderer.weasyprint import _color_scheme_overrides
from app.docgen.pdf.theme_manager import (
    SCHEME_PRIMARY_COLORS,
    derive_universal_palette,
    universal_color_overrides,
)
from app.docgen.pdf.design_enforcer import enforce_design
from app.docgen.pdf.design_rules import DesignDecision, resolve_design
from app.docgen.pdf.recipes import ReportRecipe


def test_derive_universal_palette_hex():
    palette = derive_universal_palette("#E74C3C")
    assert palette is not None
    assert set(palette) == {
        "--primary",
        "--accent",
        "--primary-light",
        "--primary-dark",
    }
    for value in palette.values():
        assert value.startswith("#")
        int(value.lstrip("#"), 16)


def test_derive_universal_palette_named_and_invalid():
    assert derive_universal_palette("红色") is not None
    assert derive_universal_palette("藏青") is not None
    assert derive_universal_palette("不是一个颜色") is None
    assert derive_universal_palette("") is None


def test_extended_scheme_primaries_cover_all_schemes():
    expected = {
        "iceblue",
        "desert",
        "vintage",
        "midnight",
        "pureblack",
        "mistsage",
        "mistblue",
        "duskmauve",
        "lotuspink",
        "dunesand",
        "smokegray",
    }
    assert expected <= set(SCHEME_PRIMARY_COLORS)


def test_color_scheme_overrides_extended_scheme():
    overrides = _color_scheme_overrides("iceblue")
    assert overrides["--primary"] == "#2C5775"
    assert "--primary-light" in overrides


def test_color_scheme_overrides_raw_color():
    overrides = _color_scheme_overrides("红色")
    assert overrides["--primary"].startswith("#")
    assert overrides["--primary-light"].startswith("#")


def test_universal_color_overrides_derives_from_primary():
    overrides = universal_color_overrides({"--color-primary": "#E74C3C"})
    assert overrides["--primary"]
    assert overrides["--primary-light"]
    assert overrides["--primary-dark"]


def test_universal_color_overrides_explicit_wins():
    overrides = universal_color_overrides(
        {"--primary": "#123456", "--accent": "#654321"}
    )
    assert overrides["--primary"] == "#123456"
    assert overrides["--accent"] == "#654321"


def test_universal_color_overrides_empty():
    assert universal_color_overrides(None) == {}
    assert universal_color_overrides({}) == {}


def test_resolve_design_spec_beats_scene():
    decision = resolve_design(
        "季度工作汇报",
        recipe_name="report",
        design_spec={"base_theme": "academic", "primary_color": "红色"},
    )
    assert decision.theme == "academic"
    assert decision.theme_source == "design-llm"
    assert decision.primary_color == "红色"
    assert decision.primary_source == "design-llm"
    # 场景标签保留（封面 badge 仍可用）
    assert decision.scene == "quarterly"


def test_resolve_design_style_words_beat_spec():
    decision = resolve_design(
        "要极简风格的季度汇报",
        recipe_name="report",
        design_spec={"base_theme": "academic"},
    )
    assert decision.theme == "minimal"
    assert decision.theme_source == "override"


def test_resolve_design_explicit_args_beat_spec():
    decision = resolve_design(
        "季度工作汇报",
        recipe_name="report",
        theme="notion",
        color_scheme="green",
        design_spec={
            "base_theme": "academic",
            "primary_color": "红色",
            "cover": False,
        },
    )
    assert decision.theme_source == "explicit"
    assert decision.theme == "notion"
    assert decision.color_scheme == "green"
    assert decision.primary_color is None


def test_resolve_design_spec_cover_toc():
    decision = resolve_design(
        "整理一下本周进展",  # weekly 场景默认 cover=True/toc=False
        recipe_name="report",
        design_spec={"cover": False, "toc": True},
    )
    assert decision.cover is False
    assert decision.cover_source == "design-llm"
    assert decision.toc is True
    assert decision.toc_source == "design-llm"


def test_resolve_design_invalid_spec_ignored():
    decision = resolve_design(
        "季度工作汇报",
        recipe_name="report",
        design_spec={
            "base_theme": "not-a-theme",
            "primary_color": "不是颜色",
            "cover_style": "bogus",
            "cover": "yes",
        },
    )
    assert decision.theme == "universal"  # 回落到 quarterly 场景主题
    assert decision.primary_color is None
    assert decision.cover_style == "split"  # 场景默认
    assert decision.cover_source == "scene"


def test_resolve_design_spec_cover_style():
    decision = resolve_design(
        "随便写点什么",
        recipe_name="report",
        design_spec={"cover_style": "terminal"},
    )
    assert decision.cover_style == "terminal"


def test_resolve_design_travel_gets_spec_primary():
    decision = resolve_design(
        "日本旅行攻略",
        recipe_name="travel",
        recipe_theme="travel",
        design_spec={"primary_color": "#123456"},
    )
    assert decision.primary_color == "#123456"
    assert decision.primary_source == "design-llm"


def test_enforce_design_keeps_resolvable_raw_scheme():
    decision = DesignDecision(
        theme="universal", style="", color_scheme="红色",
        cover=True, toc=False,
    )
    enforced = enforce_design(decision, ReportRecipe())
    assert enforced.color_scheme == "红色"


def test_enforce_design_rejects_unknown_scheme():
    decision = DesignDecision(
        theme="universal", style="", color_scheme="not-a-color-xyz",
        cover=True, toc=False,
    )
    enforced = enforce_design(decision, ReportRecipe())
    assert enforced.color_scheme == ReportRecipe.color_scheme
