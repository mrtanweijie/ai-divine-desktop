import json
import re
import sys
import time
from pathlib import Path

from docx import Document
from docx.shared import Pt

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.tools.scripts.file_utils import unique_output_path  # noqa: E402
from app.word_themes import add_title_page, apply_word_theme  # noqa: E402


def safe_name(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "_", name).strip("._")
    if not cleaned:
        cleaned = fallback
    if not cleaned.endswith(".docx"):
        cleaned += ".docx"
    return cleaned


def _heading_level(section_type: str) -> int:
    kind = (section_type or "").lower()
    if kind in ("h1", "heading1", "title", "chapter"):
        return 1
    if kind in ("h3", "heading3", "subheading"):
        return 3
    return 2


def add_sections(document: Document, sections: list[dict]) -> None:
    for section in sections or []:
        section_type = str(section.get("type") or "").lower()
        content = str(
            section.get("content")
            or section.get("body")
            or section.get("text")
            or ""
        )
        heading = str(
            section.get("heading")
            or section.get("title")
            or ""
        )

        if section_type in ("heading", "h1", "h2", "h3", "heading1", "heading3", "subheading", "chapter", "title"):
            document.add_heading(
                content or heading,
                level=_heading_level(section_type),
            )
            continue

        if section_type in ("bullet_list", "list", "bullets"):
            for line in content.splitlines():
                if line.strip():
                    document.add_paragraph(line.strip(), style="List Bullet")
            continue

        if heading:
            document.add_heading(heading, level=2)
        for line in content.splitlines():
            document.add_paragraph(line)


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"])
    output_root = Path(data.get("output_dir") or workspace)
    params = data.get("params") or {}
    title = params.get("title") or "未命名文档"
    sections = params.get("sections") or []
    theme = str(params.get("theme") or params.get("style") or "universal").strip()
    output_dir = output_root / "documents"
    raw_path = str(params.get("path") or "").strip()
    if raw_path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = workspace / candidate
        output_dir = candidate.resolve()
        try:
            output_dir.relative_to(workspace.resolve())
        except ValueError:
            print(
                json.dumps(
                    {"success": False, "message": f"保存路径越界: {output_dir}"},
                    ensure_ascii=False,
                )
            )
            return
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = unique_output_path(output_dir, title, "文档", ".docx")

    for attempt in range(2):
        try:
            document = Document()
            apply_word_theme(document, theme)
            add_title_page(document, title, theme)
            add_sections(document, sections)
            if not sections:
                document.add_paragraph("此文档由 AI Divine 自动生成。")
            footer = document.add_paragraph()
            footer_run = footer.add_run("AI Divine · Word Document")
            footer_run.font.size = Pt(8)
            document.save(output_path)
            break
        except Exception:
            if output_path.exists():
                output_path.unlink()
            if attempt == 1:
                raise
            time.sleep(1)

    print(
        json.dumps(
            {
                "success": True,
                "message": "Word 文档生成完成",
                "file_name": output_path.name,
                "filepath": str(output_path),
                "data": {"theme": theme},
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
