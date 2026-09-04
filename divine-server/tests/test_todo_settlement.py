"""计划终态收敛测试：修复 D1（run 结束 todo 状态归零）+ D5（skipped 语义）。

覆盖设计文档（docs/agent-progress-observability-design.md）验收清单：
- sync_todos 保留本地 done/error 实证状态，不被 state 覆盖
- sync_todos 按 title 匹配合并，state 新增/删除正确反映
- [复盘] 回流项跨 run 存活，普通本地独有项清理
- settle_todos：running→done、pending→skipped、done/error 不动
- abort_todos：running→skipped、pending 保留
- _sync_todos_from_state：空 state 不动本地、status 映射正确
"""


def _init(monkeypatch, tmp_path):
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "smoke.db"))

    from app import db

    db.init_db()
    project = db.create_project("测试", str(tmp_path / "workspace"))
    session = db.create_session("终态收敛测试", project["id"])
    return db, session["id"]


def _states(items):
    """按 sync_todos 入参契约构造（persistence 层负责 content→title 映射）。"""
    return [{"title": title, "status": status} for title, status in items]


def test_sync_keeps_local_error_status(monkeypatch, tmp_path):
    db, sid = _init(monkeypatch, tmp_path)
    db.replace_todos(sid, ["读取配置", "运行验证"])
    todos = db.list_todos(sid)
    db.update_todo_status(todos[0]["id"], "error", "文件不存在")

    db.sync_todos(
        sid,
        _states([("读取配置", "completed"), ("运行验证", "pending")]),
    )
    result = {t["title"]: t["status"] for t in db.list_todos(sid)}
    assert result["读取配置"] == "error"
    assert result["运行验证"] == "pending"


def test_sync_upgrades_local_pending_to_done(monkeypatch, tmp_path):
    db, sid = _init(monkeypatch, tmp_path)
    db.replace_todos(sid, ["读取配置", "运行验证"])

    db.sync_todos(
        sid,
        _states([("读取配置", "done"), ("运行验证", "running")]),
    )
    result = {t["title"]: t["status"] for t in db.list_todos(sid)}
    assert result["读取配置"] == "done"
    assert result["运行验证"] == "running"


def test_sync_keeps_local_done_when_state_pending(monkeypatch, tmp_path):
    db, sid = _init(monkeypatch, tmp_path)
    db.replace_todos(sid, ["读取配置"])
    todo = db.list_todos(sid)[0]
    db.update_todo_status(todo["id"], "done")

    db.sync_todos(sid, _states([("读取配置", "pending")]))
    assert db.list_todos(sid)[0]["status"] == "done"


def test_sync_adds_and_removes_items(monkeypatch, tmp_path):
    db, sid = _init(monkeypatch, tmp_path)
    db.replace_todos(sid, ["旧步骤"])

    db.sync_todos(
        sid, _states([("新步骤一", "completed"), ("新步骤二", "pending")])
    )
    titles = [t["title"] for t in db.list_todos(sid)]
    assert titles == ["新步骤一", "新步骤二"]


def test_sync_preserves_recovery_todo(monkeypatch, tmp_path):
    db, sid = _init(monkeypatch, tmp_path)
    db.replace_todos(sid, ["读取配置"])
    recovery = db.add_todo(sid, "[复盘] edit_file 失败：权限不足")

    db.sync_todos(sid, _states([("读取配置", "completed")]))
    titles = [t["title"] for t in db.list_todos(sid)]
    assert titles == ["读取配置", "[复盘] edit_file 失败：权限不足"]
    assert db.list_todos(sid)[-1]["id"] == recovery["id"]
    assert db.list_todos(sid)[-1]["status"] == "pending"


def test_sync_drops_stale_recovery_done(monkeypatch, tmp_path):
    db, sid = _init(monkeypatch, tmp_path)
    recovery = db.add_todo(sid, "[复盘] edit_file 失败：权限不足")
    db.update_todo_status(recovery["id"], "done")

    db.sync_todos(sid, _states([("读取配置", "completed")]))
    titles = [t["title"] for t in db.list_todos(sid)]
    assert "[复盘] edit_file 失败：权限不足" not in titles


def test_settle_running_to_done_pending_to_skipped(monkeypatch, tmp_path):
    db, sid = _init(monkeypatch, tmp_path)
    db.replace_todos(sid, ["步骤一", "步骤二", "步骤三", "步骤四"])
    todos = db.list_todos(sid)
    db.update_todo_status(todos[0]["id"], "done")
    db.update_todo_status(todos[1]["id"], "error", "原因")
    db.update_todo_status(todos[2]["id"], "running")

    items, settled = db.settle_todos(sid)
    result = {t["title"]: t["status"] for t in items}
    assert result["步骤一"] == "done"
    assert result["步骤二"] == "error"
    assert result["步骤三"] == "done"
    assert result["步骤四"] == "skipped"
    assert settled == 2


def test_abort_running_to_skipped_pending_kept(monkeypatch, tmp_path):
    db, sid = _init(monkeypatch, tmp_path)
    db.replace_todos(sid, ["步骤一", "步骤二", "步骤三"])
    todos = db.list_todos(sid)
    db.update_todo_status(todos[0]["id"], "done")
    db.update_todo_status(todos[1]["id"], "running")

    db.abort_todos(sid)
    result = {t["title"]: t["status"] for t in db.list_todos(sid)}
    assert result["步骤一"] == "done"
    assert result["步骤二"] == "skipped"
    assert result["步骤三"] == "pending"


def test_sync_from_state_empty_keeps_local(monkeypatch, tmp_path):
    from app.agent.state.persistence import _sync_todos_from_state

    db, sid = _init(monkeypatch, tmp_path)
    db.replace_todos(sid, ["读取配置"])
    todo = db.list_todos(sid)[0]
    db.update_todo_status(todo["id"], "done")

    _sync_todos_from_state(sid, {"todos": []})
    result = db.list_todos(sid)
    assert len(result) == 1
    assert result[0]["status"] == "done"


def test_sync_from_state_maps_statuses(monkeypatch, tmp_path):
    from app.agent.state.persistence import _sync_todos_from_state

    db, sid = _init(monkeypatch, tmp_path)
    db.replace_todos(sid, ["步骤一", "步骤二", "步骤三"])

    _sync_todos_from_state(
        sid,
        {
            "todos": [
                {"content": "步骤一", "status": "in_progress"},
                {"content": "步骤二", "status": "completed"},
                {"content": "步骤三", "status": "pending"},
            ]
        },
    )
    result = {t["title"]: t["status"] for t in db.list_todos(sid)}
    assert result["步骤一"] == "running"
    assert result["步骤二"] == "done"
    assert result["步骤三"] == "pending"
