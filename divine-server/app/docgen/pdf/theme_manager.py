"""PDF 主题管理器（facade）：内容已拆分为三个子模块。

拆分结构（2026-09-01，自原 2,039 行单文件）：
- theme_colors:  颜色体系（预设色表、HSL 派生、旅行/通用覆盖计算）
- theme_registry: 主题注册与 CSS 加载（THEMES、ThemeManager、load_theme_css）
- cover_builder: 封面与旅行版式（build_cover_html、build_travel_html_document）

本文件保留完整再导出面（含 word/illustration 引用的私有名），存量调用方
（api/pdf_themes、tools/scripts/pdf_render、renderer/*、tests）无需改动。
新代码建议直接从子模块导入。
"""

from .theme_colors import *  # noqa: F401,F403
from .theme_registry import *  # noqa: F401,F403
from .cover_builder import *  # noqa: F401,F403

# 存量调用方依赖的私有名（word/elements、pdf_tool/illustration）
from .cover_builder import _fetch_image_data, _image_data_uri, _keyword_to_image_url  # noqa: F401

from .theme_registry import ThemeConfig, ThemeManager  # noqa: F401  # 类名不被 import * 导出
