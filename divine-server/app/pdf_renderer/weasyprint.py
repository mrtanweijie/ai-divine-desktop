"""WeasyPrint renderer with lazy availability detection."""

from __future__ import annotations

import contextlib
import html as html_lib
import importlib.util
import io
from pathlib import Path
from typing import Any

from .markdown import _build_toc, _prepare_markdown

_WEASYPRINT_OK: bool | None = None

def _weasyprint_available() -> bool:
    global _WEASYPRINT_OK
    if _WEASYPRINT_OK is not None:
        return _WEASYPRINT_OK
    if importlib.util.find_spec("weasyprint") is None:
        _WEASYPRINT_OK = False
        return False
    # cffi may resolve system libraries through the process environment even
    # when common paths cannot be found, so always attempt the import once.
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        try:
            import weasyprint  # noqa: F401

            _WEASYPRINT_OK = True
        except Exception:
            _WEASYPRINT_OK = False
    return _WEASYPRINT_OK

def _render_with_weasyprint(
    markdown: str,
    output: Path,
    title: str,
    style: str,
    color_scheme: str,
    paper_size: str,
    cover: bool,
    toc: bool,
    base_dir: Path | None = None,
    theme: str = "universal",
) -> None:
    from weasyprint import HTML

    import markdown as markdown_lib

    from ..pdf_theme_manager import build_cover_html, load_theme_css

    css = load_theme_css(theme, paper_size=paper_size)
    prepared = _prepare_markdown(markdown)
    body = markdown_lib.markdown(
        prepared,
        extensions=["extra", "tables", "fenced_code", "sane_lists"],
    )
    cover_html = ""
    if cover:
        cover_html = build_cover_html(
            theme,
            html_lib.escape(title),
            "AI Divine 生成文档",
        )
    toc_html = _build_toc(markdown) if toc else ""
    document = (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<style>{css}</style></head><body>"
        "<div class=\"header\">"
        f"<span class=\"doc-title\">{html_lib.escape(title)}</span>"
        "</div>"
        f"{cover_html}{toc_html}{body}</body></html>"
    )
    kwargs: dict[str, Any] = {"string": document}
    if base_dir is not None:
        kwargs["base_url"] = str(base_dir)
    HTML(**kwargs).write_pdf(str(output), presentational_hints=True)
