from pathlib import Path


def test_project_session_message_roundtrip(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    workspace_dir = tmp_path / "workspace"
    db_path = tmp_path / "smoke.db"
    monkeypatch.setenv("DIVINE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(workspace_dir))
    monkeypatch.setenv("DB_PATH", str(db_path))

    from app import db

    db.init_db()
    project = db.create_project("测试项目", str(workspace_dir))
    session = db.create_session("Hello", project["id"])
    message = db.add_message(session["id"], "user", "你好")
    db.add_message_part(message["id"], "file", '{"name":"a.txt"}', order=0)

    loaded = db.load_session(session["id"])
    assert loaded["session"]["id"] == session["id"]
    assert loaded["messages"][0]["content"] == "你好"
    # init_db may auto-create the default project; list order by updated_at is
    # nondeterministic for same-second rows, so match by name instead of [0].
    project_names = [entry["name"] for entry in db.list_projects()]
    assert "测试项目" in project_names
    assert Path(db_path).exists()


def test_local_fallback_source_marked(monkeypatch, tmp_path):
    """本地拒答转云端留痕：挂标记后下一条 assistant 消息带 source。"""
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "smoke.db"))

    from app import db

    db.init_db()
    project = db.create_project("测试", str(tmp_path / "workspace"))
    session = db.create_session("留痕测试", project["id"])
    sid = session["id"]

    # 未挂标记 → 默认 source
    normal = db.add_message(sid, "assistant", "正常回答")
    assert normal["source"] == "normal"

    # 挂标记 → 下一条 assistant 消息记 local_fallback，且只消费一次
    db.mark_fallback_pending(sid)
    fallback = db.add_message(sid, "assistant", "云端回答")
    assert fallback["source"] == "local_fallback"
    after = db.add_message(sid, "assistant", "后续回答")
    assert after["source"] == "normal"

    # user 消息不消费标记（标记只对 assistant 生效）
    db.mark_fallback_pending(sid)
    user_msg = db.add_message(sid, "user", "追问")
    assert user_msg["source"] == "normal"
    assert db.clear_fallback_pending(sid) is None


def test_history_until_message_id(monkeypatch, tmp_path):
    """重答云端：history_for_model 截断到指定消息为止（含），丢弃其后消息。"""
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "smoke.db"))

    from app import db

    db.init_db()
    project = db.create_project("测试", str(tmp_path / "workspace"))
    session = db.create_session("截断测试", project["id"])
    sid = session["id"]

    db.add_message(sid, "user", "问题一")
    m1 = db.add_message(sid, "assistant", "本地回答一", source="local")
    db.add_message(sid, "user", "问题二")
    m2 = db.add_message(sid, "assistant", "云端回答二")

    # 截断到"问题二"（m2 之前的 user）→ 不含 m2
    history = db.history_for_model(sid, limit=20, until_message_id="question2")
    # 没有该 id 时回退全量
    assert any(m["role"] == "assistant" and m["content"] == "云端回答二" for m in history)

    # 截断到 m1 之前的用户问题 → 不含"本地回答一"
    q1 = db.list_messages(sid)[0]
    history = db.history_for_model(sid, limit=20, until_message_id=q1["id"])
    contents = [m.get("content") for m in history]
    assert "问题一" in contents
    assert "本地回答一" not in contents
    assert "问题二" not in contents
