import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.tools.scripts.file_utils import unique_output_path  # noqa: E402


_DIAGRAM_STARTS = (
    "flowchart",
    "graph ",
    "sequenceDiagram",
    "stateDiagram",
    "classDiagram",
    "erDiagram",
    "gantt",
    "journey",
    "pie",
    "quadrantChart",
    "requirementDiagram",
    "gitGraph",
    "mindmap",
    "timeline",
    "zenuml",
    "sankey-beta",
    "xychart-beta",
    "block-beta",
    "packet-beta",
    "kanban",
    "architecture-beta",
    "radar",
    "c4",
)

MAX_CONTENT_CHARS = 20000


def safe_name(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "_", name).strip("._")
    if not cleaned:
        cleaned = fallback
    if not cleaned.endswith(".mmd"):
        cleaned += ".mmd"
    return cleaned


def _strip_fence(content: str) -> str:
    lines = content.strip().splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _diagram_kind(content: str) -> str:
    for line in content.splitlines()[:6]:
        stripped = line.strip()
        if not stripped or stripped.startswith("%%"):
            continue
        lowered = stripped.lower()
        for start in _DIAGRAM_STARTS:
            if lowered.startswith(start):
                return start.rstrip()
    return ""


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    output_root = Path(data.get("output_dir") or workspace).resolve()
    params = data.get("params") or {}

    content = _strip_fence(params.get("content") or "")
    if not content:
        print(
            json.dumps(
                {"success": False, "message": "Mermaid 内容不能为空"},
                ensure_ascii=False,
            )
        )
        return
    if len(content) > MAX_CONTENT_CHARS:
        print(
            json.dumps(
                {
                    "success": False,
                    "message": f"Mermaid 内容超过 {MAX_CONTENT_CHARS} 字符限制",
                },
                ensure_ascii=False,
            )
        )
        return
    if not _diagram_kind(content):
        print(
            json.dumps(
                {"success": False, "message": "内容不是可识别的 Mermaid 图"},
                ensure_ascii=False,
            )
        )
        return

    title = str(params.get("title") or "流程图").strip()
    output_dir = output_root / "diagrams"
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
                    {"success": False, "message": f"保存路径越界: {output_dir}"},
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
    file_name = str(params.get("file_name") or "").strip() or title
    output_path = unique_output_path(output_dir, file_name, "流程图", ".mmd")
    output_path.write_text(content + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "success": True,
                "message": "Mermaid 图保存完成",
                "file_name": output_path.name,
                "filepath": str(output_path),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
