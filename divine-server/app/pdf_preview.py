"""Render PDF pages to PNG data URLs for inline preview.

Uses PyMuPDF (fitz). Rendering pages to images avoids the webview's built-in
PDF viewer (and its oversized native zoom toolbar); the frontend shows plain
page images instead.
"""

from __future__ import annotations

import base64
from pathlib import Path

MAX_PDF_PREVIEW_PAGES = 12
MAX_PDF_PREVIEW_BYTES = 30 * 1024 * 1024
# 2.5x of the 72dpi base (180dpi): page images stay crisp when scaled up to
# panel width on retina displays.
PDF_RENDER_DPI = 180


def render_pdf_pages(path: Path) -> list[str]:
    """Return up to MAX_PDF_PREVIEW_PAGES pages as PNG data URLs."""
    try:
        import pymupdf as fitz  # PyMuPDF >= 1.24
    except ImportError:  # pragma: no cover - older PyMuPDF
        import fitz  # type: ignore[no-redef]

    doc = fitz.open(str(path))
    try:
        pages: list[str] = []
        for page in doc:
            pix = page.get_pixmap(dpi=PDF_RENDER_DPI)
            data = pix.tobytes("png")
            pages.append(
                "data:image/png;base64," + base64.b64encode(data).decode("ascii")
            )
            if len(pages) >= MAX_PDF_PREVIEW_PAGES:
                break
        return pages
    finally:
        doc.close()
