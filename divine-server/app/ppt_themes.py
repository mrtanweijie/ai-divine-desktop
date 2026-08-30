"""兼容 shim：渲染实现已迁移到 app/ppt_renderer 包。

仅保留主题 token 与工具函数的再导出；旧版式函数（add_title_slide 等）
已由 ppt_renderer.layouts.add_slide 统一替代。
"""

from __future__ import annotations

from app.ppt_renderer.themes import (  # noqa: F401
    PPT_THEMES,
    SLIDE_H,
    SLIDE_W,
    get_ppt_theme,
)
