"""Content search across workspace files (grep).

Reads JSON from stdin with params:
- pattern (required): regular expression to search for
- path: relative directory to search in (default: workspace root)
- glob: optional fnmatch filter applied to relative paths / basenames
- context: number of context lines before/after each match (default 0)
- case_sensitive: default False (case-insensitive)
- include_hidden: default False (skip dotfiles/dot-dirs)
- max_results: default 200, capped at 500

Behavior:
- Respects .gitignore rules found from the workspace root down to the
  search base (simple approximation: fnmatch patterns, negation, dir-only).
- Always skips VCS dirs and common heavy/vendored directories.
- Skips binary files (null byte in head) and oversized files.
- Output is compact ripgrep-style text; structured matches go in data.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.tools.gitignore import (  # noqa: E402
    SKIP_DIR_NAMES,
    load_gitignore_rules,
    is_ignored,
)

_MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB
_BINARY_SNIFF = 8192
_MAX_CONTEXT = 10
_MAX_OUTPUT_CHARS = 80_000


def _is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            head = handle.read(_BINARY_SNIFF)
    except OSError:
        return True
    return b"\x00" in head


def _format_match(rel: str, line: int, text: str, prefix: str) -> str:
    return f"{rel}{prefix}{line}: {text}"


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    params = data.get("params") or {}
    pattern_raw = str(params.get("pattern") or "")
    if not pattern_raw.strip():
        print(json.dumps({"success": False, "message": "pattern 不能为空"}, ensure_ascii=False))
        return
    try:
        flags = 0 if params.get("case_sensitive") else re.IGNORECASE
        regex = re.compile(pattern_raw, flags)
    except re.error as exc:
        print(
            json.dumps(
                {"success": False, "message": f"正则表达式无效: {exc}"},
                ensure_ascii=False,
            )
        )
        return

    raw_path = str(params.get("path") or "").strip()
    base = workspace
    if raw_path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = workspace / candidate
        base = candidate.resolve()
    if not base.is_dir():
        print(json.dumps({"success": False, "message": f"搜索目录不存在: {base}"}, ensure_ascii=False))
        return

    glob_filter = str(params.get("glob") or "").strip() or None
    try:
        context = max(0, min(int(params.get("context") or 0), _MAX_CONTEXT))
    except (TypeError, ValueError):
        context = 0
    try:
        max_results = max(1, min(int(params.get("max_results") or 200), 500))
    except (TypeError, ValueError):
        max_results = 200
    include_hidden = bool(params.get("include_hidden"))

    matchers, matcher_dirs = load_gitignore_rules(workspace, base)

    matches: list[dict[str, object]] = []
    searched_files = 0
    skipped_binary = 0
    skipped_oversized = 0
    truncated = False

    for root, dirs, names in os.walk(base):
        root_path = Path(root)
        rel_root = root_path.relative_to(base).as_posix()
        rel_root = "" if rel_root == "." else rel_root

        pruned: list[str] = []
        for d in sorted(dirs):
            if d in SKIP_DIR_NAMES:
                continue
            if not include_hidden and d.startswith("."):
                continue
            child_rel = f"{rel_root}/{d}" if rel_root else d
            if is_ignored(matchers, matcher_dirs, base, child_rel, True):
                continue
            pruned.append(d)
        dirs[:] = pruned

        for name in sorted(names):
            if not include_hidden and name.startswith("."):
                continue
            rel = f"{rel_root}/{name}" if rel_root else name
            if is_ignored(matchers, matcher_dirs, base, rel, False):
                continue
            if glob_filter and not (
                fnmatch.fnmatch(rel, glob_filter)
                or fnmatch.fnmatch(name, glob_filter)
                or fnmatch.fnmatch(rel, f"**/{glob_filter}")
            ):
                continue
            path = root_path / name
            try:
                if path.is_symlink() and not path.is_file():
                    continue
                size = path.stat().st_size
            except OSError:
                continue
            if size > _MAX_FILE_SIZE:
                skipped_oversized += 1
                continue
            if _is_binary(path):
                skipped_binary += 1
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            searched_files += 1
            lines = text.splitlines()
            for lineno, line_text in enumerate(lines, start=1):
                if regex.search(line_text) is None:
                    continue
                matches.append({"path": rel, "line": lineno, "text": line_text})
                if len(matches) >= max_results:
                    truncated = True
                    break
            if len(matches) >= max_results:
                break
        if len(matches) >= max_results:
            break

    total = len(matches)
    # Build compact text output (rg-like with context groups).
    lines_out: list[str] = []
    if context > 0:
        # Group by file, render hunk blocks with context.
        by_file: dict[str, list[dict[str, object]]] = {}
        for m in matches:
            by_file.setdefault(str(m["path"]), []).append(m)
        for rel, file_matches in by_file.items():
            lines_out.append(rel)
            shown: set[tuple[int, int]] = set()  # (lineno, kind)
            # Re-read file for context lines.
            file_lines: list[str] = []
            file_path = base / rel
            try:
                file_lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                pass
            prev_end = -1
            for m in file_matches:
                center = int(m["line"])
                start = max(1, center - context)
                end = min(len(file_lines), center + context)
                if start <= prev_end:
                    start = prev_end + 1
                for ln in range(start, end + 1):
                    if ln == center:
                        lines_out.append(f"{ln}: {file_lines[ln - 1] if ln <= len(file_lines) else ''}")
                    else:
                        lines_out.append(f"{ln}- {file_lines[ln - 1] if ln <= len(file_lines) else ''}")
                prev_end = end
            lines_out.append("--")
    else:
        for m in matches:
            lines_out.append(f"{m['path']}:{m['line']}: {m['text']}")

    header = (
        f"grep_files 匹配 {total} 处（pattern={pattern_raw!r}，"
        f"搜索 {searched_files} 个文件"
        + (f"，截断至 {max_results} 条" if truncated else "")
        + "）"
    )
    body = "\n".join(lines_out)
    content = header + "\n" + body
    if len(content) > _MAX_OUTPUT_CHARS:
        content = content[:_MAX_OUTPUT_CHARS] + "\n...(输出已截断)"
        truncated = True

    print(
        json.dumps(
            {
                "success": True,
                "message": (
                    f"找到 {total} 处匹配"
                    + (f"，已截断" if truncated else "")
                ),
                "content": content,
                "data": {
                    "pattern": pattern_raw,
                    "total": total,
                    "truncated": truncated,
                    "searched_files": searched_files,
                    "skipped_binary": skipped_binary,
                    "skipped_oversized": skipped_oversized,
                    "matches": matches[:500],
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
