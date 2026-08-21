from pathlib import Path


def _init(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    workspace_dir = tmp_path / "workspace"
    db_path = tmp_path / "memories.db"
    monkeypatch.setenv("DIVINE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(workspace_dir))
    monkeypatch.setenv("DB_PATH", str(db_path))

    from app import db

    db.init_db()
    return db


def test_memory_save_and_list(tmp_path, monkeypatch):
    db = _init(tmp_path, monkeypatch)
    saved = db.save_memory("用户偏好 TypeScript，不喜欢 Python", "preference")
    assert saved["status"] == "active"
    assert saved["category"] == "preference"

    listed = db.list_active_memories()
    assert len(listed) == 1
    assert listed[0]["content"] == "用户偏好 TypeScript，不喜欢 Python"


def test_memory_category_validation(tmp_path, monkeypatch):
    db = _init(tmp_path, monkeypatch)
    try:
        db.save_memory("随便", "unknown_category")
        raise AssertionError("should have raised ValueError")
    except ValueError:
        pass


def test_memory_search_cjk_and_en(tmp_path, monkeypatch):
    db = _init(tmp_path, monkeypatch)
    db.save_memory("用户偏好 TypeScript，不喜欢 Python", "preference")
    db.save_memory("用户对花生过敏", "fact")
    db.save_memory("用户养了一只柯基叫土豆", "fact")

    hits = db.search_memories("TypeScript", limit=5)
    assert hits and hits[0]["content"].startswith("用户偏好 TypeScript")

    hits_cjk = db.search_memories("过敏", limit=5)
    assert hits_cjk and "花生" in hits_cjk[0]["content"]

    hits_kor = db.search_memories("柯基", limit=5)
    assert hits_kor and "柯基" in hits_kor[0]["content"]


def test_memory_supersede_similar(tmp_path, monkeypatch):
    db = _init(tmp_path, monkeypatch)
    old = db.save_memory("用户喜欢深色主题", "preference")
    new = db.save_memory("用户喜欢浅色主题", "preference")

    active = db.list_active_memories()
    assert all(item["id"] != old["id"] for item in active)
    assert any(item["id"] == new["id"] for item in active)
    assert db.list_active_memories(category="fact") == []


def test_memory_keeps_different_topics(tmp_path, monkeypatch):
    db = _init(tmp_path, monkeypatch)
    vue = db.save_memory("用户喜欢 Vue", "preference")
    react = db.save_memory("用户改成用 React 了，以后都用 React", "preference")

    active = db.list_active_memories()
    assert any(item["id"] == vue["id"] for item in active)
    assert any(item["id"] == react["id"] for item in active)


def test_memory_forget_by_content(tmp_path, monkeypatch):
    db = _init(tmp_path, monkeypatch)
    db.save_memory("用户养了一只柯基叫土豆", "fact")
    removed = db.forget_memory_by_content("用户养了一只柯基叫土豆")
    assert removed == 1
    assert db.list_active_memories() == []

    # Second forget is a no-op.
    assert db.forget_memory_by_content("用户养了一只柯基叫土豆") == 0


def test_memory_forget_by_id(tmp_path, monkeypatch):
    db = _init(tmp_path, monkeypatch)
    saved = db.save_memory("用户喜欢深色主题", "preference")
    assert db.forget_memory(saved["id"]) is True
    assert db.forget_memory(saved["id"]) is False
    assert db.list_active_memories() == []


def test_memory_search_empty_query_falls_back(tmp_path, monkeypatch):
    db = _init(tmp_path, monkeypatch)
    db.save_memory("用户喜欢深色主题", "preference")
    hits = db.search_memories("", limit=5)
    assert len(hits) == 1
