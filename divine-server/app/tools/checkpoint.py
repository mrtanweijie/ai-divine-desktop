"""Turn-level workspace checkpoints（P3-3b）。

每轮对话开始前对项目工作区做一次快照，供"撤销本轮 agent 改动"使用。
覆盖 git 管不到的场景：新建文件、非 git 目录。

设计要点：
- 快照存在应用数据目录（data_dir/checkpoints/<session>/<ts>/），不进工作区；
- 只收普通文件：跳过 .git/node_modules 等重目录与 gitignore 规则，单文件
  ≤512KB、总数 ≤2000、总量 ≤32MB；超限则标记 incomplete——恢复时不做
  删除（只覆盖），避免误删没进快照的文件；
- ``restore_latest`` 恢复"最近一个与当前工作区不同的快照"：同一快照状态
  会被跳过，因此连续两次 undo 相当于 undo → redo（恢复前会把当前状态
  先存为新快照，任何一步都可再撤销）；
- .git 目录永不触碰。
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path

from ..config import data_dir
from .gitignore import SKIP_DIR_NAMES, is_ignored, load_gitignore_rules

logger = logging.getLogger("divine.tools.checkpoint")

_MAX_FILE_BYTES = 512 * 1024
_MAX_TOTAL_BYTES = 32 * 1024 * 1024
_MAX_FILES = 2000
_KEEP_PER_SESSION = 5


def _checkpoints_root(session_id: str) -> Path:
    return data_dir() / "checkpoints" / session_id


def _walk_files(workspace: Path) -> list[Path]:
    """Gitignore-aware file listing (relative paths, sorted)."""
    matchers, matcher_dirs = load_gitignore_rules(workspace, workspace)
    found: list[Path] = []

    def walk(node: Path, rel: str) -> None:
        try:
            children = sorted(node.iterdir(), key=lambda p: p.name)
        except OSError:
            return
        for child in children:
            name = child.name
            if name in SKIP_DIR_NAMES or name.startswith("."):
                continue
            child_rel = f"{rel}/{name}" if rel else name
            if child.is_dir():
                if is_ignored(matchers, matcher_dirs, workspace, child_rel, True):
                    continue
                walk(child, child_rel)
            else:
                if is_ignored(matchers, matcher_dirs, workspace, child_rel, False):
                    continue
                found.append(child)

    walk(workspace, "")
    return found


def _fingerprint(workspace: Path) -> str:
    """Cheap state identity: rel path + size + mtime for every walked file."""
    parts: list[str] = []
    for path in _walk_files(workspace):
        try:
            stat = path.stat()
            parts.append(f"{path.relative_to(workspace)}:{stat.st_size}:{stat.st_mtime_ns}")
        except OSError:
            continue
    return "\n".join(parts)


def create_checkpoint(workspace: Path, session_id: str) -> dict:
    """Snapshot the workspace before a turn mutates it. Best-effort."""
    workspace = Path(workspace).resolve()
    if not workspace.is_dir():
        return {"skipped": "workspace_missing"}

    files = _walk_files(workspace)
    if len(files) > _MAX_FILES:
        return {"skipped": f"too_many_files({len(files)})"}

    # 同一秒内的多个快照必须严格递增：纳秒部分固定 9 位零填充，
    # 否则字符串排序会打乱时间顺序（undo/redo 依赖"最新优先"）。
    stamp = time.strftime("%Y%m%d_%H%M%S") + (
        f"_{time.time_ns() % 1_000_000_000:09d}"
    )
    cp_dir = _checkpoints_root(session_id) / stamp
    files_dir = cp_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    manifest_files: list[str] = []
    total = 0
    complete = True
    for path in files:
        rel = path.relative_to(workspace).as_posix()
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > _MAX_FILE_BYTES:
            complete = False
            continue
        if total + size > _MAX_TOTAL_BYTES or len(manifest_files) >= _MAX_FILES:
            complete = False
            break
        target = files_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(path, target)
        except OSError:
            complete = False
            continue
        manifest_files.append(rel)
        total += size

    (cp_dir / "manifest.json").write_text(
        json.dumps(
            {
                "created_at": time.time(),
                "workspace": str(workspace),
                "complete": complete,
                "fingerprint": _fingerprint(workspace),
                "files": manifest_files,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _prune(session_id)
    return {
        "checkpoint": stamp,
        "files": len(manifest_files),
        "bytes": total,
        "complete": complete,
    }


def _prune(session_id: str) -> None:
    root = _checkpoints_root(session_id)
    try:
        entries = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError:
        return
    for entry in entries[: -_KEEP_PER_SESSION]:
        shutil.rmtree(entry, ignore_errors=True)


def _load_manifest(cp_dir: Path) -> dict | None:
    try:
        return json.loads((cp_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _current_fingerprint_match(workspace: Path, fingerprint: str) -> bool:
    return _fingerprint(workspace) == fingerprint


def restore_latest(workspace: Path, session_id: str) -> dict:
    """Restore the newest checkpoint whose state differs from the workspace.

    恢复前先把当前状态存为新快照（redo 通道）；``complete=False`` 的快照
    只覆盖、不删除（快照不完整，删除会误伤没进快照的文件）。
    """
    workspace = Path(workspace).resolve()
    root = _checkpoints_root(session_id)
    candidates = sorted(
        (p for p in root.iterdir() if p.is_dir()), reverse=True
    ) if root.is_dir() else []

    chosen: tuple[Path, dict] | None = None
    for cp_dir in candidates:
        manifest = _load_manifest(cp_dir)
        if not manifest:
            continue
        if _current_fingerprint_match(workspace, str(manifest.get("fingerprint") or "")):
            continue  # 工作区仍是快照当时的状态，跳过（连续 undo → redo）
        chosen = (cp_dir, manifest)
        break
    if chosen is None:
        return {"restored": 0, "deleted": 0, "message": "没有可撤销的改动"}

    cp_dir, manifest = chosen
    # 先把当前状态存档，保证撤销本身可回退
    create_checkpoint(workspace, session_id)

    files_dir = cp_dir / "files"
    restored = 0
    for rel in manifest.get("files") or []:
        source = files_dir / rel
        target = workspace / rel
        if not source.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(source, target)
            restored += 1
        except OSError as exc:
            logger.warning("checkpoint restore failed rel=%s: %s", rel, exc)

    deleted = 0
    if manifest.get("complete"):
        snapshot_files = set(manifest.get("files") or [])
        for path in _walk_files(workspace):
            rel = path.relative_to(workspace).as_posix()
            if rel in snapshot_files:
                continue
            try:
                path.unlink()
                deleted += 1
            except OSError:
                pass

    logger.info(
        "checkpoint restored session=%s checkpoint=%s restored=%d deleted=%d",
        session_id,
        cp_dir.name,
        restored,
        deleted,
    )
    return {
        "restored": restored,
        "deleted": deleted,
        "checkpoint": cp_dir.name,
        "complete": bool(manifest.get("complete")),
    }
