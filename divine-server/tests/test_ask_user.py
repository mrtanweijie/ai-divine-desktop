"""ask_user（agent 主动问）测试。

覆盖：工具注册、SSE 事件形状、execution 特判（答案回传/每轮一次/超时降级）、
/chat/answer 端点（直接调用 endpoint 函数——沙箱下 pytest+TestClient 会被
SIGTERM，与 test_user_injection.py 相同的绕行策略）。
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def dirs():
    """沙箱环境下 pytest 的 tmp_path 目录可能被拦截，用 tempfile 兜底。"""
    root = Path(tempfile.mkdtemp(prefix="divine-ask-test-"))
    yield root
    shutil.rmtree(root, ignore_errors=True)


def _make_ctx(session_id: str = "ask-ctx"):
    from app.agent.core.context import AgentRunContext

    return AgentRunContext(
        session_id=session_id,
        workspace=Path("/tmp"),
        approval_mode="ask",
    )


def _setup_db(monkeypatch, dirs) -> None:
    monkeypatch.setenv("DIVINE_DATA_DIR", str(dirs / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(dirs / "workspace"))
    monkeypatch.setenv("DB_PATH", str(dirs / "smoke.db"))

    from app import db

    db.init_db()


def _create_session() -> dict:
    from app import db

    project = db.create_project("ask 测试", "/tmp")
    return db.create_session("ask 会话", project["id"])


# ---------------------------------------------------------------------------
# 注册与 SSE 事件形状
# ---------------------------------------------------------------------------


def test_ask_user_tool_registered_with_schema():
    from app.tools.registry import get_tool

    tool = get_tool("ask_user")
    assert tool is not None
    props = tool.parameters["properties"]
    assert "question" in props
    assert props["input_type"]["enum"] == ["text", "single_choice"]
    assert "options" in props


def test_ask_user_in_readonly_and_noplan_whitelists():
    from app.agent.core.constants import _NO_PLAN_TOOLS, _READ_ONLY_TOOLS

    assert "ask_user" in _READ_ONLY_TOOLS
    assert "ask_user" in _NO_PLAN_TOOLS


def test_interrupt_sse_ask_user_shape():
    from app.agent.core.sse import _interrupt_sse

    out = _interrupt_sse(
        {
            "type": "ask_user",
            "session_id": "s1",
            "call_id": "c1",
            "question": "配色选哪个？",
            "options": ["蓝", "绿"],
            "input_type": "single_choice",
        }
    )
    # event:tool + JSON payload
    assert out.startswith("event: tool")
    assert "confirm_type" in out and '"ask_user"' in out
    assert '"question"' in out and "配色选哪个" in out
    assert '"options"' in out and "蓝" in out
    assert '"input_type"' in out and "single_choice" in out
    assert '"call_id"' in out


# ---------------------------------------------------------------------------
# execution 特判：答案回传 / 每轮一次 / 超时降级
# ---------------------------------------------------------------------------


def test_handle_ask_user_returns_answer(monkeypatch):
    from app.agent.tools import execution

    events: list[dict] = []
    writer = lambda event: events.append(event)  # noqa: E731

    def fake_interrupt(session_id, marker, payload):
        # 与 interrupts._ask_interrupt 一致：同步函数（langgraph interrupt 原语）
        assert payload["type"] == "ask_user"
        assert payload["question"] == "配色改什么？"
        assert payload["options"] == ["蓝绿", "深蓝"]
        assert payload["input_type"] == "single_choice"
        assert payload["call_id"] == "call_x"
        return {"allowed": True, "answer": "蓝绿"}

    monkeypatch.setattr(execution, "_ask_interrupt", fake_interrupt)
    ctx = _make_ctx()

    result = asyncio.run(
        execution._handle_ask_user(
            ctx, None, "ask_user", {"question": "配色改什么？",
                                    "options": ["蓝绿", "深蓝"],
                                    "input_type": "single_choice"},
            "call_x", writer,
        )
    )
    assert result == "蓝绿"
    assert ctx.ask_user_count == 1
    done = [e for e in events if e["status"] == "done"]
    assert done and done[0]["messageKey"] == "tool.askUserAnswered"


def test_handle_ask_user_hard_limit_once(monkeypatch):
    from app.agent.tools import execution

    calls: list[str] = []

    def fake_interrupt(session_id, marker, payload):
        calls.append(marker)
        return {"answer": "ok"}

    monkeypatch.setattr(execution, "_ask_interrupt", fake_interrupt)
    ctx = _make_ctx()

    async def run():
        events: list[dict] = []
        writer = lambda event: events.append(event)  # noqa: E731
        first = await execution._handle_ask_user(
            ctx, None, "ask_user", {"question": "问什么？"}, "c1", writer
        )
        second = await execution._handle_ask_user(
            ctx, None, "ask_user", {"question": "再问一次？"}, "c2", writer
        )
        return first, second

    first, second = asyncio.run(run())
    assert first == "ok"
    assert len(calls) == 1  # 第二次不再 interrupt
    assert "本轮已向用户提问过" in second


def test_handle_ask_user_timeout_fallback(monkeypatch):
    from app.agent.tools import execution

    def fake_interrupt(session_id, marker, payload):
        # 180s 超时 → orchestrator resume {"allowed": True, "answer": None}
        return {"allowed": True, "answer": None}

    monkeypatch.setattr(execution, "_ask_interrupt", fake_interrupt)
    ctx = _make_ctx()
    events: list[dict] = []

    result = asyncio.run(
        execution._handle_ask_user(
            ctx, None, "ask_user", {"question": "问什么？"}, "c1",
            lambda e: events.append(e),
        )
    )
    assert result == execution._ASK_USER_FALLBACK
    timeout = [e for e in events if e.get("messageKey") == "tool.askUserTimeout"]
    assert timeout


def test_handle_ask_user_skipped_in_full_mode(monkeypatch):
    """定时任务/完全访问模式无人在线：直接跳过提问，不 interrupt。"""
    from app.agent.tools import execution

    calls: list[str] = []

    def fake_interrupt(session_id, marker, payload):
        calls.append(marker)
        return {"answer": "ok"}

    monkeypatch.setattr(execution, "_ask_interrupt", fake_interrupt)
    from app.agent.core.context import AgentRunContext

    ctx = AgentRunContext(
        session_id="full-ctx",
        workspace=Path("/tmp"),
        approval_mode="full",
    )
    result = asyncio.run(
        execution._handle_ask_user(ctx, None, "ask_user",
                                   {"question": "问什么？"}, "c1", lambda e: None)
    )
    assert calls == []
    assert "自动执行模式" in result
    assert ctx.ask_user_count == 0


def test_handle_ask_user_replay_after_resume(monkeypatch):
    """langgraph 对工具内 interrupt 的 resume = 整体重放：同 marker 仍存活时
    必须放行到 interrupt() 消费 resume 值，不能命中"本轮已问过"守卫。"""
    from app.agent.tools import execution
    from app.agent.tools.interrupts import _ACTIVE_INTERRUPTS

    calls: list[str] = []
    ctx = _make_ctx("replay-ctx")

    def fake_interrupt(session_id, marker, payload):
        calls.append(marker)
        # 模拟真实 _ask_interrupt：pause 期间 marker 存活
        _ACTIVE_INTERRUPTS.add((session_id, marker))
        return {"answer": "BLUE"}

    monkeypatch.setattr(execution, "_ask_interrupt", fake_interrupt)
    # 第一次调用：正常 interrupt
    first = asyncio.run(
        execution._handle_ask_user(ctx, None, "ask_user",
                                   {"question": "问什么？"}, "c1", lambda e: None)
    )
    assert first == "BLUE"
    assert ctx.ask_user_count == 1
    # 模拟 resume 后的整体重放：marker 仍存活、计数已为 1
    # → 应放行而非返回"已问过"提示
    second = asyncio.run(
        execution._handle_ask_user(ctx, None, "ask_user",
                                   {"question": "问什么？"}, "c1", lambda e: None)
    )
    assert second == "BLUE", "重放应消费 resume 值而非被守卫拦截"
    assert ctx.ask_user_count == 2  # 重放再计数无害（守卫只看 >0）
    # 而新的 call_id（真正第二次提问）仍被拦截
    third = asyncio.run(
        execution._handle_ask_user(ctx, None, "ask_user",
                                   {"question": "再问？"}, "c2", lambda e: None)
    )
    assert "本轮已向用户提问过" in third
    assert len(calls) == 2  # 两次 interrupt（初调 + 重放），第三次被拦截
    _ACTIVE_INTERRUPTS.discard(("replay-ctx", "ask_user:c1"))


def test_handle_ask_user_truncates_long_answer(monkeypatch):
    from app.agent.tools import execution

    def fake_interrupt(session_id, marker, payload):
        return {"answer": "长" * 5000}

    monkeypatch.setattr(execution, "_ask_interrupt", fake_interrupt)
    result = asyncio.run(
        execution._handle_ask_user(_make_ctx(), None, "ask_user",
                                   {"question": "问什么？"}, "c1", lambda e: None)
    )
    assert len(result) <= 2001  # 2000 + 省略号


# ---------------------------------------------------------------------------
# 端点：/chat/answer（直接调用 endpoint 函数）
# ---------------------------------------------------------------------------


def test_answer_route_resolves_pending(monkeypatch, dirs):
    from app.api.chat import answer_question
    from app.api.terminal import (
        _PENDING_TERMINAL,
        create_terminal_decision,
        remove_terminal_decision,
    )
    from app.schemas import ChatAnswer

    _setup_db(monkeypatch, dirs)
    sid = _create_session()["id"]
    create_terminal_decision(sid)
    try:
        result = asyncio.run(
            answer_question(ChatAnswer(session_id=sid, call_id="c1", answer="蓝绿"))
        )
        assert result == {"ok": True}
        pending = _PENDING_TERMINAL[sid]
        assert pending["answer"] == "蓝绿"
        assert pending["allowed"] is True
        assert pending["event"].is_set()
    finally:
        remove_terminal_decision(sid)


def test_answer_route_409_without_pending(monkeypatch, dirs):
    import pytest as _pytest
    from fastapi import HTTPException

    from app.api.chat import answer_question
    from app.api.terminal import remove_terminal_decision
    from app.schemas import ChatAnswer

    _setup_db(monkeypatch, dirs)
    sid = _create_session()["id"]
    remove_terminal_decision(sid)
    with _pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            answer_question(ChatAnswer(session_id=sid, call_id="c1", answer="蓝绿"))
        )
    assert exc_info.value.status_code == 409


def test_answer_route_404_missing_session(monkeypatch, dirs):
    import pytest as _pytest
    from fastapi import HTTPException

    from app.api.chat import answer_question
    from app.schemas import ChatAnswer

    _setup_db(monkeypatch, dirs)
    with _pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            answer_question(ChatAnswer(session_id="nope", call_id="c1", answer="x"))
        )
    assert exc_info.value.status_code == 404


def test_decide_terminal_semantics_unchanged(monkeypatch, dirs):
    """回归：二元审批通道（terminal/decide 路径）行为不被 answer 槽位影响。"""
    from app.api.terminal import (
        TerminalDecision,
        create_terminal_decision,
        decide_terminal,
        remove_terminal_decision,
    )

    _setup_db(monkeypatch, dirs)
    sid = _create_session()["id"]
    create_terminal_decision(sid)
    try:
        result = asyncio.run(
            decide_terminal(TerminalDecision(session_id=sid, allow=False))
        )
        assert result == {"ok": True, "allow": False}
    finally:
        remove_terminal_decision(sid)
