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


# --- v2 supersede 语义（022 §5.1）---------------------------------------


def test_polarity_conflict_parks_new_memory_as_pending(tmp_path, monkeypatch):
    """存入「喜欢」后再存「不喜欢」：两条均存活，新记忆挂起待确认。"""
    db = _init(tmp_path, monkeypatch)
    old = db.save_memory("用户喜欢 Python", "preference")
    new = db.save_memory("用户不喜欢 Python", "preference")

    assert old["status"] == "active"
    assert new["status"] == "pending"
    # pending 不进入读取路径
    assert [m["id"] for m in db.list_active_memories()] == [old["id"]]
    hits = db.search_memories("Python")
    assert [m["id"] for m in hits] == [old["id"]]
    # 旧记忆未被覆盖，留痕为空
    assert old["superseded_by"] is None


def test_polarity_false_positive_keeps_both_active(tmp_path, monkeypatch):
    """「不错」等假否定词不应触发 pending 或覆盖。"""
    db = _init(tmp_path, monkeypatch)
    a = db.save_memory("用户觉得 Python 不错", "preference")
    b = db.save_memory("用户觉得 Python 好用", "preference")
    assert a["status"] == "active"
    assert b["status"] == "active"


def test_near_duplicate_auto_supersedes_with_trace(tmp_path, monkeypatch):
    """高重复 + 同极性才自动 supersede，且 superseded_by 可追溯。"""
    db = _init(tmp_path, monkeypatch)
    old = db.save_memory("用户喜欢深色主题", "preference")
    new = db.save_memory("用户喜欢深色主题呀", "preference")

    assert new["status"] == "active"
    active = db.list_active_memories()
    assert [m["id"] for m in active] == [new["id"]]
    superseded = db.list_memories(status="superseded")
    row = next(m for m in superseded if m["id"] == old["id"])
    assert row["superseded_by"] == new["id"]


def test_paraphrase_update_via_supersede_id(tmp_path, monkeypatch):
    """改述式更新走显式 supersede_id，绕过相似度阈值。"""
    db = _init(tmp_path, monkeypatch)
    old = db.save_memory("用户喜欢 Python", "preference")
    new = db.save_memory(
        "用户现在主用 Go 了", "preference", supersede_id=old["id"]
    )
    assert new["status"] == "active"
    assert [m["id"] for m in db.list_active_memories()] == [new["id"]]
    superseded = db.list_memories(status="superseded")
    row = next(m for m in superseded if m["id"] == old["id"])
    assert row["superseded_by"] == new["id"]


def test_supersede_id_requires_existing_active_memory(tmp_path, monkeypatch):
    db = _init(tmp_path, monkeypatch)
    try:
        db.save_memory("随便", "preference", supersede_id="missing")
        raise AssertionError("should have raised ValueError")
    except ValueError:
        pass

    old = db.save_memory("用户喜欢深色主题", "preference")
    db.forget_memory(old["id"])
    try:
        db.save_memory("用户喜欢浅色主题", "preference", supersede_id=old["id"])
        raise AssertionError("should have raised ValueError")
    except ValueError:
        pass


def test_short_memory_cannot_swallow_long_subset(tmp_path, monkeypatch):
    """子集判定的长度/token 护栏：短句不应吞掉长句。"""
    db = _init(tmp_path, monkeypatch)
    old = db.save_memory("用户喜欢 Python", "preference")
    new = db.save_memory(
        "用户喜欢 Python，也喜欢 Go 和 Rust，最近还在学 Swift", "preference"
    )
    assert new["status"] == "active"
    assert old["status"] == "active"
    assert len(db.list_active_memories()) == 2


def test_pending_confirm_and_reject(tmp_path, monkeypatch):
    db = _init(tmp_path, monkeypatch)
    old = db.save_memory("用户喜欢 Python", "preference")
    new = db.save_memory("用户不喜欢 Python", "preference")

    assert db.confirm_pending_memory(new["id"]) is True
    assert {m["id"] for m in db.list_active_memories()} == {old["id"], new["id"]}
    assert db.list_pending_memories() == []
    # 再次确认是 no-op
    assert db.confirm_pending_memory(new["id"]) is False


def test_pending_reject_soft_deletes(tmp_path, monkeypatch):
    db = _init(tmp_path, monkeypatch)
    db.save_memory("用户喜欢 Python", "preference")
    new = db.save_memory("用户不喜欢 Python", "preference")

    assert db.reject_pending_memory(new["id"]) is True
    assert db.list_active_memories()
    assert db.list_pending_memories() == []
    superseded = db.list_memories(status="superseded")
    assert any(m["id"] == new["id"] for m in superseded)


def test_unrelated_topics_unaffected_by_polarity(tmp_path, monkeypatch):
    """低相似度时极性不影响各自独立存活。"""
    db = _init(tmp_path, monkeypatch)
    a = db.save_memory("用户喜欢 Python", "preference")
    b = db.save_memory("用户养了一只柯基叫土豆", "fact")
    assert a["status"] == "active"
    assert b["status"] == "active"


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
