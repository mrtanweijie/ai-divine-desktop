from pathlib import Path


def _init(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    workspace_dir = tmp_path / "workspace"
    db_path = tmp_path / "compact.db"
    monkeypatch.setenv("DIVINE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(workspace_dir))
    monkeypatch.setenv("DB_PATH", str(db_path))

    from app import db

    db.init_db()
    return db


def test_estimate_tokens():
    from app.agent.state import estimate_tokens

    assert estimate_tokens("") == 0
    assert estimate_tokens("你好世界") == 4
    assert estimate_tokens("hello") == 1  # round(5/4) = 1
    assert estimate_tokens("你好") == 2
    assert estimate_tokens("hello world") == 2  # 10 non-CJK chars -> round(10/4) = 2
    assert estimate_tokens("hello world 你好") == 2 + 2  # 10 non-CJK + 2 CJK


def test_build_context_breakdown(tmp_path, monkeypatch):
    db = _init(tmp_path, monkeypatch)
    session = db.create_session("Test", None)
    for i in range(6):
        db.add_message(session["id"], "user", f"问题 {i}：" + "很长的内容" * 20)
        db.add_message(session["id"], "assistant", f"回答 {i}：" + "详细说明" * 20)

    from app.agent.state import build_context_breakdown

    usage = build_context_breakdown(session["id"])
    assert usage["contextWindow"] > 0
    assert usage["breakdown"]["systemPrompt"] > 0
    assert usage["breakdown"]["tools"] > 0
    assert usage["breakdown"]["messages"] > 0
    assert usage["estimatedTokens"] == (
        usage["breakdown"]["systemPrompt"]
        + usage["breakdown"]["tools"]
        + usage["breakdown"]["messages"]
    )
    assert 0 <= usage["usedPercent"] <= 100


def test_history_injects_summary(tmp_path, monkeypatch):
    db = _init(tmp_path, monkeypatch)
    session = db.create_session("Test", None)
    for i in range(4):
        db.add_message(session["id"], "user", f"问题 {i}")
        db.add_message(session["id"], "assistant", f"回答 {i}")

    db.save_summary(session["id"], "用户是前端工程师，喜欢简洁回答", cutoff_rowid=99, saved_tokens=100)

    from app.db.history import history_for_model

    history = history_for_model(session["id"], limit=20)
    assert history[0]["role"] == "system"
    assert "前端工程师" in history[0]["content"]
    assert history[1]["role"] == "user"


def test_compact_should_compact_after_enough_new_messages(tmp_path, monkeypatch):
    db = _init(tmp_path, monkeypatch)
    session = db.create_session("Test", None)
    for i in range(6):
        db.add_message(session["id"], "user", f"问题 {i}")
        db.add_message(session["id"], "assistant", f"回答 {i}")

    from app.agent.state import _should_compact

    # No summary yet -> cutoff 0 -> 6 user rows >= 4 turns and 12 rows -> compactable
    assert _should_compact(session["id"], 20, None) is True

    # After a summary with high cutoff -> not compactable yet
    from app.db.connection import _connect
    from contextlib import closing

    with closing(_connect()) as conn:
        max_rowid = conn.execute(
            "SELECT MAX(rowid) AS m FROM messages WHERE session_id = ?",
            (session["id"],),
        ).fetchone()["m"]
    summary = db.save_summary(session["id"], "早期摘要", cutoff_rowid=max_rowid, saved_tokens=10)
    assert _should_compact(session["id"], 20, summary) is False
