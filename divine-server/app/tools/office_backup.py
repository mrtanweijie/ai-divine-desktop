"""Office 编辑备份：undo_last_turn 对大体积 Office 文件的兜底撤销。

背景（docs/design/017-office-edit-closed-loop-20260906.md §5.3）：checkpoint 快照单文件
上限 512KB（checkpoint.py ``_MAX_FILE_BYTES``），带图 docx/xlsx 轻松超限，
``undo_last_turn`` 的快照恢复保护不了 Office 编辑。本模块提供字节级备份：

- 备份放 ``data_dir/backups/<session_id>/``，**不进 workspace**——Rust 侧
  文件树（workspace.rs）无点前缀过滤，workspace 内的备份文件会漏进前端
  文件面板并触发 watch 事件；放 data_dir 与 checkpoints 同级有先例；
- manifest.jsonl 逐条记录 {ts, original, backup}；恢复按批次（同一 ts）
  进行，恢复即消费该批次，连续调用 undo 可逐批回溯（无 redo，文档化限制）；
- 每个原文件保留最近 3 份备份。
"""

from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

from ..config import data_dir

_KEEP_PER_TARGET = 3
_MANIFEST_NAME = "manifest.jsonl"


def _session_dir(session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "")[:80] or "default"
    return data_dir() / "backups" / safe


def _read_manifest(root: Path) -> list[dict]:
    manifest = root / _MANIFEST_NAME
    if not manifest.is_file():
        return []
    entries: list[dict] = []
    try:
        for line in manifest.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return entries


def _append_manifest(root: Path, entry: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with (root / _MANIFEST_NAME).open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _rewrite_manifest(root: Path, entries: list[dict]) -> None:
    tmp = root / (_MANIFEST_NAME + ".tmp")
    with tmp.open("w", encoding="utf-8") as fp:
        for entry in entries:
            fp.write(json.dumps(entry, ensure_ascii=False) + "\n")
    tmp.replace(root / _MANIFEST_NAME)


def _prune(root: Path, original: str) -> None:
    entries = _read_manifest(root)
    mine = [e for e in entries if e.get("original") == original]
    if len(mine) <= _KEEP_PER_TARGET:
        return
    doomed = mine[: len(mine) - _KEEP_PER_TARGET]
    for entry in doomed:
        backup = root / str(entry.get("backup") or "")
        if backup.is_file():
            try:
                backup.unlink()
            except OSError:
                pass
    _rewrite_manifest(root, [e for e in entries if e not in doomed])


def backup_file(session_id: str, source: Path) -> Path | None:
    """编辑前备份原文件字节；返回备份路径，失败返回 None（不阻塞编辑）。"""
    try:
        source = Path(source).resolve()
        if not source.is_file():
            return None
        root = _session_dir(session_id)
        ts = time.strftime("%Y%m%d_%H%M%S") + f"_{time.monotonic_ns() % 10**9:09d}"
        root.mkdir(parents=True, exist_ok=True)
        backup = root / f"{ts}.bak"
        shutil.copy2(source, backup)
        _append_manifest(root, {"ts": ts, "original": str(source), "backup": backup.name})
        _prune(root, str(source))
        return backup
    except Exception:  # noqa: BLE001 — 备份失败不阻塞编辑主流程
        return None


def restore_latest_batch(session_id: str) -> dict:
    """恢复最近一批备份（同一 ts 为一批）；恢复即消费，返回恢复明细。"""
    root = _session_dir(session_id)
    entries = _read_manifest(root)
    if not entries:
        return {"restored": []}
    latest_ts = max(str(e.get("ts") or "") for e in entries)
    batch = [e for e in entries if str(e.get("ts")) == latest_ts]
    restored: list[dict] = []
    remaining = [e for e in entries if str(e.get("ts")) != latest_ts]
    for entry in batch:
        backup = root / str(entry.get("backup") or "")
        original = Path(str(entry.get("original") or ""))
        if not backup.is_file() or not original.name:
            continue
        try:
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, original)
            restored.append({"original": str(original), "backup": backup.name})
            try:
                backup.unlink()
            except OSError:
                pass
        except OSError:
            remaining.append(entry)
    _rewrite_manifest(root, remaining)
    return {"restored": restored}
