"""Facade that picks WeasyPrint first and falls back to ReportLab."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .markdown import _normalize
from .reportlab import _render_with_reportlab
from .styles import COLOR_KEYS, PAPER_KEYS, STYLE_KEYS
from .weasyprint import _render_with_weasyprint, _weasyprint_available

logger = logging.getLogger("divine.pdf")

def render_markdown_to_pdf(
    markdown: str,
    output: Path,
    title: str = "PDF文档",
    style: str = "modern",
    color_scheme: str = "blue",
    paper_size: str = "A4",
    cover: bool = False,
    toc: bool = False,
    base_dir: Path | None = None,
    theme: str = "universal",
) -> dict[str, Any]:
    normalized_style = _normalize(style, STYLE_KEYS, "modern")
    normalized_color = _normalize(color_scheme, COLOR_KEYS, "blue")
    normalized_paper = _normalize(paper_size, PAPER_KEYS, "a4")
    if _weasyprint_available():
        try:
            _render_with_weasyprint(
                markdown,
                output,
                title,
                normalized_style,
                normalized_color,
                normalized_paper,
                cover,
                toc,
                base_dir,
                theme,
            )
            renderer = "weasyprint"
            return {
                "title": title,
                "style": normalized_style,
                "color_scheme": normalized_color,
                "paper_size": normalized_paper,
                "renderer": renderer,
            }
        except Exception:
            logger.warning(
                "weasyprint render failed, falling back to reportlab",
                exc_info=True,
            )
            pass
    _render_with_reportlab(markdown, output, title, base_dir, theme)
    renderer = "reportlab"
    return {
        "title": title,
        "style": normalized_style,
        "color_scheme": normalized_color,
        "paper_size": normalized_paper,
        "renderer": renderer,
    }
