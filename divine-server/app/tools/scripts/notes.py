import json
import re
import sys
from pathlib import Path


def safe_name(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "_", name).strip("._")
    if not cleaned:
        cleaned = fallback
    if not cleaned.endswith(".md"):
        cleaned += ".md"
    return cleaned


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"])
    params = data.get("params") or {}
    title = params.get("title") or "未命名笔记"
    content = params.get("content") or ""
    output_dir = workspace / "notes"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / safe_name(title, "笔记")

    text = f"# {title}\n\n{content}\n"
    output_path.write_text(text, encoding="utf-8")
    print(
        json.dumps(
            {
                "success": True,
                "message": "Markdown 笔记生成完成",
                "file_name": output_path.name,
                "filepath": str(output_path),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
