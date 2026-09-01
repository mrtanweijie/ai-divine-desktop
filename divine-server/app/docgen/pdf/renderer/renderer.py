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
    overrides: dict[str, Any] | None = None,
    extra_css: str | None = None,
) -> dict[str, Any]:
    normalized_style = _normalize(style, STYLE_KEYS, "modern")
    # color_scheme 除经典 5 色外，还支持扩展预设（iceblue 等）与直接传颜色
    #（"红色"/#E74C3C）：非经典值原样保留，由渲染层按主色派生覆盖
    raw_scheme = (color_scheme or "").strip()
    if raw_scheme.lower() in COLOR_KEYS:
        normalized_color = raw_scheme.lower()
    else:
        from ..theme_manager import SCHEME_PRIMARY_COLORS, resolve_color

        normalized_color = (
            raw_scheme
            if raw_scheme
            and (
                raw_scheme.lower() in SCHEME_PRIMARY_COLORS
                or resolve_color(raw_scheme)
            )
            else "blue"
        )
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
                overrides,
                extra_css,
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
    overrides: dict[str, str] | None = None,
    images: bool = False,
) -> dict[str, Any]:
    normalized_paper = _normalize(paper_size, PAPER_KEYS, "a4")
    if not _weasyprint_available():
        raise RuntimeError("HTML 转 PDF 需要 WeasyPrint，当前环境不可用")
    from weasyprint import HTML

    from ..theme_manager import build_travel_html_document

    document = build_travel_html_document(
        html_body,
        title,
        cover_data=cover_data,
        include_cover=cover,
        overrides=overrides,
        theme=theme,
        images=images,
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
