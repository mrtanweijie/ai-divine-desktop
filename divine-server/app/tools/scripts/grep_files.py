"""Content search across workspace files (grep).

两个引擎，自动选择：
1. **ripgrep 快速路径**：找到 rg 二进制（DIVINE_RG_PATH → PATH → 打包目录）
   时用 rg（C 级并行扫描，大仓库快一个量级）。用 `--no-require-git` 保证
   非 git 目录也尊重 .gitignore（与 Python 路径行为一致）。
2. **Python 兜底**：rg 不可用或执行失败（如 rust 正则不支持 lookahead）
   时，自动回退到纯 Python 实现，行为与历史版本一致。

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
  search base.
- Always skips VCS dirs and common heavy/vendored directories.
- Skips binary files and (Python engine) oversized files.
- Output is compact ripgrep-style text; structured matches go in data
  (data.engine 标记实际使用的引擎)。

``run_tool`` is the reusable in-process entrypoint (adapters call it directly
inside ``asyncio.to_thread``); ``main`` reads the stdin payload and prints the
same result dict for the standalone subprocess path.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import subprocess
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
_RG_TIMEOUT = 120


def _is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            head = handle.read(_BINARY_SNIFF)
    except OSError:
        return True
    return b"\x00" in head


def _format_match(rel: str, line: int, text: str, prefix: str) -> str:
    return f"{rel}{prefix}{line}: {text}"


# ---------------------------------------------------------------------------
# ripgrep engine
# ---------------------------------------------------------------------------


def _rg_binary() -> str | None:
    """Locate a usable ripgrep binary; None when unavailable."""
    candidates: list[Path] = []
    env_path = os.getenv("DIVINE_RG_PATH")
    if env_path:
        candidates.append(Path(env_path))
    which = shutil.which("rg")
    if which:
        candidates.append(Path(which))
    name = "rg.exe" if os.name == "nt" else "rg"
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates += [exe_dir / "_internal" / "rg" / name, exe_dir / "rg" / name]
    else:
        candidates.append(
            Path(__file__).resolve().parents[3] / "bin" / "rg" / name
        )
    for candidate in candidates:
        try:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        except OSError:
            continue
    return None


def _run_with_rg(
    rg_bin: str,
    pattern: str,
    base: Path,
    glob_filter: str | None,
    context: int,
    case_sensitive: bool,
    include_hidden: bool,
    max_results: int,
) -> dict:
    """rg 快速路径。执行错误（含 rust 正则不支持的语法）抛 RuntimeError，
    由调用方回退 Python 引擎。"""
    args = [rg_bin, "--json", "--no-messages", "--no-follow", "--no-require-git"]
    if not case_sensitive:
        args.append("-i")
    if include_hidden:
        args.append("--hidden")
    args += ["-g", "!**/.git/**"]
    for heavy in sorted(SKIP_DIR_NAMES):
        args += ["-g", f"!**/{heavy}/**"]
    if glob_filter:
        args += ["-g", glob_filter]
    args += [pattern, str(base)]

    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    matches: list[dict[str, object]] = []
    truncated = False
    searched_files = 0
    assert proc.stdout is not None
    try:
        for raw in proc.stdout:
            raw = raw.strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            kind = event.get("type")
            data = event.get("data") or {}
            if kind == "begin":
                searched_files += 1
            elif kind == "match":
                path_text = str(((data.get("path") or {}).get("text")) or "")
                rel = os.path.relpath(path_text, base).replace(os.sep, "/")
                line_number = int(data.get("line_number") or 0)
                text = str(((data.get("lines") or {}).get("text")) or "").rstrip("\n")
                matches.append({"path": rel, "line": line_number, "text": text})
                if len(matches) >= max_results:
                    truncated = True
                    break
    finally:
        if proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    # 自然结束且退出码为 2 → rg 报错（如不支持的语法），回退 Python
    if not truncated and proc.returncode not in (0, 1, None):
        raise RuntimeError(f"rg exit {proc.returncode}")

    return _render(
        matches=matches,
        truncated=truncated,
        base=base,
        context=context,
        pattern_raw=pattern,
        searched_files=searched_files,
        skipped_binary=0,
        skipped_oversized=0,
        engine="ripgrep",
    )


# ---------------------------------------------------------------------------
# Python engine（历史实现，rg 不可用/失败时的兜底）
# ---------------------------------------------------------------------------


def _run_with_python(
    regex,
    workspace: Path,
    base: Path,
    glob_filter: str | None,
    context: int,
    include_hidden: bool,
    max_results: int,
    pattern_raw: str,
) -> dict:
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

    return _render(
        matches=matches,
        truncated=truncated,
        base=base,
        context=context,
        pattern_raw=pattern_raw,
        searched_files=searched_files,
        skipped_binary=skipped_binary,
        skipped_oversized=skipped_oversized,
        engine="python",
    )


def _render(
    matches: list[dict[str, object]],
    truncated: bool,
    base: Path,
    context: int,
    pattern_raw: str,
    searched_files: int,
    skipped_binary: int,
    skipped_oversized: int,
    engine: str,
) -> dict:
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
        + (f"，截断至 {total} 条" if truncated else "")
        + f"，引擎 {engine}"
        + "）"
    )
    body = "\n".join(lines_out)
    content = header + "\n" + body
    if len(content) > _MAX_OUTPUT_CHARS:
        content = content[:_MAX_OUTPUT_CHARS] + "\n...(输出已截断)"
        truncated = True

    return {
        "success": True,
        "message": (
            f"找到 {total} 处匹配"
            + ("，已截断" if truncated else "")
        ),
        "content": content,
        "data": {
            "pattern": pattern_raw,
            "total": total,
            "truncated": truncated,
            "engine": engine,
            "searched_files": searched_files,
            "skipped_binary": skipped_binary,
            "skipped_oversized": skipped_oversized,
            "matches": matches[:500],
        },
    }


def run_tool(workspace: Path, params: dict) -> dict:
    """Run the grep search and return the tool result dict."""
    pattern_raw = str(params.get("pattern") or "")
    if not pattern_raw.strip():
        return {"success": False, "message": "pattern 不能为空"}
    try:
        flags = 0 if params.get("case_sensitive") else re.IGNORECASE
        regex = re.compile(pattern_raw, flags)
    except re.error as exc:
        return {"success": False, "message": f"正则表达式无效: {exc}"}

    raw_path = str(params.get("path") or "").strip()
    base = workspace
    if raw_path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = workspace / candidate
        base = candidate.resolve()
    if not base.is_dir():
        return {"success": False, "message": f"搜索目录不存在: {base}"}

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
    case_sensitive = bool(params.get("case_sensitive"))

    rg_bin = _rg_binary()
    if rg_bin is not None:
        try:
            return _run_with_rg(
                rg_bin=rg_bin,
                pattern=pattern_raw,
                base=base,
                glob_filter=glob_filter,
                context=context,
                case_sensitive=case_sensitive,
                include_hidden=include_hidden,
                max_results=max_results,
            )
        except Exception:  # noqa: BLE001 — rg 失败一律回退 Python 引擎
            pass

    return _run_with_python(
        regex=regex,
        workspace=workspace,
        base=base,
        glob_filter=glob_filter,
        context=context,
        include_hidden=include_hidden,
        max_results=max_results,
        pattern_raw=pattern_raw,
    )


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    params = data.get("params") or {}
    print(json.dumps(run_tool(workspace, params), ensure_ascii=False))


if __name__ == "__main__":
    main()
