"""Resume package：简历生成（统一模板库入口见 templates 包）。"""

from .templates import build_html, render_template_resume  # noqa: F401

__all__ = ["build_html", "render_template_resume"]
