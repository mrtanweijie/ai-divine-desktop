"""pdf_to_word 脚本：把 PDF 的文本内容转换为可编辑的 Word 文档（方案 B）。

链路：read_file_text（anydoc→GFM Markdown，失败回退 PyPDFLoader）
→ markdown_to_document（复用 word_document 的渲染管线）→ .docx。
零新增依赖；保真度与 read_file 的 PDF 读取一致（标题/表格/列表保留，
复杂排版可能丢失）。扫描件无文本层 → 明确失败（OCR 不在支持范围）。

输出：workspace/documents/<原名>.docx（自动避让重名）。原 PDF 只读不动。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from docx import Document  # noqa: E402

from app.document_reader import read_file_text  # noqa: E402
from app.docgen.word.markdown import markdown_to_document  # noqa: E402
from app.docgen.word.themes import add_footer, apply_word_theme  # noqa: E402
from app.tools.office_files import OfficePathError, resolve_office_path  # noqa: E402
from app.tools.scripts.file_utils import unique_output_path  # noqa: E402
from app.tools.scripts.word_document import verify_document  # noqa: E402

_MIN_TEXT_CHARS = 20


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"])
    output_root = Path(data.get("output_dir") or workspace)
    params = data.get("params") or {}
    theme = str(params.get("theme") or params.get("style") or "universal").strip()
    title = str(params.get("title") or "").strip()

    try:
        source = resolve_office_path(workspace, str(params.get("path") or ""), kind="pdf")
    except OfficePathError as exc:
        print(json.dumps({"success": False, "message": str(exc)}, ensure_ascii=False))
        return

    markdown = read_file_text(source)
    chars = len(markdown.strip())
    if chars < _MIN_TEXT_CHARS:
        print(
            json.dumps(
                {
                    "success": False,
                    "message": (
                        "该 PDF 没有可提取的文本层（可能是扫描件或纯图片版），"
                        "无法转换为 Word；OCR 不在支持范围"
                    ),
                },
                ensure_ascii=False,
            )
        )
        return

    if not title:
        title = source.stem

    output_dir = output_root / "documents"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = unique_output_path(output_dir, title, "转换文档", ".docx")

    warnings: list[str] = []
    try:
        document = Document()
        apply_word_theme(document, theme)
        counts = markdown_to_document(document, markdown, workspace, theme)
        add_footer(document, theme)
        document.save(str(output_path))
    except Exception as exc:  # noqa: BLE001
        if output_path.exists():
            output_path.unlink()
        print(
            json.dumps(
                {"success": False, "message": f"转换失败: {exc}"}, ensure_ascii=False
            )
        )
        return

    warnings.extend(verify_document(output_path, {}))

    import pymupdf  # noqa: PLC0415

    pages = 0
    try:
        pages = pymupdf.open(str(source)).page_count
    except Exception:  # noqa: BLE001 — 页数仅用于报告
        pages = 0

    print(
        json.dumps(
            {
                "success": True,
                "message": f"PDF 转 Word 完成（{pages} 页 / {chars} 字符）",
                "file_name": output_path.name,
                "filepath": str(output_path),
                "content": (
                    f"已将 {source.name}（{pages} 页）转换为可编辑 Word："
                    f"{output_path.name}。复杂排版可能存在差异，建议打开检查。"
                ),
                "data": {
                    "source_path": str(source),
                    "pages": pages,
                    "chars": chars,
                    "theme": theme,
                    **(counts or {}),
                    "warnings": warnings,
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
