"""事故回流测试：工具失败 → [复盘] todo 挂回计划。

覆盖设计文档验收清单：
- 失败生成复盘项 / 同 tool 去重 / 成功不生成
- add_todo 追加 index / 总量上限拦截 / 上限不影响普通 todo
"""


def _init(monkeypatch, tmp_path):
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "smoke.db"))

    from app import db
    from app.agent.state import (
        _MAX_RECOVERY_TODOS,
        _spawn_recovery_todo,
    )

    db.init_db()
    project = db.create_project("测试", str(tmp_path / "workspace"))
    session = db.create_session("回流测试", project["id"])
    return db, session["id"], _spawn_recovery_todo, _MAX_RECOVERY_TODOS


def test_failed_tool_spawns_recovery_todo(monkeypatch, tmp_path):
    db, sid, spawn, _ = _init(monkeypatch, tmp_path)
    assert db.list_todos(sid) == []
    new = spawn(sid, [], {"tool_name": "read_file", "reason": "文件不存在"})
    assert new is not None
    assert new["status"] == "pending"
    assert new["title"].startswith("[复盘] read_file 失败")
    assert db.list_todos(sid)[-1]["title"] == new["title"]


def test_same_tool_does_not_spawn_duplicate(monkeypatch, tmp_path):
    db, sid, spawn, _ = _init(monkeypatch, tmp_path)
    first = spawn(sid, [], {"tool_name": "read_file", "reason": "第一次失败"})
    assert first is not None
    again = spawn(
        sid, db.list_todos(sid), {"tool_name": "read_file", "reason": "第二次失败"}
    )
    assert again is None
    recovery = [t for t in db.list_todos(sid) if t["title"].startswith("[复盘]")]
    assert len(recovery) == 1


def test_success_tool_does_not_spawn(monkeypatch, tmp_path):
    db, sid, _, _ = _init(monkeypatch, tmp_path)
    # 成功路径：_finish_todo(success=True) 后不产生复盘项
    db.replace_todos(sid, ["普通任务"])
    todo = db.list_todos(sid)[0]

    from app.agent.state import _finish_todo

    _finish_todo(todo, True, "执行成功")
    titles = [t["title"] for t in db.list_todos(sid)]
    assert titles == ["普通任务"]
    assert not any(t.startswith("[复盘]") for t in titles)


def test_add_todo_appends_index(monkeypatch, tmp_path):
    db, sid, _, _ = _init(monkeypatch, tmp_path)
    db.replace_todos(sid, ["任务一", "任务二"])
    new = db.add_todo(sid, "追加任务")
    todos = db.list_todos(sid)
    assert [t["title"] for t in todos] == ["任务一", "任务二", "追加任务"]
    assert todos[-1]["id"] == new["id"]
    assert todos[-1]["index"] == 2


def test_cap_stops_spawning_after_max(monkeypatch, tmp_path):
    db, sid, spawn, cap = _init(monkeypatch, tmp_path)
    todos: list = []
    for i in range(cap):
        new = spawn(sid, todos, {"tool_name": f"tool_{i}", "reason": "失败"})
        assert new is not None
        todos = db.list_todos(sid)
    # 已达到上限：再多一个不同工具也不回流
    blocked = spawn(sid, todos, {"tool_name": "tool_overflow", "reason": "失败"})
    assert blocked is None
    recovery = [t for t in db.list_todos(sid) if t["title"].startswith("[复盘]")]
    assert len(recovery) == cap


def test_cap_does_not_affect_normal_todos(monkeypatch, tmp_path):
    db, sid, spawn, cap = _init(monkeypatch, tmp_path)
    # 普通 todo 超过上限数量，但复盘项为 0 → 不受上限影响，仍可回流
    for i in range(cap * 2):
        db.add_todo(sid, f"普通任务{i}")
    new = spawn(sid, db.list_todos(sid), {"tool_name": "read_file", "reason": "失败"})
    assert new is not None
    assert len(db.list_todos(sid)) == cap * 2 + 1
