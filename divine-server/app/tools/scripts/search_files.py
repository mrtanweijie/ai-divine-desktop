import json
import os
import sys
from pathlib import Path


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    params = data.get("params") or {}
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
            print(
                json.dumps(
                    {
                        "success": False,
                        "message": f"搜索路径越界: {base}",
                    },
                    ensure_ascii=False,
                )
            )
            return
    if not base.is_dir():
        print(
            json.dumps(
                {"success": False, "message": f"搜索目录不存在: {base}"},
                ensure_ascii=False,
            )
        )
        return

    files = []
    max_results = 300
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
            lower_query = query.lower()
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

    print(
        json.dumps(
            {
                "success": True,
                "message": f"找到 {len(files)} 个文件",
                "content": json.dumps(files, ensure_ascii=False),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
