import json
import os
import sys
from pathlib import Path


def run_tool(workspace: Path, params: dict) -> dict:
    """Search workspace files by name/path keyword and return the result dict.

    Callable both from the CLI entrypoint and in-process (adapters run this
    directly inside ``asyncio.to_thread``).
    """
    query = str(params.get("query") or "").strip()
    raw_path = str(params.get("path") or "").strip()

    base = workspace
    if raw_path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = workspace / candidate
        base = candidate.resolve()
        try:
            base.relative_to(workspace)
        except ValueError:
            return {"success": False, "message": f"搜索路径越界: {base}"}
    if not base.is_dir():
        return {"success": False, "message": f"搜索目录不存在: {base}"}

    files = []
    max_results = 300
    lower_query = query.lower()
    for root, dirs, names in os.walk(base):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        relative = Path(root).relative_to(base)
        if len(relative.parts) >= 6:
            dirs[:] = []
        for name in sorted(names):
            if name.startswith("."):
                continue
            path = Path(root) / name
            if not path.is_file():
                continue
            rel = path.relative_to(workspace).as_posix()
            if lower_query and (
                lower_query not in rel.lower()
                and lower_query not in name.lower()
            ):
                continue
            files.append(
                {
                    "path": rel,
                    "name": name,
                    "size": path.stat().st_size,
                }
            )
            if len(files) >= max_results:
                break
        if len(files) >= max_results:
            break

    return {
        "success": True,
        "message": f"找到 {len(files)} 个文件",
        "content": json.dumps(files, ensure_ascii=False),
    }


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    params = data.get("params") or {}
    print(json.dumps(run_tool(workspace, params), ensure_ascii=False))


if __name__ == "__main__":
    main()
