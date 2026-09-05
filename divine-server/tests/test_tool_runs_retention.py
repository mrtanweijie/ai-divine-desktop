"""tool_runs retention：过期记录清理 + 行数上限。"""

import sqlite3

from app import db
from app.db.connection import get_conn, _new_id
from app.db.tool_runs import prune_tool_runs


def _seed_run(session_id: str, started_at: str) -> str:
    run_id = _new_id()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO tool_runs (id, session_id, tool_name, status, input, started_at) "
            "VALUES (?, ?, 'terminal', 'done', '{}', ?)",
            (run_id, session_id, started_at),
        )
    return run_id


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "retention.db"))
    from app import db as db_mod

    db_mod.init_db()
    return db_mod.create_session("retention")["id"]


def test_prune_removes_expired_keeps_recent(tmp_path, monkeypatch):
    session_id = _setup(tmp_path, monkeypatch)
    old_id = _seed_run(session_id, "2020-01-01T00:00:00+00:00")
    fresh_id = _seed_run(session_id, "2099-01-01T00:00:00+00:00")

    removed = prune_tool_runs(keep_days=30)

    assert removed >= 1
    rows = sqlite3.connect(str(tmp_path / "retention.db")).execute(
        "SELECT id FROM tool_runs"
    ).fetchall()
    ids = {r[0] for r in rows}
    assert old_id not in ids
    assert fresh_id in ids


def test_prune_caps_total_rows(tmp_path, monkeypatch):
    session_id = _setup(tmp_path, monkeypatch)
    for i in range(6):
        _seed_run(session_id, f"2099-01-0{((i % 9) + 1)}T00:00:00+00:00")

    prune_tool_runs(keep_days=30, max_rows=4)

    rows = sqlite3.connect(str(tmp_path / "retention.db")).execute(
        "SELECT COUNT(*) FROM tool_runs"
    ).fetchone()[0]
    assert rows == 4


def test_prune_on_empty_table_is_noop(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert prune_tool_runs() == 0
