import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.tools.gitignore import (  # noqa: E402
    SKIP_DIR_NAMES,
    load_gitignore_rules,
    is_ignored,
)


def _relative(base: Path, path: Path) -> str:
    try:
        return path.relative_to(base).as_posix() or "."
    except ValueError:
        return str(path)


def _build(
    base: Path,
    node: Path,
    depth: int,
    show_hidden: bool,
    show_sizes: bool,
    limit: int,
    matchers,
    matcher_dirs,
):
    entries = []
    truncated = False
    try:
        children = sorted(
            os.scandir(node), key=lambda entry: entry.name.lower()
        )
    except OSError:
        return entries, False
    for child in children:
        if len(entries) >= limit:
            truncated = True
            break
        if child.name in SKIP_DIR_NAMES:
            continue
        if child.name.startswith(".") and not show_hidden:
            continue
        rel = _relative(base, Path(child.path))
        child_path = Path(child.path)
        if child.is_dir(follow_symlinks=False):
            if is_ignored(matchers, matcher_dirs, base, rel, True):
                continue
            entry = {
                "path": rel,
                "type": "dir",
            }
            if depth > 0:
                child_entries, child_truncated = _build(
                    base,
                    child_path,
                    depth - 1,
                    show_hidden,
                    show_sizes,
                    limit,
                    matchers,
                    matcher_dirs,
                )
                entry["children"] = child_entries
                truncated = truncated or child_truncated
            entries.append(entry)
        else:
            if is_ignored(matchers, matcher_dirs, base, rel, False):
                continue
            entry = {
                "path": rel,
                "type": "file",
            }
            if show_sizes:
                try:
                    entry["size"] = child_path.stat().st_size
                except OSError:
                    entry["size"] = None
            entries.append(entry)
    return entries, truncated


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    params = data.get("params") or {}
    raw_path = str(params.get("path") or "").strip()
    base = workspace
    if raw_path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = workspace / candidate
        base = candidate.resolve()
    if not base.is_dir():
        print(json.dumps({"success": False, "message": f"目录不存在: {base}"}))
        return

    try:
        depth = int(params.get("depth") or 3)
    except (TypeError, ValueError):
        depth = 3
    depth = max(0, min(6, depth))
    try:
        limit = int(params.get("max_entries") or 200)
    except (TypeError, ValueError):
        limit = 200
    limit = max(1, min(500, limit))
    show_hidden = bool(params.get("show_hidden"))
    show_sizes = bool(params.get("show_sizes"))

    matchers, matcher_dirs = load_gitignore_rules(workspace, base)
    entries, truncated = _build(
        base,
        base,
        depth,
        show_hidden,
        show_sizes,
        limit,
        matchers,
        matcher_dirs,
    )
    print(
        json.dumps(
            {
                "success": True,
                "message": f"目录扫描完成，返回 {len(entries)} 个顶层条目",
                "content": json.dumps(
                    {
                        "root": str(base),
                        "truncated": truncated,
                        "tree": entries,
                    },
                    ensure_ascii=False,
                ),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
