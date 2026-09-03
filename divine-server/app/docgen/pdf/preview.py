"""Render PDF pages to PNG data URLs for inline preview.

Uses PyMuPDF (fitz). Rendering pages to images avoids the webview's built-in
PDF viewer (and its oversized native zoom toolbar); the frontend shows plain
page images instead.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

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

    try:
        doc = fitz.open(str(path))
    except Exception as exc:
        # fitz.open 阶段解压失败（zlib.error 或 PyMuPDF 包装的 RuntimeError），
        # 用 bytes 重试一次
        logger.warning("fitz.open error, retrying from bytes: %s", exc)
        try:
            doc = fitz.open(stream=path.read_bytes(), filetype="pdf")
        except Exception:
            raise RuntimeError(f"PDF 文件损坏或格式不支持: {exc}") from exc
    try:
        pages: list[str] = []
        for i, page in enumerate(doc):
            try:
                pix = page.get_pixmap(dpi=PDF_RENDER_DPI)
            except Exception as exc:
                # PyMuPDF 某些压缩流解压失败时降级为低 DPI 渲染
                logger.warning("Page %d render error at default DPI, retrying at 72dpi: %s", i, exc)
                try:
                    pix = page.get_pixmap(dpi=72)
                except Exception:
                    logger.warning("Page %d also failed at 72dpi, skipping", i)
                    continue
            data = pix.tobytes("png")
            pages.append(
                "data:image/png;base64," + base64.b64encode(data).decode("ascii")
            )
            if len(pages) >= MAX_PDF_PREVIEW_PAGES:
                break
        return pages
    finally:
        doc.close()
