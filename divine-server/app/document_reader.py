from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("divine.document_reader")

# Formats anydoc converts to GitHub-Flavored Markdown (tables/headings/lists
# preserved). Unknown or unsupported extensions keep going to the legacy
# plain-text readers below.
ANYDOC_EXTENSIONS = {
    # Word
    ".doc", ".docx", ".docm",
    # PowerPoint
    ".ppt", ".pps", ".pot", ".pptx", ".pptm", ".ppsx", ".ppsm",
    # Excel
    ".xls", ".xlsx", ".xlsm", ".xlsb",
    # OpenDocument
    ".odt", ".ods", ".odp",
    # Rich Text / EPUB / CSV / PDF
    ".rtf", ".epub", ".csv", ".pdf",
}


def read_file_text(path: Path) -> str:
    """Return document content as text (GFM Markdown when anydoc handles it).

    anydoc is the preferred reader for its supported formats; on any failure
    (image-only PDF, encrypted file, missing install, ...) we fall back to the
    legacy per-format readers so file reading never breaks.
    """
    ext = path.suffix.lower()
    if ext in ANYDOC_EXTENSIONS:
        try:
            markdown = _read_anydoc(path)
        except Exception as exc:  # noqa: BLE001 - anydoc failure must not break reading
            logger.debug("anydoc conversion failed for %s (%s); falling back", path, type(exc).__name__)
            markdown = ""
        if markdown.strip():
            return markdown
    return _read_file_text_legacy(path)


def _read_anydoc(path: Path) -> str:
    # Imported lazily: firecrawl-anydoc is a Rust native wheel; a missing or
    # broken install degrades gracefully to the legacy readers.
    import anydoc

    return anydoc.to_markdown(str(path))


def _read_file_text_legacy(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in (".xlsx", ".xlsm"):
        return _read_excel(path)
    if ext == ".docx":
        return _read_docx(path)
    if ext in (".pptx", ".pptm"):
        return _read_pptx(path)
    # 纯文本类（.txt/.md/代码文件…）直接读。
    # 原先走 TextLoader，但它只是一层薄封装（读文件 + 包成 Document），
    # 而 `import langchain_community.document_loaders` 实测要 ~3s —— 每个
    # 读文件类工具（read_file 等）启动时都要白付这笔开销。
    if ext not in (".csv", ".pdf"):
        return path.read_text(encoding="utf-8")
    # csv / pdf 仍需 langchain loader：延迟导入，让不碰这两种格式的调用完全不加载它
    from langchain_community.document_loaders import CSVLoader, PyPDFLoader

    loader = CSVLoader(str(path)) if ext == ".csv" else PyPDFLoader(str(path))
    docs = loader.load()
    return "\n\n".join(doc.page_content for doc in docs)


def _read_docx(path: Path) -> str:
    from docx import Document

    document = Document(str(path))
    parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            parts.append("\t".join(cell.text.strip() for cell in row.cells))
    return "\n\n".join(parts)


def _read_excel(path: Path) -> str:
    from openpyxl import load_workbook

    workbook = load_workbook(str(path), read_only=True, data_only=True)
    parts: list[str] = []
    try:
        for sheet in workbook.worksheets:
            rows = []
            for row in sheet.iter_rows(values_only=True):
                cells = ["" if cell is None else str(cell) for cell in row]
                rows.append("\t".join(cells))
            parts.append(f"Sheet: {sheet.title}\n" + "\n".join(rows))
    finally:
        workbook.close()
    return "\n\n".join(parts)


def _collect_shape_text(shape, texts: list[str]) -> None:
    if getattr(shape, "has_text_frame", False):
        text = "\n".join(
            paragraph.text.strip()
            for paragraph in shape.text_frame.paragraphs
            if paragraph.text.strip()
        )
        if text:
            texts.append(text)
    if getattr(shape, "has_table", False):
        for row in shape.table.rows:
            texts.append(
                "\t".join(cell.text.strip() for cell in row.cells)
            )
    if getattr(shape, "shape_type", None) is not None:
        from pptx.enum.shapes import MSO_SHAPE_TYPE

        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            for child in shape.shapes:
                _collect_shape_text(child, texts)


def _read_pptx(path: Path) -> str:
    from pptx import Presentation

    presentation = Presentation(str(path))
    parts: list[str] = []
    for index, slide in enumerate(presentation.slides, start=1):
        texts: list[str] = []
        for shape in slide.shapes:
            _collect_shape_text(shape, texts)
        if texts:
            parts.append(f"Slide {index}\n" + "\n".join(texts))
    return "\n\n".join(parts)
