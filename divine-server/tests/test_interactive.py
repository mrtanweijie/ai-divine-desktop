"""``interactive`` 任务类型（design 027 §3.4）+ decide 路由。"""

from __future__ import annotations

import asyncio

from app.agent.tasks.interactive import (
    resolve_decision,
    run_interactive_task,
)


def _init_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "it.db"))
    from app import db

    db.init_db()
    return db


def _make_task(db, tmp_path, **overrides):
    project = db.create_project("p", str(tmp_path / "ws"))
    session = db.create_session("s", project["id"])
    defaults = dict(
        title="要开始整理日报吗",
        session_id=session["id"],
        task_type="interactive",
        prompt="整理今天的日报",
    )
    defaults.update(overrides)
    return db.create_scheduled_task(**defaults)


async def _drive(db, task, decision, expire=5):
    """起 handler → 等 ticket 落库 → 决策（decision=None 表示不决策，等超时）。"""
    import app.agent.tasks.interactive as it

    handler = asyncio.create_task(run_interactive_task(task))
    ticket = None
    for _ in range(200):
        await asyncio.sleep(0.01)
        current = db.get_scheduled_task(task["id"])
        if current and current.get("pending_user_action"):
            ticket = current["pending_user_action"]
            break
    assert ticket, "pending_user_action 一直没落库，前端发现不了待决任务"
    if decision is not None:
        assert it.resolve_decision(ticket, decision) is True
    await asyncio.wait_for(handler, timeout=expire + 5)
    return db.list_runs_for_task(task["id"])[0]


# --------------------------------------------------------------- 票据


def test_resolve_decision_unknown_ticket():
    assert resolve_decision("no-such-ticket", "approve") is False


# --------------------------------------------------------------- 三条分支


def test_approve_runs_agent(monkeypatch, tmp_path):
    import app.agent.tasks.interactive as it

    db = _init_env(monkeypatch, tmp_path)
    seen: dict = {}

    async def fake_agent(task):
        seen["prompt"] = task["prompt"]
        return [{"role": "assistant", "content": "日报已整理"}]

    monkeypatch.setattr(it, "run_agent_with_user_prompt", fake_agent)
    task = _make_task(db, tmp_path)

    run = asyncio.run(_drive(db, task, "approve"))

    assert run["status"] == "succeeded"
    assert run["output"] == "日报已整理"
    assert seen["prompt"] == "整理今天的日报"


def test_reject_skips(monkeypatch, tmp_path):
    import app.agent.tasks.interactive as it

    db = _init_env(monkeypatch, tmp_path)
    called = False

    async def fake_agent(task):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(it, "run_agent_with_user_prompt", fake_agent)
    task = _make_task(db, tmp_path)

    run = asyncio.run(_drive(db, task, "reject"))

    assert run["status"] == "skipped"
    assert "跳过" in (run["error"] or "")
    assert called is False, "用户拒绝后不该跑 Agent"


def test_timeout_skips(monkeypatch, tmp_path):
    import app.agent.tasks.interactive as it

    db = _init_env(monkeypatch, tmp_path)
    called = False

    async def fake_agent(task):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(it, "run_agent_with_user_prompt", fake_agent)
    # 1 秒过期，且不决策
    task = _make_task(db, tmp_path, interactive={"expire_seconds": 1})

    run = asyncio.run(_drive(db, task, None, expire=3))

    assert run["status"] == "skipped"
    assert "超时" in (run["error"] or "")
    assert called is False


def test_pending_flag_is_cleared_after_decision(monkeypatch, tmp_path):
    import app.agent.tasks.interactive as it

    db = _init_env(monkeypatch, tmp_path)

    async def fake_agent(task):
        return [{"role": "assistant", "content": "ok"}]

    monkeypatch.setattr(it, "run_agent_with_user_prompt", fake_agent)
    task = _make_task(db, tmp_path)

    asyncio.run(_drive(db, task, "approve"))

    after = db.get_scheduled_task(task["id"])
    assert after["pending_user_action"] is None, "卡片标记没清，前端会一直显示陈旧询问"


def test_pending_flag_cleared_on_timeout(monkeypatch, tmp_path):
    import app.agent.tasks.interactive as it

    db = _init_env(monkeypatch, tmp_path)

    async def fake_agent(task):
        return []

    monkeypatch.setattr(it, "run_agent_with_user_prompt", fake_agent)
    task = _make_task(db, tmp_path, interactive={"expire_seconds": 1})

    asyncio.run(_drive(db, task, None, expire=3))

    assert db.get_scheduled_task(task["id"])["pending_user_action"] is None


def test_agent_exception_recorded(monkeypatch, tmp_path):
    import app.agent.tasks.interactive as it

    db = _init_env(monkeypatch, tmp_path)

    async def boom(task):
        raise RuntimeError("agent down")

    monkeypatch.setattr(it, "run_agent_with_user_prompt", boom)
    task = _make_task(db, tmp_path)

    run = asyncio.run(_drive(db, task, "approve"))
    assert run["status"] == "failed"
    assert "agent down" in (run["error"] or "")


# --------------------------------------------------------------- decide 路由


def _client(monkeypatch, tmp_path):
    """起 TestClient（真实 ASGI 栈）。"""
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "api.db"))
    from app import db

    db.init_db()
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app), db


def test_decide_route_sets_event(monkeypatch, tmp_path):
    import app.agent.tasks.interactive as it

    client, db = _client(monkeypatch, tmp_path)
    project = db.create_project("p", str(tmp_path / "ws"))
    session = db.create_session("s", project["id"])
    task = db.create_scheduled_task(
        title="t", session_id=session["id"], task_type="interactive"
    )

    event = asyncio.Event()
    it._DECISIONS["ticket-1"] = event
    try:
        resp = client.post(
            f"/api/scheduled-tasks/{task['id']}/decide",
            json={"ticket": "ticket-1", "decision": "approve"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "decision": "approve"}
        assert event.is_set()
        assert it._DECISION_RESULT["ticket-1"] == "approve"
    finally:
        it._DECISIONS.pop("ticket-1", None)
        it._DECISION_RESULT.pop("ticket-1", None)


def test_decide_route_rejects_stale_ticket(monkeypatch, tmp_path):
    client, db = _client(monkeypatch, tmp_path)
    project = db.create_project("p", str(tmp_path / "ws"))
    session = db.create_session("s", project["id"])
    task = db.create_scheduled_task(
        title="t", session_id=session["id"], task_type="interactive"
    )

    resp = client.post(
        f"/api/scheduled-tasks/{task['id']}/decide",
        json={"ticket": "stale", "decision": "approve"},
    )
    assert resp.status_code == 409


def test_decide_route_unknown_task(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)
    resp = client.post(
        "/api/scheduled-tasks/nope/decide",
        json={"ticket": "t", "decision": "approve"},
    )
    assert resp.status_code == 404


def test_decide_route_rejects_bad_decision(monkeypatch, tmp_path):
    client, db = _client(monkeypatch, tmp_path)
    project = db.create_project("p", str(tmp_path / "ws"))
    session = db.create_session("s", project["id"])
    task = db.create_scheduled_task(
        title="t", session_id=session["id"], task_type="interactive"
    )
    resp = client.post(
        f"/api/scheduled-tasks/{task['id']}/decide",
        json={"ticket": "t", "decision": "maybe"},
    )
    assert resp.status_code == 422, "decision 只允许 approve / reject"
