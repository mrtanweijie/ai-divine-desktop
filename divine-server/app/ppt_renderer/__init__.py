"""PPT 渲染包：主题 token、排版自适应、原生图表/表格、14 种版式。"""

from .themes import (PPT_THEMES, SLIDE_H, SLIDE_W, blend, get_ppt_theme)
from .layouts import LAYOUTS, add_slide, guess_layout

__all__ = [
    "PPT_THEMES",
    "SLIDE_W",
    "SLIDE_H",
    "LAYOUTS",
    "add_slide",
    "blend",
    "get_ppt_theme",
    "guess_layout",
]
