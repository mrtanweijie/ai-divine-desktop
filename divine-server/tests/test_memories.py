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


# --- v2 打分与工具链（022 §4.2 / §5.2）----------------------------------


def test_search_returns_normalized_score_and_sim(tmp_path, monkeypatch):
    db = _init(tmp_path, monkeypatch)
    db.save_memory("用户对花生过敏", "fact")
    db.save_memory("用户养了一只柯基叫土豆", "fact")
    hits = db.search_memories("花生", limit=5)
    assert hits
    top = hits[0]
    assert "花生" in top["content"]
    # 归一化后 sim_norm = 1.0，sim 保留原始余弦便于调参观测
    assert top["sim"] > 0
    assert top["score"] >= top["sim"]


def test_access_refresh_keeps_hot_memory_ranking(tmp_path, monkeypatch):
    """访问续命：被召回的记忆 last_accessed_at 刷新，recency 不衰减。"""
    from datetime import datetime, timedelta, timezone

    db = _init(tmp_path, monkeypatch)
    old_topic = db.save_memory("用户喜欢深色主题", "preference")
    stale = datetime.now(timezone.utc) - timedelta(days=120)
    db.touch_memory_access([])
    # 直接把 last_accessed_at 调旧，模拟久未访问
    import sqlite3

    conn = sqlite3.connect(str(tmp_path / "memories.db"))
    conn.execute(
        "UPDATE user_memories SET last_accessed_at = ? WHERE id = ?",
        (stale.isoformat(timespec="seconds"), old_topic["id"]),
    )
    conn.commit()
    conn.close()

    db.touch_memory_access([old_topic["id"]])
    row = db.list_active_memories()[0]
    assert row["last_accessed_at"] is not None
    assert row["last_accessed_at"] > stale.isoformat(timespec="seconds")


def test_recall_memories_tool_entry(tmp_path, monkeypatch):
    db = _init(tmp_path, monkeypatch)
    db.save_memory("用户对花生过敏", "fact")
    db.save_memory("用户不喜欢吃香菜", "preference")

    hits = db.recall_memories("对花生过敏吗", scope="user", limit=5)
    assert hits
    assert all(m["status"] == "active" for m in hits)
    # 召回即续命
    assert all(m["last_accessed_at"] for m in hits)
    hits2 = db.recall_memories("香菜", scope="user", limit=5)
    assert hits2 and "香菜" in hits2[0]["content"]


def test_fuzzy_forget_dominant_candidate_auto_deletes(tmp_path, monkeypatch):
    """模糊删除：top1 相似度足够高且显著领先时直接删。"""
    db = _init(tmp_path, monkeypatch)
    db.save_memory("用户养了一只柯基叫土豆", "fact")
    db.save_memory("用户对花生过敏", "fact")

    result = db.forget_memory_by_query("用户养了一只柯基叫土豆呀")
    assert len(result["deleted"]) == 1
    assert "柯基" in result["deleted"][0]["content"]
    remaining = db.list_active_memories()
    assert len(remaining) == 1
    assert "花生" in remaining[0]["content"]


def test_fuzzy_forget_uncertain_match_requires_confirmation(tmp_path, monkeypatch):
    """口语化指认相似度不够高时不自动删，返回候选交由确认。"""
    db = _init(tmp_path, monkeypatch)
    db.save_memory("用户养了一只柯基叫土豆", "fact")
    db.save_memory("用户对花生过敏", "fact")

    result = db.forget_memory_by_query("那条柯基的记忆")
    assert not result["deleted"]
    assert len(result["candidates"]) >= 1
    assert all("柯基" in c["content"] for c in result["candidates"])
    # 按确认后的 id 删除
    assert db.forget_memory(result["candidates"][0]["id"]) is True


def test_fuzzy_forget_lexical_decoy_never_auto_deletes(tmp_path, monkeypatch):
    """词汇碰瓷查询（用户在东京买房了 vs 用户在上海工作 sim≈0.34）不得自动删。"""
    db = _init(tmp_path, monkeypatch)
    db.save_memory("用户在上海工作", "fact")
    db.save_memory("用户养了一只柯基叫土豆", "fact")

    result = db.forget_memory_by_query("用户在东京买房了")
    assert not result["deleted"]
    assert len(db.list_active_memories()) == 2


def test_fuzzy_forget_no_match_is_noop(tmp_path, monkeypatch):
    db = _init(tmp_path, monkeypatch)
    db.save_memory("用户养了一只柯基叫土豆", "fact")
    result = db.forget_memory_by_query("帮我写一个快速排序")
    assert not result["deleted"]
    assert not result["candidates"]
    assert len(db.list_active_memories()) == 1


# --- 三期：项目作用域（022 §5.3）----------------------------------------


def _make_project(db, name: str, path: str) -> dict:
    return db.create_project(name=name, path=path)


def test_project_scope_isolation(tmp_path, monkeypatch):
    """项目 A 的约定不出现在项目 B / 全局注入中。"""
    db = _init(tmp_path, monkeypatch)
    pa = _make_project(db, "项目A", str(tmp_path / "a"))
    pb = _make_project(db, "项目B", str(tmp_path / "b"))
    db.save_memory("项目A用 pnpm 构建有坑", "fact", project_id=pa["id"])
    db.save_memory("项目B用 npm workspaces", "fact", project_id=pb["id"])
    db.save_memory("用户对花生过敏", "fact")

    hits_a = db.search_memories("构建", limit=5, project_id=pa["id"])
    contents = [h["content"] for h in hits_a]
    assert any("pnpm" in c for c in contents)
    assert not any("npm workspaces" in c for c in contents)

    hits_b = db.search_memories("构建", limit=5, project_id=pb["id"])
    assert not any("pnpm" in h["content"] for h in hits_b)

    # 全局查询只见全局记忆
    hits_global = db.search_memories("构建", limit=5)
    assert hits_global == []


def test_project_memories_rank_first_with_global_reserved(tmp_path, monkeypatch):
    """合并检索：项目记忆优先，但全局记忆保留席位。"""
    db = _init(tmp_path, monkeypatch)
    pa = _make_project(db, "项目A", str(tmp_path / "a"))
    for index in range(5):
        db.save_memory(f"项目A规范第{index}条", "fact", project_id=pa["id"])
    db.save_memory("用户对花生过敏", "fact")

    hits = db.search_memories("规范 过敏", limit=5, project_id=pa["id"])
    contents = [h["content"] for h in hits]
    assert "用户对花生过敏" in contents  # 全局席位保留
    assert contents[-1] == "用户对花生过敏"  # 且排在项目记忆之后
    assert len(hits) <= 5


def test_save_and_recall_project_scope(tmp_path, monkeypatch):
    db = _init(tmp_path, monkeypatch)
    pa = _make_project(db, "项目A", str(tmp_path / "a"))
    saved = db.save_memory("项目A部署用 Docker", "fact", project_id=pa["id"])
    assert saved["project_id"] == pa["id"]

    hits = db.recall_memories(
        "部署 Docker", scope="project", limit=5, project_id=pa["id"]
    )
    assert any("Docker" in h["content"] for h in hits)


def test_legacy_backfill_via_source_session(tmp_path, monkeypatch):
    """历史记忆按 source_session_id 反查项目回填（022 §5.3）。"""
    db = _init(tmp_path, monkeypatch)
    pa = _make_project(db, "项目A", str(tmp_path / "a"))
    session = db.create_session(title="旧会话", project_id=pa["id"])
    import sqlite3

    saved = db.save_memory(
        "旧项目记忆", "fact", source_session_id=session["id"]
    )
    assert saved["project_id"] is None
    # 重新跑 init_db 触发回填
    db.init_db()
    conn = sqlite3.connect(str(tmp_path / "memories.db"))
    row = conn.execute(
        "SELECT project_id FROM user_memories WHERE id = ?", (saved["id"],)
    ).fetchone()
    conn.close()
    assert row[0] == pa["id"]


# --- 四期：L1 情景记忆跨会话检索（022 §4.3）------------------------------


def test_session_summary_cross_session_recall(tmp_path, monkeypatch):
    """「上次那个方案最后定的什么」：scope=session 跨会话检索摘要。"""
    db = _init(tmp_path, monkeypatch)
    pa = _make_project(db, "项目A", str(tmp_path / "a"))
    s1 = db.create_session(title="会话1", project_id=pa["id"])
    s2 = db.create_session(title="会话2", project_id=pa["id"])
    db.save_summary(
        s1["id"],
        "最终决定：登录模块采用 OAuth2 + JWT，放弃 session 方案；下周联调。",
        cutoff_rowid=10,
    )
    db.save_summary(
        s2["id"],
        "讨论了缓存策略，倾向本地 LRU + TTL 双层。",
        cutoff_rowid=5,
    )

    hits = db.recall_memories("登录模块最终用什么方案", scope="session", limit=3)
    assert hits
    assert hits[0]["category"] == "session"
    assert "OAuth2" in hits[0]["content"]

    # 项目作用域：项目 B 检索不到项目 A 的摘要
    pb = _make_project(db, "项目B", str(tmp_path / "b"))
    s3 = db.create_session(title="会话3", project_id=pb["id"])
    db.save_summary(s3["id"], "项目B改用 GraphQL 网关。", cutoff_rowid=3)
    hits_b = db.recall_memories(
        "登录模块最终用什么方案", scope="session", limit=5, project_id=pb["id"]
    )
    assert all("OAuth2" not in h["content"] for h in hits_b)


def test_session_summary_project_id_deduped_on_save(tmp_path, monkeypatch):
    db = _init(tmp_path, monkeypatch)
    pa = _make_project(db, "项目A", str(tmp_path / "a"))
    s1 = db.create_session(title="会话1", project_id=pa["id"])
    row = db.save_summary(s1["id"], "结论：用 pnpm。", cutoff_rowid=1)
    assert row["project_id"] == pa["id"]
