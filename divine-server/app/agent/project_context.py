"""Project skeleton auto-injection for the agent prompt.

When the session workspace looks like a software project, inject a compact
overview (manifest fields + a small gitignore-aware directory tree) so the
agent does not start from zero on every turn. The block is cached per session
and refreshed after a short TTL or when key files change.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from ..tools.gitignore import SKIP_DIR_NAMES, load_gitignore_rules, is_ignored

logger = logging.getLogger("divine.agent.project_context")

_MAX_BLOCK_CHARS = 1800
_CACHE_TTL = 300  # seconds
_TREE_DEPTH = 2
_TREE_MAX_ENTRIES = 60

_MANIFEST_NAMES = (
    "README.md",
    "README",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "Cargo.toml",
    "go.mod",
)


def _looks_like_project(workspace: Path) -> bool:
    if not workspace.is_dir():
        return False
    if (workspace / ".git").exists():
        return True
    return any((workspace / name).is_file() for name in _MANIFEST_NAMES)


def _readme_summary(workspace: Path) -> str | None:
    for name in ("README.md", "README"):
        path = workspace / name
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return None
        kept: list[str] = []
        for line in lines[:60]:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("!["):  # skip markdown images/badges
                continue
            kept.append(stripped)
            if len(kept) >= 6:
                break
        summary = " / ".join(kept)[:800]
        return summary if summary else None
    return None


def _package_json_summary(workspace: Path) -> str | None:
    path = workspace / "package.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None
    parts: list[str] = []
    name = str(data.get("name") or "")
    if name:
        parts.append(f"name={name}")
    version = str(data.get("version") or "")
    if version:
        parts.append(f"version={version}")
    scripts = data.get("scripts")
    if isinstance(scripts, dict) and scripts:
        script_lines = ", ".join(
            f"{key}" for key in list(scripts.keys())[:12]
        )
        parts.append(f"scripts=[{script_lines}]")
    deps = data.get("dependencies")
    dev_deps = data.get("devDependencies")
    if isinstance(deps, dict) and deps:
        parts.append(f"dependencies={len(deps)}")
    if isinstance(dev_deps, dict) and dev_deps:
        parts.append(f"devDependencies={len(dev_deps)}")
    if not parts:
        return None
    return "package.json: " + "，".join(parts)[:600]


def _pyproject_summary(workspace: Path) -> str | None:
    path = workspace / "pyproject.toml"
    if not path.is_file():
        return None
    try:
        import tomllib

        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError, ImportError):
        return None
    parts: list[str] = []
    project = data.get("project") or {}
    name = str(project.get("name") or "")
    if name:
        parts.append(f"name={name}")
    version = str(project.get("version") or "")
    if version:
        parts.append(f"version={version}")
    deps = project.get("dependencies")
    if isinstance(deps, list) and deps:
        parts.append(f"dependencies={len(deps)}")
    poetry = data.get("tool", {}).get("poetry", {})
    if not parts and poetry:
        pname = str(poetry.get("name") or "")
        if pname:
            parts.append(f"name={pname}")
        pdeps = poetry.get("dependencies")
        if isinstance(pdeps, dict) and pdeps:
            parts.append(f"dependencies={len(pdeps)}")
    if not parts:
        return None
    return "pyproject.toml: " + "，".join(parts)[:400]


def _requirements_summary(workspace: Path) -> str | None:
    path = workspace / "requirements.txt"
    if not path.is_file():
        return None
    try:
        lines = [
            line.strip()
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    except OSError:
        return None
    if not lines:
        return None
    shown = lines[:8]
    return "requirements.txt: " + ", ".join(shown)[:400]


def _project_tree(workspace: Path) -> str | None:
    """Compact gitignore-aware tree (depth 2, capped)."""
    workspace = workspace.resolve()
    matchers, matcher_dirs = load_gitignore_rules(workspace, workspace)
    lines: list[str] = []
    count = 0

    def walk(node: Path, rel: str, depth: int) -> None:
        nonlocal count
        if count >= _TREE_MAX_ENTRIES:
            return
        try:
            children = sorted(
                (entry for entry in node.iterdir()),
                key=lambda p: p.name.lower(),
            )
        except OSError:
            return
        for child in children:
            if count >= _TREE_MAX_ENTRIES:
                return
            name = child.name
            if name in SKIP_DIR_NAMES or name.startswith("."):
                continue
            child_rel = f"{rel}/{name}" if rel else name
            if is_ignored(matchers, matcher_dirs, workspace, child_rel, child.is_dir()):
                continue
            if child.is_dir():
                lines.append(f"{child_rel}/")
                count += 1
                if depth > 0:
                    walk(child, child_rel, depth - 1)
            else:
                lines.append(child_rel)
                count += 1

    walk(workspace, "", _TREE_DEPTH)
    if not lines:
        return None
    return "目录结构（已忽略 .gitignore / node_modules 等）：\n" + "\n".join(lines)


def build_project_context(workspace: Any, session_id: str) -> str | None:
    """Build the project overview block for the prompt; cached per session."""
    ws = Path(workspace).resolve()
    if not _looks_like_project(ws):
        return None
    cache = _CACHE.get(session_id)
    fingerprint = _fingerprint(ws)
    now = time.time()
    if (
        cache
        and cache["fingerprint"] == fingerprint
        and now - cache["ts"] < _CACHE_TTL
    ):
        return cache["text"]
    text = _build_block(ws)
    _CACHE[session_id] = {
        "ts": now,
        "fingerprint": fingerprint,
        "text": text,
    }
    return text


def _fingerprint(workspace: Path) -> tuple[int, int]:
    """Cheap change detector: newest mtime among key files + dir mtime."""
    newest = 0
    for name in _MANIFEST_NAMES:
        try:
            newest = max(newest, (workspace / name).stat().st_mtime_ns)
        except OSError:
            pass
    try:
        newest = max(newest, workspace.stat().st_mtime_ns)
    except OSError:
        pass
    return newest, workspace.stat().st_ino if workspace.exists() else 0


def _build_block(workspace: Path) -> str | None:
    parts: list[str] = []
    readme = _readme_summary(workspace)
    if readme:
        parts.append(f"README：{readme}")
    for summary in (
        _package_json_summary(workspace),
        _pyproject_summary(workspace),
        _requirements_summary(workspace),
    ):
        if summary:
            parts.append(summary)
    tree = _project_tree(workspace)
    if tree:
        parts.append(tree)
    if not parts:
        return None
    header = "## 项目概况（自动注入，供开发任务参考；改动后文件以实际内容为准）"
    block = header + "\n" + "\n".join(parts)
    if len(block) > _MAX_BLOCK_CHARS:
        block = block[:_MAX_BLOCK_CHARS] + "\n...(项目概况已截断)"
    return block


_CACHE: dict[str, dict[str, Any]] = {}


def clear_project_context_cache(session_id: str | None = None) -> None:
    if session_id is None:
        _CACHE.clear()
    else:
        _CACHE.pop(session_id, None)
