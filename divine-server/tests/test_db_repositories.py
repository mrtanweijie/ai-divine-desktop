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
    assert db.list_projects()[0]["name"] == "测试项目"
    assert Path(db_path).exists()
