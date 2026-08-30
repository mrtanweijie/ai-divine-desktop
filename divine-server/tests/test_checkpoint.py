"""turn 级工作区快照与撤销（P3-3b）：checkpoint 创建/恢复/undo-redo/剪枝。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "eval-cp.db"))
    from app.tools import checkpoint

    return checkpoint


def _make_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "src").mkdir(parents=True)
    (ws / "src" / "main.py").write_text("print('v1')\n", encoding="utf-8")
    (ws / "README.md").write_text("hello\n", encoding="utf-8")
    (ws / ".git").mkdir()
    (ws / ".git" / "HEAD").write_text("ref: main\n", encoding="utf-8")
    return ws


def test_create_and_noop_restore(tmp_path, monkeypatch):
    checkpoint = _setup_env(tmp_path, monkeypatch)
    ws = _make_workspace(tmp_path)
    info = checkpoint.create_checkpoint(ws, "s1")
    assert info.get("files") == 2  # .git 被跳过
    assert info.get("complete") is True
    # 工作区没变 → 没有可撤销的改动
    result = checkpoint.restore_latest(ws, "s1")
    assert result["restored"] == 0 and result["deleted"] == 0


def test_restore_reverts_edits_and_deletes_new_files(tmp_path, monkeypatch):
    checkpoint = _setup_env(tmp_path, monkeypatch)
    ws = _make_workspace(tmp_path)
    checkpoint.create_checkpoint(ws, "s2")

    # agent 修改现有文件 + 新建文件
    (ws / "src" / "main.py").write_text("print('v2 broken')\n", encoding="utf-8")
    (ws / "src" / "extra.py").write_text("new\n", encoding="utf-8")

    result = checkpoint.restore_latest(ws, "s2")
    assert result["restored"] == 2
    assert result["deleted"] == 1
    assert (ws / "src" / "main.py").read_text(encoding="utf-8") == "print('v1')\n"
    assert not (ws / "src" / "extra.py").exists()
    # .git 永不被碰
    assert (ws / ".git" / "HEAD").read_text(encoding="utf-8") == "ref: main\n"


def test_undo_then_undo_again_is_redo(tmp_path, monkeypatch):
    checkpoint = _setup_env(tmp_path, monkeypatch)
    ws = _make_workspace(tmp_path)
    checkpoint.create_checkpoint(ws, "s3")  # S1: v1

    (ws / "src" / "main.py").write_text("print('v2')\n", encoding="utf-8")
    # 下一轮开始时的快照（状态 = v2）
    checkpoint.create_checkpoint(ws, "s3")  # S2: v2

    # undo：跳过与当前一致的 S2，恢复到 S1
    checkpoint.restore_latest(ws, "s3")
    assert (ws / "src" / "main.py").read_text(encoding="utf-8") == "print('v1')\n"

    # 再 undo 一次 → 找到与当前不同的最新快照（S3=撤销前存档）→ 回到 v2（redo）
    checkpoint.restore_latest(ws, "s3")
    assert (ws / "src" / "main.py").read_text(encoding="utf-8") == "print('v2')\n"


def test_incomplete_snapshot_restores_without_delete(tmp_path, monkeypatch):
    checkpoint = _setup_env(tmp_path, monkeypatch)
    ws = _make_workspace(tmp_path)
    big = ws / "big.bin"
    big.write_bytes(b"x" * (600 * 1024))  # 超过单文件上限 → incomplete
    info = checkpoint.create_checkpoint(ws, "s4")
    assert info.get("complete") is False

    (ws / "README.md").write_text("changed\n", encoding="utf-8")
    result = checkpoint.restore_latest(ws, "s4")
    # README 被覆盖恢复；big.bin 不在快照里但不被误删
    assert (ws / "README.md").read_text(encoding="utf-8") == "hello\n"
    assert big.exists()
    assert result.get("complete") is False


def test_prune_keeps_recent_snapshots(tmp_path, monkeypatch):
    checkpoint = _setup_env(tmp_path, monkeypatch)
    ws = _make_workspace(tmp_path)
    import time

    for _ in range(7):
        checkpoint.create_checkpoint(ws, "s5")
        time.sleep(0.01)
    root = checkpoint._checkpoints_root("s5")
    entries = [p for p in root.iterdir() if p.is_dir()]
    assert len(entries) <= checkpoint._KEEP_PER_SESSION
