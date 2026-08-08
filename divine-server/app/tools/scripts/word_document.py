import json
import re
import sys
from pathlib import Path

from docx import Document


def safe_name(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "_", name).strip("._")
    if not cleaned:
        cleaned = fallback
    if not cleaned.endswith(".docx"):
        cleaned += ".docx"
    return cleaned


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"])
    params = data.get("params") or {}
    title = params.get("title") or "未命名文档"
    sections = params.get("sections") or []
    output_dir = workspace / "documents"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / safe_name(title, "文档")

    document = Document()
    document.add_heading(title, level=0)
    for section in sections:
        heading = section.get("heading") or ""
        body = section.get("body") or ""
        if heading:
            document.add_heading(heading, level=1)
        for paragraph in body.splitlines():
            document.add_paragraph(paragraph)
    if not sections:
        document.add_paragraph("此文档由 AI Workspace 自动生成。")
    document.save(output_path)

    print(
        json.dumps(
            {
                "success": True,
                "message": "Word 文档生成完成",
                "file_name": output_path.name,
                "filepath": str(output_path),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
