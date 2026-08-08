from pathlib import Path

from langchain_community.document_loaders import (
    CSVLoader,
    PyPDFLoader,
    TextLoader,
)


def read_file_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".csv":
        loader = CSVLoader(str(path))
    elif ext in (".xlsx", ".xlsm"):
        return _read_excel(path)
    elif ext == ".docx":
        return _read_docx(path)
    elif ext == ".pdf":
        loader = PyPDFLoader(str(path))
    else:
        loader = TextLoader(str(path), encoding="utf-8")
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
