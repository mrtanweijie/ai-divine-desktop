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
    cover_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_style = _normalize(style, STYLE_KEYS, "modern")
    normalized_color = _normalize(color_scheme, COLOR_KEYS, "blue")
    normalized_paper = _normalize(paper_size, PAPER_KEYS, "a4")
    if theme == "travel":
        cover = True
        toc = False
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
                cover_data,
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


def render_html_to_pdf(
    html_body: str,
    output: Path,
    title: str = "PDF文档",
    paper_size: str = "A4",
    cover: bool = True,
    cover_data: dict[str, Any] | None = None,
    base_dir: Path | None = None,
    theme: str = "travel",
) -> dict[str, Any]:
    normalized_paper = _normalize(paper_size, PAPER_KEYS, "a4")
    if not _weasyprint_available():
        raise RuntimeError("HTML 转 PDF 需要 WeasyPrint，当前环境不可用")
    from weasyprint import HTML

    from ..pdf_theme_manager import build_travel_html_document

    document = build_travel_html_document(
        html_body,
        title,
        cover_data=cover_data,
        include_cover=cover,
    )
    kwargs: dict[str, Any] = {"string": document}
    if base_dir is not None:
        kwargs["base_url"] = str(base_dir)
    try:
        HTML(**kwargs).write_pdf(str(output), presentational_hints=True)
    except Exception:
        logger.warning("travel HTML render failed", exc_info=True)
        raise RuntimeError("旅行 HTML 转 PDF 渲染失败") from None
    return {
        "title": title,
        "theme": theme,
        "paper_size": normalized_paper,
        "renderer": "weasyprint",
    }
