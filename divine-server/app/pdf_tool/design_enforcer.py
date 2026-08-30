"""设计决策校验与修正层。

对 design_rules 产出的 DesignDecision 做二次校验：
- 主题必须是已知值，否则回退到配方默认；
- 配色必须是已知预设或可解析的颜色值（"红色"/#E74C3C 等），否则回退；
- 旅行主题强制 cover=True、toc=False（与渲染器约定一致）。
"""

from __future__ import annotations

from typing import Any

from ..pdf_theme_manager import resolve_color
from .base import PDFRecipe
from .design_rules import (
    KNOWN_COLOR_SCHEMES,
    KNOWN_THEMES,
    DesignDecision,
)


def enforce_design(
    decision: DesignDecision,
    recipe: PDFRecipe,
) -> DesignDecision:
    """校验并修正设计决策；返回新的（或原样的）决策对象。"""
    if decision.theme not in KNOWN_THEMES:
        decision.theme = recipe.css_template
    if (
        decision.color_scheme not in KNOWN_COLOR_SCHEMES
        and not resolve_color(decision.color_scheme)
    ):
        decision.color_scheme = recipe.color_scheme
    if decision.theme in ("travel", "travel_mag"):
        decision.cover = True
        decision.toc = False
    return decision
