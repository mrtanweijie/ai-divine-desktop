"""Tests for the ReAct text-mode tool calling (parser / stream filter /
middleware / config)."""

from __future__ import annotations

import json

import pytest
from langchain_core.language_models.chat_models import SimpleChatModel

from app.agent.tools.react import (
    REACT_MAX_ACTION_INPUT_LEN,
    ReActParseMiddleware,
    ReActStreamProcessor,
    _extract_json,
    _clean_react_text,
    parse_react_trace,
)
from app.agent.core import _resolve_tool_mode
from app.config import merge_model_updates, normalize_models


# --- trace parser ---------------------------------------------------------


def test_parse_full_trace():
    text = (
        "我先看看这个文件。\n"
        "Thought: 用户想看文件内容，先读取文件。\n"
        "Action: read_file\n"
        'Action Input: {"file_path": "notes/foo.md"}\n'
        "Thought: 读取成功，现在总结。\n"
        "Final Answer: 文件内容总结如下：..."
    )
    trace = parse_react_trace(text)
    assert trace is not None
    assert len(trace.thoughts) == 2
    assert trace.thoughts[0] == "用户想看文件内容，先读取文件。"
    assert len(trace.actions) == 1
    assert trace.actions[0].name == "read_file"
    assert trace.actions[0].arguments == {"file_path": "notes/foo.md"}
    assert trace.final_answer == "文件内容总结如下：..."
    assert trace.prose == ["我先看看这个文件。"]


def test_parse_inline_action():
    trace = parse_react_trace(
        'Thought: 算一下\nAction: calculator({"expression": "1+1"})\n'
        "Final Answer: 结果是 2"
    )
    assert trace is not None
    assert trace.actions[0].name == "calculator"
    assert trace.actions[0].arguments == {"expression": "1+1"}


def test_parse_plain_prose_returns_none():
    assert parse_react_trace("普通回答，没有任何工具调用") is None
    assert parse_react_trace("") is None


def test_parse_only_final_answer():
    trace = parse_react_trace("Final Answer: 完成")
    assert trace is not None
    assert trace.final_answer == "完成"
    assert not trace.actions


def test_parse_action_without_action_input():
    trace = parse_react_trace("Action: calculator\nFinal Answer: 完成")
    assert trace is not None
    assert len(trace.actions) == 1
    assert trace.actions[0].name == "calculator"
    assert trace.actions[0].arguments == {}


def test_parse_malformed_action_input_keeps_error():
    trace = parse_react_trace(
        "Action: read_file\nAction Input: 不是json\nFinal Answer: 完成"
    )
    assert trace is not None
    assert trace.actions[0].error is not None
    assert trace.actions[0].arguments == {}


def test_parse_multiple_actions():
    trace = parse_react_trace(
        'Action: a\nAction Input: {"x": 1}\nAction: b\nAction Input: {"y": 2}'
    )
    assert trace is not None
    assert [action.name for action in trace.actions] == ["a", "b"]


def test_parse_thought_continuation_lines():
    trace = parse_react_trace(
        "Thought: 第一步\n第二步\nAction: x\nAction Input: {}\nFinal Answer: 结果"
    )
    assert trace is not None
    assert trace.thoughts == ["第一步\n第二步"]


def test_clean_react_text_returns_final_answer():
    trace = parse_react_trace("Thought: t\nFinal Answer: 结论")
    assert trace is not None
    assert _clean_react_text(trace) == "结论"


# --- tolerant JSON extraction ---------------------------------------------


def test_extract_json_trailing_prose():
    args, error = _extract_json('{"a": {"b": [1, 2]}} 然后继续')
    assert error is None
    assert args == {"a": {"b": [1, 2]}}


def test_extract_json_rejects_non_object():
    args, error = _extract_json("[1, 2, 3]")
    assert error is not None
    assert args == {}


def test_extract_json_oversize():
    args, error = _extract_json('{"x": "' + "a" * (REACT_MAX_ACTION_INPUT_LEN + 1) + '"}')
    assert error is not None
    assert args == {}


# --- streaming filter -----------------------------------------------------


def _run_processor(text: str) -> list[dict[str, str]]:
    processor = ReActStreamProcessor()
    events: list[dict[str, str]] = []
    for ch in text:
        events.extend(processor.push(ch))
    events.extend(processor.flush())
    return events


def test_stream_filter_splits_thought_and_suppresses_action():
    events = _run_processor(
        'Thought: 分析中\nAction: read_file\nAction Input: {"file_path": "a.txt"}\n'
        "Final Answer: 好了"
    )
    kinds = {event["type"] for event in events}
    assert kinds <= {"think", "message"}
    text = "".join(event["content"] for event in events)
    assert "分析中" in text
    assert "好了" in text
    assert "Action" not in text
    assert "Thought" not in text


def test_stream_filter_chunk_split_tolerance():
    # Feed one character at a time — the classifier must survive arbitrary
    # token boundaries.
    events = _run_processor("Thought: 想\nAction: x\nFinal Answer: 答")
    text = "".join(event["content"] for event in events)
    think = "".join(e["content"] for e in events if e["type"] == "think")
    assert "想" in think
    assert "答" in text


def test_stream_filter_multiline_thought():
    events = _run_processor("Thought: 一\n二\nAction: x\nFinal Answer: 三")
    think = "".join(e["content"] for e in events if e["type"] == "think")
    assert "一" in think and "二" in think
    msg = "".join(e["content"] for e in events if e["type"] == "message")
    assert "三" in msg


def test_stream_filter_plain_prose_passthrough():
    events = _run_processor("你好，这是普通回答。")
    text = "".join(event["content"] for event in events)
    assert text == "你好，这是普通回答。"
    assert all(event["type"] == "message" for event in events)


def test_stream_filter_keyword_like_prose_not_misclassified():
    # "Action 是什么" has no colon — must stay visible prose.
    events = _run_processor("Action 是什么？")
    text = "".join(event["content"] for event in events)
    assert "Action 是什么" in text


# --- config plumbing ------------------------------------------------------


def test_normalize_models_tool_mode_defaults_to_auto():
    models = normalize_models([{"id": "a", "name": "A", "model": "m1"}], {})
    assert models[0]["tool_mode"] == "auto"


def test_normalize_models_tool_mode_whitelist():
    models = normalize_models(
        [
            {"id": "a", "name": "A", "model": "m1", "tool_mode": "react"},
            {"id": "b", "name": "B", "model": "m2", "tool_mode": "bogus"},
        ],
        {},
    )
    by_id = {entry["id"]: entry for entry in models}
    assert by_id["a"]["tool_mode"] == "react"
    assert by_id["b"]["tool_mode"] == "auto"


def test_merge_model_updates_keeps_tool_mode():
    stored = [{"id": "a", "name": "A", "model": "m1", "tool_mode": "react"}]
    merged = merge_model_updates(stored, [{"id": "a", "name": "A", "model": "m1"}])
    assert merged[0]["tool_mode"] == "react"


def test_resolve_tool_mode_precedence():
    settings = {
        "models": [
            {"id": "a", "name": "A", "model": "m1", "active": True},
            {"id": "b", "name": "B", "model": "m2", "tool_mode": "react"},
        ]
    }
    # auto (default) resolves to native
    assert _resolve_tool_mode(None, None, settings) == "native"
    # model entry react wins
    assert _resolve_tool_mode(None, "b", settings) == "react"
    # per-request override wins over everything
    assert _resolve_tool_mode("react", None, settings) == "react"
    assert _resolve_tool_mode("native", "b", settings) == "native"


# --- middleware -----------------------------------------------------------


class _FakeRequest:
    def __init__(self, tools) -> None:
        self.tools = tools
        self.overridden = False

    def override(self, **overrides):
        self.tools = overrides.get("tools", self.tools)
        self.overridden = True
        return self


class _FakeResponse:
    def __init__(self, messages, structured_response=None) -> None:
        self.result = messages
        self.structured_response = structured_response


def _fake_handler(message):
    def handler(request):
        return _FakeResponse([message])

    return handler


def test_middleware_strips_tools_and_rewrites_tool_calls():
    from langchain_core.messages import AIMessage

    middleware = ReActParseMiddleware()
    request = _FakeRequest(tools=["read_file"])
    message = AIMessage(
        content='Thought: 读文件\nAction: read_file\nAction Input: {"file_path": "a.txt"}',
        id="raw-1",
    )
    response = middleware.wrap_model_call(request, _fake_handler(message))
    assert getattr(request, "overridden", False)
    rewritten = response.result[0]
    assert len(rewritten.tool_calls) == 1
    call = rewritten.tool_calls[0]
    assert call["name"] == "read_file"
    assert call["args"] == {"file_path": "a.txt"}
    assert rewritten.id == "raw-1"  # think_by_id alignment


def test_middleware_strips_final_answer_prefix():
    from langchain_core.messages import AIMessage

    middleware = ReActParseMiddleware()
    message = AIMessage(
        content="Thought: 想\nFinal Answer: 结论在此",
        id="raw-2",
    )
    response = middleware.wrap_model_call(
        _FakeRequest(tools=None), _fake_handler(message)
    )
    assert response.result[0].content == "结论在此"
    assert not response.result[0].tool_calls


def test_middleware_passthrough_plain_text():
    from langchain_core.messages import AIMessage

    middleware = ReActParseMiddleware()
    message = AIMessage(content="普通回答", id="raw-3")
    response = middleware.wrap_model_call(
        _FakeRequest(tools=None), _fake_handler(message)
    )
    assert response.result[0].content == "普通回答"


def test_middleware_keeps_usage_metadata():
    from langchain_core.messages import AIMessage

    middleware = ReActParseMiddleware()
    message = AIMessage(
        content='Action: calculator\nAction Input: {"expression": "1"}',
        id="raw-4",
        usage_metadata={
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
        },
    )
    response = middleware.wrap_model_call(
        _FakeRequest(tools=None), _fake_handler(message)
    )
    rewritten = response.result[0]
    assert rewritten.usage_metadata["total_tokens"] == 15
    assert rewritten.tool_calls[0]["name"] == "calculator"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# --- full-loop integration (react middleware + real tool execution) --------


def _init_db(tmp_path, monkeypatch) -> str:
    """Point the app at an isolated DB and create a real session row, since
    tool execution persists tool_runs (FK -> sessions)."""
    data_dir = tmp_path / "data"
    workspace_dir = tmp_path / "workspace"
    db_path = tmp_path / "react.db"
    monkeypatch.setenv("DIVINE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(workspace_dir))
    monkeypatch.setenv("DB_PATH", str(db_path))

    from app import db

    db.init_db()
    return db.create_session("ReAct 测试会话")["id"]


class _ReActFakeModel:
    """A chat model that speaks the ReAct text format: first turn emits an
    action, then (after the observation) emits a Final Answer."""

    _llm_type = "react-fake"

    def bind(self, **kwargs):
        return self

    def bind_tools(self, tools, **kwargs):
        return self

    async def ainvoke(self, messages, **kwargs):
        from langchain_core.messages import AIMessage

        last = messages[-1] if messages else None
        if getattr(last, "type", "") == "tool":
            return AIMessage(content="Final Answer: 计算结果是 2")
        return AIMessage(
            content=(
                "Thought: 需要计算\n"
                "Action: calculator\n"
                'Action Input: {"expression": "1+1"}'
            )
        )


def test_react_loop_executes_tool(tmp_path, monkeypatch):
    import asyncio

    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from app.agent.core import AgentRunContext
    from app.agent.tools import _build_agent, _build_tools

    session_id = _init_db(tmp_path, monkeypatch)
    ctx = AgentRunContext(
        session_id=session_id,
        workspace=tmp_path / "workspace",
        approval_mode="ask",
        locale="zh-CN",
        tool_mode="react",
    )
    agent = _build_agent(_ReActFakeModel(), _build_tools(ctx), ctx)
    config = {"configurable": {"thread_id": session_id}, "recursion_limit": 64}

    async def run():
        return await agent.ainvoke(
            {"messages": [HumanMessage(content="用计算器算一下 1+1")]}, config
        )

    result = asyncio.run(run())
    types = [type(m).__name__ for m in result["messages"]]
    assert "ToolMessage" in types
    final = result["messages"][-1]
    assert isinstance(final, AIMessage)
    assert final.content == "计算结果是 2"
    # The observation (tool result) must have reached the model in the loop.
    observations = [
        m.content
        for m in result["messages"]
        if isinstance(m, ToolMessage)
    ]
    assert any("2" in str(content) for content in observations)


class _StreamingReActFakeModel(SimpleChatModel):
    """Streams the ReAct trace like a real chat model (token events)."""

    @property
    def _llm_type(self) -> str:
        return "react-fake-stream"

    def _call(self, messages, stop=None, run_manager=None, **kwargs):
        last = messages[-1] if messages else None
        if getattr(last, "type", "") == "tool":
            return "Final Answer: 计算结果是 2"
        return (
            "我先算一下。\n"
            "Thought: 用户要算 1+1，调用计算器。\n"
            "Action: calculator\n"
            'Action Input: {"expression": "1+1"}\n'
        )


def test_react_sse_pipeline(tmp_path, monkeypatch):
    """The SSE layer must stream Thought as think events, suppress the Action
    scaffolding, and persist the final answer via the middleware rewrite."""
    import asyncio

    from langchain_core.messages import HumanMessage

    from app.agent.core import AgentRunContext
    from app.agent.core import _stream_agent_run
    from app.agent.tools import _build_agent, _build_tools

    session_id = _init_db(tmp_path, monkeypatch)
    ctx = AgentRunContext(
        session_id=session_id,
        workspace=tmp_path / "workspace",
        approval_mode="ask",
        locale="zh-CN",
        tool_mode="react",
    )
    agent = _build_agent(
        _StreamingReActFakeModel(), _build_tools(ctx), ctx
    )
    config = {"configurable": {"thread_id": session_id}, "recursion_limit": 64}

    async def run():
        sse_payloads: list[str] = []
        final_state = None
        think_by_id = None
        async for kind, data in _stream_agent_run(
            agent,
            {"messages": [HumanMessage(content="算 1+1")]},
            config,
            react=True,
        ):
            if kind == "sse":
                sse_payloads.append(data)
            elif kind == "final_state":
                final_state, think_by_id = data
        return sse_payloads, final_state, think_by_id

    sse_payloads, final_state, think_by_id = asyncio.run(run())
    joined = "\n".join(sse_payloads)

    # Thought streams as think events; Action scaffolding never appears.
    assert "event: think" in joined
    assert "event: think_done" in joined
    assert "Action: calculator" not in joined
    assert "Action Input" not in joined
    # The real tool card still appears (adapter emits it, not the scaffold).
    assert '"tool": "calculator"' in joined
    assert '"status": "running"' in joined
    # Final answer streams as message events. B6 攒批后相邻 delta 可能
    # 合并成一帧，因此按事件类型聚合 content 后断言全文（对攒批不敏感）。
    message_text = ""
    for payload in sse_payloads:
        event_type = ""
        for line in payload.splitlines():
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:") and event_type == "message":
                data_part = line[5:].strip()
                try:
                    message_text += json.loads(data_part).get("content", "")
                except json.JSONDecodeError:
                    continue
    assert "计算结果是 2" in message_text

    # Final state: tool call + observation + rewritten final answer.
    messages = final_state["messages"]
    assert any(getattr(m, "tool_calls", None) for m in messages)
    assert any(type(m).__name__ == "ToolMessage" for m in messages)
    assert messages[-1].content == "计算结果是 2"
    # Thought captured for persistence, keyed by the message id the
    # middleware preserved.
    assert any("计算器" in think for think in think_by_id.values())



def test_cancel_disconnect_persists_partial_output(tmp_path, monkeypatch):
    """手动停止先断开 SSE 连接：run_agent 在 yield 点被 CancelledError
    拆掉时，也必须把已生成的部分输出落库。

    历史 bug：落库只挂在循环内的 cancel_event 检查上，而前端停止时
    abort 连接先于 cancel 接口到达，生成器在 yield 点被拆、检查永远
    走不到 → 刷新后看不到被终止的输出。
    """
    import asyncio

    from app import db
    from app.agent import orchestrator

    session_id = _init_db(tmp_path, monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    monkeypatch.setattr(
        orchestrator, "_build_llm", lambda **kw: _StreamingReActFakeModel()
    )

    async def run() -> str:
        gen = orchestrator.run_agent(
            session_id,
            [{"role": "user", "content": "算 1+1"}],
            think=False,
            workspace=workspace,
            approval_mode="ask",
            tool_mode="react",
        )
        streamed = ""
        try:
            async for event in gen:
                if event.startswith("event: message"):
                    data = json.loads(
                        next(
                            line[5:].strip()
                            for line in event.splitlines()
                            if line.startswith("data:")
                        )
                    )
                    streamed += str(data.get("content") or "")
                if "我先算一下" in streamed:
                    # 模拟客户端断连：Starlette 在生成器 yield 点抛 CancelledError
                    await gen.athrow(asyncio.CancelledError())
        except asyncio.CancelledError:
            pass
        return streamed

    streamed = asyncio.run(run())
    assert "我先算一下" in streamed

    rows = db.list_messages(session_id)
    assistant = [m for m in rows if m["role"] == "assistant"]
    assert assistant, "断连取消后必须持久化部分输出"
    assert "我先算一下" in assistant[-1]["content"]


def test_recursion_limit_persists_partial_output(tmp_path, monkeypatch):
    """撞上 GraphRecursionError 时，已流出的部分内容必须落库。

    历史 bug：该路径只 abort_todos 就返回，用户做了大半的工作在
    刷新后丢失（与手动停止断连同款漏洞）。
    """
    import asyncio

    from langgraph.errors import GraphRecursionError

    from app import db
    from app.agent import orchestrator
    from app.agent.core.sse import sse_event

    session_id = _init_db(tmp_path, monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    monkeypatch.setattr(orchestrator, "_build_llm", lambda **kw: object())

    class _StubAgent:
        async def aget_state(self, config):
            class _Snapshot:
                values = {}
            return _Snapshot()

    monkeypatch.setattr(orchestrator, "_build_agent", lambda *a, **k: _StubAgent())

    async def fake_stream(*args, **kwargs):
        yield "sse", sse_event("message", {"content": "已经完成了一半的分析。"})
        raise GraphRecursionError("recursion limit reached")

    monkeypatch.setattr(orchestrator, "_stream_agent_run", fake_stream)

    async def run():
        agen = orchestrator.run_agent(
            session_id,
            [{"role": "user", "content": "做个大任务"}],
            think=False,
            workspace=workspace,
            approval_mode="ask",
            tool_mode="default",
        )
        async for _ in agen:
            pass

    asyncio.run(run())
    rows = db.list_messages(session_id)
    assistant = [m for m in rows if m["role"] == "assistant"]
    assert assistant, "撞限后必须持久化已生成的部分输出"
    assert "一半" in assistant[-1]["content"]


def test_model_error_persists_tool_turn_and_partial_output(tmp_path, monkeypatch):
    """模型侧异常（如 429 限流）时，已流出的内容必须落库。

    历史 bug：异常兜底只覆盖 GraphRecursionError 与断连取消；429 穿透到
    chat 层只发 server_error，本轮已渲染的工具轮次与正文刷新即丢。
    工具轮次从 checkpointer 快照捞回，正文只补快照之外的尾部（防双写）。
    """
    import asyncio

    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from app import db
    from app.agent import orchestrator
    from app.agent.core.sse import sse_event

    session_id = _init_db(tmp_path, monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)

    thread_messages = [
        HumanMessage(content="做个分析"),
        AIMessage(
            content="",
            tool_calls=[
                {"id": "c1", "name": "calculator", "args": {}, "type": "tool_call"}
            ],
        ),
        ToolMessage(content="ok", tool_call_id="c1", name="calculator"),
    ]

    class _StubAgent:
        async def aget_state(self, config):
            class _Snapshot:
                values = {"messages": list(thread_messages)}

            return _Snapshot()

    monkeypatch.setattr(orchestrator, "_build_llm", lambda **kw: object())
    monkeypatch.setattr(orchestrator, "_build_agent", lambda *a, **k: _StubAgent())

    async def fake_stream(*args, **kwargs):
        yield "sse", sse_event("message", {"content": "我来为您生成分析："})
        raise RuntimeError("Error code: 429 - 该模型当前访问量过大")

    monkeypatch.setattr(orchestrator, "_stream_agent_run", fake_stream)

    async def run():
        agen = orchestrator.run_agent(
            session_id,
            [{"role": "user", "content": "做个分析"}],
            think=False,
            workspace=workspace,
            approval_mode="ask",
            tool_mode="default",
        )
        with pytest.raises(RuntimeError):
            async for _ in agen:
                pass

    asyncio.run(run())
    rows = db.list_messages(session_id)
    assert any(m["role"] == "tool" for m in rows), "工具结果必须从快照落库"
    contents = [m["content"] for m in rows if m["role"] == "assistant"]
    assert any("我来为您生成分析" in c for c in contents), "正文必须落库"
    assert sum("我来为您生成分析" in c for c in contents) == 1, "正文不得双写"
