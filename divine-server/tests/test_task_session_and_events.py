"""任务专属会话 + 全局事件广播（design 027 收尾）。

覆盖四件事：
1. ``app.events`` 的订阅 / 广播 / SSE 报文格式；
2. ``common.ensure_task_session`` 懒创建会话并**写回** session_id（否则每次执行
   都会新建会话，侧栏会被刷屏）；
3. API 创建任务时自动建专属会话——agent 类建、reminder 不建；
4. ``webhook`` 在 Agent 无产出时**不投递**（防空消息 + 误报 succeeded）。
"""

from __future__ import annotations

import asyncio
import json

import httpx

from app import events


def _init_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "sessions_events.db"))
    from app import db

    db.init_db()
    return db


# --------------------------------------------------------------------------
# 1. events 广播
# --------------------------------------------------------------------------


def test_format_sse_shape():
    text = events.format_sse("sessions_changed", {"reason": "task_run"})
    assert text.startswith("event: sessions_changed\n")
    assert text.endswith("\n\n")
    payload = text.split("data: ", 1)[1].strip()
    assert json.loads(payload) == {"reason": "task_run"}


def test_broadcast_reaches_subscriber_then_unsubscribe_stops():
    async def scenario():
        queue = events.subscribe()
        try:
            events.broadcast("sessions_changed", {"n": 1})
            message = await asyncio.wait_for(queue.get(), timeout=1)
            assert "event: sessions_changed" in message
            assert json.loads(message.split("data: ", 1)[1].strip()) == {"n": 1}

            events.unsubscribe(queue)
            assert events.subscriber_count() == 0

            # 退订后不该再收到任何东西
            events.broadcast("sessions_changed", {"n": 2})
            assert queue.empty()
        finally:
            events.unsubscribe(queue)

    asyncio.run(scenario())


def test_broadcast_without_subscribers_is_noop():
    assert events.subscriber_count() == 0
    # 无订阅者时广播必须是安全的空操作
    events.broadcast("sessions_changed", {"n": 1})


def test_queue_full_drops_oldest_not_newest():
    async def scenario():
        queue = events.subscribe()
        try:
            # 灌满队列再多投一条，最新一条必须还在
            for i in range(105):
                events.broadcast("sessions_changed", {"n": i})
            latest = None
            while not queue.empty():
                latest = queue.get_nowait()
            assert latest is not None
            assert json.loads(latest.split("data: ", 1)[1].strip())["n"] == 104
        finally:
            events.unsubscribe(queue)

    asyncio.run(scenario())


# --------------------------------------------------------------------------
# 2. ensure_task_session：懒创建 + 写回
# --------------------------------------------------------------------------


def test_ensure_task_session_creates_and_persists(monkeypatch, tmp_path):
    db = _init_env(monkeypatch, tmp_path)
    from app.agent.tasks.common import ensure_task_session

    task = db.create_scheduled_task(
        title="每日简报", task_type="agent", description="总结今天的邮件"
    )
    assert task["session_id"] is None

    session_id = ensure_task_session(task)
    assert session_id
    session = db.get_session(session_id)
    assert session is not None
    assert "每日简报" in session["title"]

    # 关键：必须写回任务，第二次调用复用同一个会话而不是再建一个
    reloaded = db.get_scheduled_task(task["id"])
    assert reloaded["session_id"] == session_id
    assert ensure_task_session(reloaded) == session_id
    assert len(db.list_sessions()) == 1


def test_ensure_task_session_reuses_existing(monkeypatch, tmp_path):
    db = _init_env(monkeypatch, tmp_path)
    from app.agent.tasks.common import ensure_task_session

    project = db.create_project("p", str(tmp_path / "ws"))
    session = db.create_session("已有会话", project["id"])
    task = db.create_scheduled_task(
        title="t", task_type="agent", session_id=session["id"]
    )

    assert ensure_task_session(task) == session["id"]
    assert len(db.list_sessions()) == 1, "已有会话时不该新建"


# --------------------------------------------------------------------------
# 3. API 创建任务时自动建专属会话
# --------------------------------------------------------------------------


def test_api_creates_dedicated_session_for_agent_task(monkeypatch, tmp_path):
    db = _init_env(monkeypatch, tmp_path)
    from app.api.scheduled_tasks import create_scheduled_task
    from app.schemas import ScheduledTaskCreate

    task = create_scheduled_task(
        ScheduledTaskCreate(
            title="每日简报", task_type="agent", prompt="总结今天的邮件"
        )
    )

    assert task["session_id"], "agent 任务必须自动带上会话"
    session = db.get_session(task["session_id"])
    assert session is not None
    assert "每日简报" in session["title"]


def test_api_does_not_create_session_for_reminder(monkeypatch, tmp_path):
    db = _init_env(monkeypatch, tmp_path)
    from app.api.scheduled_tasks import create_scheduled_task
    from app.schemas import ScheduledTaskCreate

    task = create_scheduled_task(
        ScheduledTaskCreate(title="喝水提醒", task_type="reminder")
    )

    assert task["session_id"] is None, "reminder 只提醒、不跑 Agent，不该建会话"
    assert db.list_sessions() == []


def test_api_broadcasts_sessions_changed(monkeypatch, tmp_path):
    _init_env(monkeypatch, tmp_path)
    from app.api.scheduled_tasks import create_scheduled_task
    from app.schemas import ScheduledTaskCreate

    seen: list[dict] = []
    monkeypatch.setattr(
        events, "broadcast", lambda name, data=None: seen.append({"name": name, **(data or {})})
    )

    create_scheduled_task(ScheduledTaskCreate(title="周报", task_type="agent"))

    assert seen and seen[0]["name"] == "sessions_changed"
    assert seen[0]["reason"] == "task_created"


# --------------------------------------------------------------------------
# 4. webhook 空内容不投递
# --------------------------------------------------------------------------


def _install_feishu(monkeypatch) -> dict:
    from app.agent.tasks import delivery
    from app.agent.tasks.channels import FeishuChannel

    sent = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        sent["count"] += 1
        return httpx.Response(200, json={"code": 0})

    monkeypatch.setattr(
        delivery,
        "_REGISTRY",
        {"feishu": FeishuChannel(transport=httpx.MockTransport(handler))},
    )
    return sent


def test_webhook_skips_delivery_when_agent_outputs_nothing(monkeypatch, tmp_path):
    db = _init_env(monkeypatch, tmp_path)
    import app.agent.tasks.webhook as wh

    sent = _install_feishu(monkeypatch)

    async def empty_agent(task):
        return []  # 会话不可用等情况下 Agent 没有任何产出

    monkeypatch.setattr(wh, "run_agent_with_user_prompt", empty_agent)

    project = db.create_project("p", str(tmp_path / "ws"))
    session = db.create_session("s", project["id"])
    task = db.create_scheduled_task(
        title="每日热点",
        session_id=session["id"],
        task_type="webhook",
        prompt="收集新闻",
        delivery={"channels": [{"type": "feishu", "webhook_url": "https://f/h"}]},
    )

    asyncio.run(wh.run_webhook_task(task))

    run = db.list_runs_for_task(task["id"])[0]
    assert run["status"] == "skipped", "空内容应标 skipped 而不是 succeeded"
    assert sent["count"] == 0, "空内容绝不能真的发到频道"


# --------------------------------------------------------------------------
# 5. 归属项目：取「列表第一个」，不是 default_project() 的最早创建那个
# --------------------------------------------------------------------------


def test_task_session_uses_first_project_not_earliest(monkeypatch, tmp_path):
    db = _init_env(monkeypatch, tmp_path)
    from app.api.scheduled_tasks import create_scheduled_task
    from app.schemas import ScheduledTaskCreate

    earliest = db.create_project("最早建的", str(tmp_path / "old"))
    listed_first = db.create_project("列表第一个", str(tmp_path / "first"))

    # 钉住 first_project 的返回值：updated_at 精度到秒，两个项目同秒创建时
    # 排序不确定，直接依赖真实排序会让这条测试变脆。
    monkeypatch.setattr(db, "first_project", lambda: listed_first)

    task = create_scheduled_task(ScheduledTaskCreate(title="日报", task_type="agent"))
    session = db.get_session(task["session_id"])

    assert session["project_id"] == listed_first["id"]
    assert session["project_id"] != earliest["id"], "不该落到最早创建的项目"


def test_lazy_ensure_task_session_also_uses_first_project(monkeypatch, tmp_path):
    db = _init_env(monkeypatch, tmp_path)
    from app.agent.tasks.common import ensure_task_session

    earliest = db.create_project("最早建的", str(tmp_path / "old"))
    listed_first = db.create_project("列表第一个", str(tmp_path / "first"))
    monkeypatch.setattr(db, "first_project", lambda: listed_first)

    task = db.create_scheduled_task(title="周报", task_type="agent")
    session = db.get_session(ensure_task_session(task))

    assert session["project_id"] == listed_first["id"]
    assert session["project_id"] != earliest["id"]


def test_first_project_matches_sidebar_order(monkeypatch, tmp_path):
    """first_project() 必须与 list_projects() 的首项一致（侧栏顺序）。

    注意：``init_db()`` 自己就会建一个默认项目，所以这里不假设「初始无项目」。
    """
    db = _init_env(monkeypatch, tmp_path)

    db.create_project("A", str(tmp_path / "a"))
    db.create_project("B", str(tmp_path / "b"))

    projects = db.list_projects()
    assert projects, "至少应有一个项目"
    assert db.first_project()["id"] == projects[0]["id"]


# --------------------------------------------------------------------------
# 6. /api/events 端点（直接测响应与生成器，不走 TestClient 流式）
# --------------------------------------------------------------------------


def test_events_endpoint_response_config(monkeypatch, tmp_path):
    """端点必须回 text/event-stream 且带防缓冲头。

    ⚠️ 这里**故意不用** TestClient 去 stream 这个端点：它的生成器是无限的，
    TestClient 关闭响应时会阻塞（实测把整个测试挂死 7 分钟）。
    直接调 handler 拿 StreamingResponse 才是确定性的。
    """
    _init_env(monkeypatch, tmp_path)
    from app.api.events import stream_events

    response = asyncio.run(stream_events())

    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"


def test_events_generator_emits_ready_then_releases_subscriber(monkeypatch, tmp_path):
    """首帧是 ready；生成器关闭后订阅者必须被回收。"""
    _init_env(monkeypatch, tmp_path)
    from app.api.events import stream_events

    async def scenario():
        response = await stream_events()
        generator = response.body_iterator
        # 订阅发生在生成器内部：没开始迭代就不该占槽位（否则响应不被迭代时泄漏）
        assert events.subscriber_count() == 0, "未开始迭代时不该注册订阅者"
        try:
            first = await generator.__anext__()
            assert "event: ready" in first
            assert events.subscriber_count() == 1, "迭代开始后应注册订阅者"
        finally:
            await generator.aclose()
        assert events.subscriber_count() == 0, "生成器关闭后必须回收订阅者"

    asyncio.run(scenario())


def test_events_generator_forwards_broadcast(monkeypatch, tmp_path):
    """广播的事件必须从生成器里流出来（前端就是靠这个刷新会话列表）。"""
    _init_env(monkeypatch, tmp_path)
    from app.api.events import stream_events

    async def scenario():
        response = await stream_events()
        generator = response.body_iterator
        try:
            await generator.__anext__()  # ready 帧
            events.broadcast("sessions_changed", {"reason": "task_run"})
            frame = await asyncio.wait_for(generator.__anext__(), timeout=2)
            assert "event: sessions_changed" in frame
            assert '"reason": "task_run"' in frame
        finally:
            await generator.aclose()

    asyncio.run(scenario())
