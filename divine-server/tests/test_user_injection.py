"""用户插话（steering）注入链路测试：队列 / 中间件 / 端点。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException


@pytest.fixture
def dirs():
    """沙箱环境下 pytest 的 pytest-of-* 根目录可能 EEXIST，用 tempfile 兜底。"""
    import shutil
    import tempfile
    root = Path(tempfile.mkdtemp(prefix="divine-inject-test-"))
    yield root
    shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# 队列
# ---------------------------------------------------------------------------


def test_queue_enqueue_drain_roundtrip():
    from app.agent.core import injection

    injection.discard_injections("s1")
    assert injection.enqueue_injection("s1", "补充一")
    assert injection.enqueue_injection("s1", "补充二")
    assert injection.pending_count("s1") == 2

    items = injection.drain_injections("s1")
    assert items == ["补充一", "补充二"]
    # drain 即消费即删除
    assert injection.pending_count("s1") == 0
    assert injection.drain_injections("s1") == []


def test_queue_session_isolation():
    from app.agent.core import injection

    injection.discard_injections("s1")
    injection.discard_injections("s2")
    injection.enqueue_injection("s1", "只给 s1")
    assert injection.drain_injections("s2") == []
    assert injection.drain_injections("s1") == ["只给 s1"]


def test_queue_full_rejects():
    from app.agent.core import injection

    injection.discard_injections("full")
    for index in range(injection.MAX_PENDING_INJECTIONS):
        assert injection.enqueue_injection("full", f"m{index}")
    assert not injection.enqueue_injection("full", "溢出")
    assert injection.pending_count("full") == injection.MAX_PENDING_INJECTIONS
    injection.discard_injections("full")
    assert injection.pending_count("full") == 0


def test_discard_clears_without_consuming():
    from app.agent.core import injection

    injection.enqueue_injection("dead", "迟到的插话")
    injection.discard_injections("dead")
    assert injection.pending_count("dead") == 0


# ---------------------------------------------------------------------------
# 中间件
# ---------------------------------------------------------------------------


def _make_middleware(session_id: str):
    from app.agent.core.context import AgentRunContext
    from app.agent.middleware import UserInjectionMiddleware

    ctx = AgentRunContext(
        session_id=session_id,
        workspace=Path("/tmp"),
        approval_mode="ask",
    )
    return UserInjectionMiddleware(ctx)


def test_middleware_empty_queue_returns_none():
    from app.agent.core import injection

    injection.discard_injections("mw1")
    middleware = _make_middleware("mw1")
    assert asyncio.run(middleware.abefore_model({}, runtime=None)) is None


def test_middleware_injects_human_messages_and_consumes():
    from langchain_core.messages import HumanMessage

    from app.agent.core import injection

    injection.discard_injections("mw2")
    injection.enqueue_injection("mw2", "补充 A")
    injection.enqueue_injection("mw2", "补充 B")

    middleware = _make_middleware("mw2")
    update = asyncio.run(middleware.abefore_model({}, runtime=None))
    assert update is not None
    messages = update["messages"]
    assert [m.content for m in messages] == ["补充 A", "补充 B"]
    assert all(isinstance(m, HumanMessage) for m in messages)
    # 消费即删除：下一次模型调用不再注入
    assert asyncio.run(middleware.abefore_model({}, runtime=None)) is None


# ---------------------------------------------------------------------------
# 端点（直接调用 endpoint 函数：沙箱环境下 pytest + TestClient 会被 SIGTERM，
# 裸调 FastAPI endpoint 与线上行为一致且绕开该环境问题）
# ---------------------------------------------------------------------------


def _setup_db(monkeypatch, dirs) -> None:
    monkeypatch.setenv("DIVINE_DATA_DIR", str(dirs / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(dirs / "workspace"))
    monkeypatch.setenv("DB_PATH", str(dirs / "smoke.db"))

    from app import db

    db.init_db()


def test_inject_rejects_without_active_stream(monkeypatch, dirs):
    import pytest as _pytest

    from app.api.chat import _CANCEL_EVENTS, inject_message
    from app.agent.core import injection
    from app.schemas import InjectRequest

    _setup_db(monkeypatch, dirs)
    session = _create_session()
    _CANCEL_EVENTS.pop(session["id"], None)
    injection.discard_injections(session["id"])

    with _pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            inject_message(session["id"], InjectRequest(content="补充"))
        )
    assert exc_info.value.status_code == 409
    assert injection.pending_count(session["id"]) == 0


def test_inject_enqueues_and_persists_with_marker(monkeypatch, dirs):
    from app import db
    from app.api.chat import _CANCEL_EVENTS, inject_message
    from app.agent.core import injection
    from app.schemas import InjectRequest

    _setup_db(monkeypatch, dirs)
    sid = _create_session()["id"]
    injection.discard_injections(sid)
    _CANCEL_EVENTS[sid] = asyncio.Event()
    try:
        result = asyncio.run(
            inject_message(sid, InjectRequest(content="配色改成蓝绿"))
        )
        assert result == {"ok": True}
        assert injection.drain_injections(sid) == ["配色改成蓝绿"]

        messages = db.list_messages(sid)
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == (
            f"{injection.SUPPLEMENT_PREFIX} 配色改成蓝绿"
        )
    finally:
        _CANCEL_EVENTS.pop(sid, None)
        injection.discard_injections(sid)


def test_inject_validates_content_and_session(monkeypatch, dirs):
    import pytest as _pytest

    from app.api.chat import inject_message
    from app.schemas import InjectRequest

    _setup_db(monkeypatch, dirs)
    sid = _create_session()["id"]

    # 空内容
    with _pytest.raises(HTTPException) as empty_error:
        asyncio.run(inject_message(sid, InjectRequest(content="   ")))
    assert empty_error.value.status_code == 400

    # 会话不存在
    with _pytest.raises(HTTPException) as missing_error:
        asyncio.run(
            inject_message("not-exist", InjectRequest(content="补充"))
        )
    assert missing_error.value.status_code == 404


def _create_session() -> dict:
    from app import db

    project = db.create_project("插话测试", "/tmp")
    return db.create_session("插话会话", project["id"])
