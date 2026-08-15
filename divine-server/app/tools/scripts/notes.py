import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.tools.scripts.file_utils import unique_output_path  # noqa: E402


def safe_name(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "_", name).strip("._")
    if not cleaned:
        cleaned = fallback
    if not cleaned.endswith(".md"):
        cleaned += ".md"
    return cleaned


def derive_title(title: str, content: str) -> str:
    candidate = (title or "").strip()
    if candidate:
        return candidate
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            stripped = stripped.lstrip("#").strip()
        if stripped:
            return stripped[:60]
    return "未命名笔记"


def _clean_content(content: str) -> str:
    lines = content.splitlines()
    while lines:
        stripped = lines[0].strip()
        if not stripped.startswith("# "):
            break
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines).strip()


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    output_root = Path(data.get("output_dir") or workspace).resolve()
    params = data.get("params") or {}
    content = params.get("content") or ""
    title = derive_title(params.get("title") or "", content)
    output_dir = output_root / "notes"
    raw_path = str(params.get("path") or "").strip()
    if raw_path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = workspace / candidate
        output_dir = candidate.resolve()
        try:
            output_dir.relative_to(workspace)
        except ValueError:
            print(
                json.dumps(
                    {
                        "success": False,
                        "message": f"保存路径越界: {output_dir}",
                    },
                    ensure_ascii=False,
                )
            )
            return
    if output_dir.exists() and not output_dir.is_dir():
        print(
            json.dumps(
                {"success": False, "message": f"保存路径不是目录: {output_dir}"},
                ensure_ascii=False,
            )
        )
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = unique_output_path(output_dir, title, "笔记", ".md")

    cleaned = _clean_content(content)
    text = f"# {title}\n\n{cleaned}\n" if cleaned else f"# {title}\n"
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
