"""FTS 增量同步：写钩子即时可见 + 水位线对账自愈，不再每次搜索全量重建。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _setup_db(monkeypatch, tmp_path):
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "smoke.db"))
    from app import db

    db.init_db()
    return db


def _session_with_message(db, title: str, content: str):
    session = db.create_session(title)
    db.add_message(session["id"], "user", content)
    return session


def test_new_message_searchable_without_rebuild(monkeypatch, tmp_path):
    db = _setup_db(monkeypatch, tmp_path)
    session = _session_with_message(db, "支付对接", "这是一条关于支付宝接口的消息")

    results = db.search_sessions("支付宝")
    assert [r["id"] for r in results] == [session["id"]]
    assert "支付宝" in results[0]["snippet"]


def test_incremental_after_first_search(monkeypatch, tmp_path):
    db = _setup_db(monkeypatch, tmp_path)
    s1 = _session_with_message(db, "会话一", "第一条消息内容")

    assert db.search_sessions("第一条")  # 触发首次建索引
    s2 = _session_with_message(db, "会话二", "第二条消息内容")

    hits = {r["id"] for r in db.search_sessions("消息内容")}
    assert hits == {s1["id"], s2["id"]}


def test_title_rename_indexed(monkeypatch, tmp_path):
    db = _setup_db(monkeypatch, tmp_path)
    session = _session_with_message(db, "旧标题", "正文内容")

    assert db.search_sessions("旧标题")
    db.update_session(session["id"], title="新标题唯一词")

    assert db.search_sessions("新标题唯一词")
    assert db.search_sessions("旧标题") == []


def test_clear_messages_removed_from_index(monkeypatch, tmp_path):
    db = _setup_db(monkeypatch, tmp_path)
    session = _session_with_message(db, "清空测试", "独一份的关键词串")

    assert db.search_sessions("独一份的关键词串")
    db.clear_messages(session["id"])
    assert db.search_sessions("独一份的关键词串") == []


def test_delete_session_removed_from_index(monkeypatch, tmp_path):
    db = _setup_db(monkeypatch, tmp_path)
    session = _session_with_message(db, "删除测试", "删除后不可再搜到的词")

    assert db.search_sessions("删除后不可再搜到的词")
    db.delete_session(session["id"])
    assert db.search_sessions("删除后不可再搜到的词") == []


def test_delete_project_purges_orphans(monkeypatch, tmp_path):
    db = _setup_db(monkeypatch, tmp_path)
    project = db.create_project("待删项目", str(tmp_path / "ws"))
    session = db.create_session("项目内会话", project["id"])
    db.add_message(session["id"], "user", "项目级独有内容词")

    assert db.search_sessions("项目级独有内容词")
    db.delete_project(project["id"])
    assert db.search_sessions("项目级独有内容词") == []


def test_watermark_catches_unhooked_insert(monkeypatch, tmp_path):
    """绕过钩子的原始 INSERT 由水位线增量补齐。"""
    db = _setup_db(monkeypatch, tmp_path)
    session = _session_with_message(db, "水位测试", "初始内容")

    assert db.search_sessions("初始内容")  # 建立水位线
    from app.db.connection import get_conn, _new_id

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (id, session_id, role, content, created_at) "
            "VALUES (?, ?, 'user', '绕钩子直插的内容词', datetime('now'))",
            (_new_id(), session["id"]),
        )
        conn.commit()

    assert db.search_sessions("绕钩子直插的内容词")


def test_watermark_self_heals_unhooked_delete(monkeypatch, tmp_path):
    """绕过钩子删除最新消息 → rowid 回退 → 全量重建自愈。"""
    db = _setup_db(monkeypatch, tmp_path)
    session = _session_with_message(db, "自愈测试", "初始内容词")
    victim = db.add_message(session["id"], "user", "被直接删除的词")

    assert db.search_sessions("被直接删除的词")
    from app.db.connection import get_conn

    with get_conn() as conn:
        conn.execute("DELETE FROM messages WHERE id = ?", (victim["id"],))
        conn.commit()

    assert db.search_sessions("被直接删除的词") == []
    assert db.search_sessions("初始内容词")  # 自愈重建后其余内容仍在


def test_fts_state_watermark_persists(monkeypatch, tmp_path):
    db = _setup_db(monkeypatch, tmp_path)
    _session_with_message(db, "水位持久化", "一些内容")

    db.search_sessions("一些内容")
    from app.db.connection import get_conn

    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM fts_state WHERE key = 'last_rowid'"
        ).fetchone()
    assert row and int(row["value"]) > 0


def test_search_syntax_error_does_not_raise(monkeypatch, tmp_path):
    db = _setup_db(monkeypatch, tmp_path)
    _session_with_message(db, "降级测试会话", "普通内容")

    # 非法/怪异查询不应抛异常，始终返回列表（必要时走 LIKE 降级）
    for bad_query in ('"', "NEAR(", "普通内容 OR (", "**"):
        results = db.search_sessions(bad_query)
        assert isinstance(results, list)


def test_project_scoped_search(monkeypatch, tmp_path):
    db = _setup_db(monkeypatch, tmp_path)
    p1 = db.create_project("项目A", str(tmp_path / "a"))
    p2 = db.create_project("项目B", str(tmp_path / "b"))
    s1 = db.create_session("会话A", p1["id"])
    s2 = db.create_session("会话B", p2["id"])
    db.add_message(s1["id"], "user", "共享关键词甲")
    db.add_message(s2["id"], "user", "共享关键词甲")

    hits = {r["id"] for r in db.search_sessions("共享关键词甲", p1["id"])}
    assert hits == {s1["id"]}
