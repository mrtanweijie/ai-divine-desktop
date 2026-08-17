"""设计决策校验与修正层。

对 design_rules 产出的 DesignDecision 做二次校验：
- 主题/配色必须是已知值，否则回退到配方默认；
- 旅行主题强制 cover=True、toc=False（与渲染器约定一致）。
"""

from __future__ import annotations

from typing import Any

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
    if decision.color_scheme not in KNOWN_COLOR_SCHEMES:
        decision.color_scheme = recipe.color_scheme
    if decision.theme in ("travel", "travel_mag"):
        decision.cover = True
        decision.toc = False
    return decision
