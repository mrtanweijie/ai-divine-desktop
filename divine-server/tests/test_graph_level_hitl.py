"""Graph-level HITL integration tests (real agent graph, scripted model).

Covers the two flows that unit tests only probe piecewise:
1. ask_user: model calls ask_user -> tool node interrupts -> we resume with a
   user answer (Command(resume)) -> the answer arrives back as the tool result
   in the next model invocation.
2. user steering: UserInjectionMiddleware drains the per-session queue at the
   next model call and the injected HumanMessages are visible in the model
   input within a real agent run.

Uses the production builder (_build_agent / _build_tools) with a scripted
chat model, so no API calls are made. Requires no DB: both flows never touch
sessions/todos.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.types import Command


class RecordingChatModel(BaseChatModel):
    """Replays scripted AIMessages; records every model input for asserts."""

    responses: list
    cursor: int = 0
    seen: list[list[dict]] = []

    @property
    def _llm_type(self) -> str:
        return "divine_test_scripted"

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001, ANN202
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ANN001, ANN202
        self.seen.append(
            [
                {
                    "role": (
                        getattr(message, "type", "?")
                        .replace("human", "user")
                        .replace("ai", "assistant")
                    ),
                    "content": str(getattr(message, "content", "")),
                }
                for message in messages
            ]
        )
        index = min(self.cursor, len(self.responses) - 1)
        self.cursor += 1
        return ChatResult(
            generations=[ChatGeneration(message=self.responses[index])]
        )


@pytest.fixture
def ctx_dirs():
    root = Path(tempfile.mkdtemp(prefix="divine-hitl-test-"))
    yield root
    shutil.rmtree(root, ignore_errors=True)


def _make_ctx(workspace: Path, approval_mode: str = "ask"):
    from app.agent.core.context import AgentRunContext

    return AgentRunContext(
        session_id=f"hitl-{uuid.uuid4().hex[:8]}",
        workspace=workspace,
        approval_mode=approval_mode,
        plan_choice_resolved=True,  # 跳过 plan_choice 门，聚焦 HITL 本身
    )


def _build_agent(ctx, llm, tool_names: set[str]):
    from langchain_core.tools import StructuredTool

    from app.agent.tools import execution
    from app.agent.tools.tools import _build_agent, _make_args_model, _make_tool_call
    from app.tools.registry import get_tool

    wrapped: list[StructuredTool] = []
    for name in tool_names:
        adapter = get_tool(name)
        if adapter is None:
            continue
        wrapped.append(
            StructuredTool.from_function(
                coroutine=_make_tool_call(ctx, adapter, name, None),
                name=name,
                description=adapter.description,
                args_schema=_make_args_model(name, adapter.parameters),
            )
        )
    return _build_agent(llm, wrapped, ctx)


# ---------------------------------------------------------------------------
# ask_user 全链路：模型调用 → interrupt → 答案 resume → 回到模型
# ---------------------------------------------------------------------------


def test_ask_user_full_loop_answer_reaches_model(ctx_dirs):
    from app.agent.tools.tools import reset_agent_thread

    ctx = _make_ctx(ctx_dirs)
    thread_id = f"ask-e2e-{uuid.uuid4().hex}"

    model = RecordingChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ask_user",
                        "args": {
                            "question": "配色用哪种？",
                            "options": ["蓝绿", "深蓝"],
                            "input_type": "single_choice",
                        },
                        "id": "ask_e2e_call",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="已按你的配色选择完成页面。"),
        ]
    )
    agent = _build_agent(ctx, model, {"ask_user"})
    config = {"configurable": {"thread_id": thread_id}}

    async def run() -> dict:
        # 第一段：模型请求 ask_user → 工具节点 interrupt
        interrupts: list[dict] = []
        async for chunk in agent.astream(
            {"messages": [HumanMessage(content="做一个落地页，配色需要确认。")]},
            config=config,
            stream_mode="updates",
        ):
            for value in _interrupt_values_from_chunk(chunk):
                if isinstance(value, dict):
                    interrupts.append(value)
        # 第二段：模拟用户经 /chat/answer 提交答案 → Command(resume)
        async for _event in agent.astream(
            Command(resume={"allowed": True, "answer": "蓝绿配色"}),
            config=config,
            stream_mode="updates",
        ):
            pass
        return {"interrupts": interrupts}

    try:
        result = asyncio.run(run())
    finally:
        asyncio.run(reset_agent_thread(thread_id))

    assert result["interrupts"], "ask_user 应在图内产生 interrupt"
    payload = result["interrupts"][0]
    assert payload["type"] == "ask_user"
    assert payload["call_id"] == "ask_e2e_call"
    assert payload["question"] == "配色用哪种？"

    # 答案必须作为工具结果回到下一次模型调用
    assert len(model.seen) >= 2, "模型应至少被调用两次（提问 + resume 后）"
    second_input = model.seen[1]
    assert any(
        entry["role"] == "tool" and "蓝绿配色" in entry["content"]
        for entry in second_input
    ), f"resume 后模型输入应含答案 ToolMessage，实际: {second_input}"
    # 工具结果确实来自 ask_user 工具（非其它来源）
    assert any("蓝绿配色" in entry["content"] for entry in second_input)


def test_ask_user_full_loop_skipped_in_full_mode(ctx_dirs):
    """approval_mode=full（定时任务/完全访问）：不 interrupt，直接继续。"""
    from app.agent.tools.tools import reset_agent_thread

    ctx = _make_ctx(ctx_dirs, approval_mode="full")
    thread_id = f"ask-full-{uuid.uuid4().hex}"

    model = RecordingChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ask_user",
                        "args": {"question": "配色用哪种？"},
                        "id": "ask_full_call",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="自动模式：按默认配色完成。"),
        ]
    )
    agent = _build_agent(ctx, model, {"ask_user"})
    config = {"configurable": {"thread_id": thread_id}}

    async def run() -> tuple[list[str], list[str]]:
        contents: list[str] = []
        async for _event in agent.astream(
            {"messages": [HumanMessage(content="做一个落地页。")]},
            config=config,
            stream_mode="updates",
        ):
            pass
        state = await agent.aget_state(config)
        for message in state.values.get("messages", []):
            if isinstance(message, AIMessage) and message.content:
                contents.append(str(message.content))
        return contents, []

    try:
        contents, _ = asyncio.run(run())
    finally:
        asyncio.run(reset_agent_thread(thread_id))

    # 未产生 interrupt：无 task；模型直接走了第二次（工具被降级为文本返回）
    assert any("自动模式" in text for text in contents)


# ---------------------------------------------------------------------------
# 用户插话（steering）全链路：队列 → before_model 注入 → 模型可见
# ---------------------------------------------------------------------------


def test_steering_injection_reaches_next_model_input(ctx_dirs):
    from app.agent.core import injection
    from app.agent.tools.tools import reset_agent_thread

    ctx = _make_ctx(ctx_dirs)
    thread_id = f"steer-e2e-{uuid.uuid4().hex}"

    model = RecordingChatModel(
        responses=[AIMessage(content="已完成初步方案。")]
    )
    agent = _build_agent(ctx, model, {"ask_user"})
    config = {"configurable": {"thread_id": thread_id}}

    injection.enqueue_injection(ctx.session_id, "加一个页脚与联系方式")
    try:
        asyncio.run(
            _stream_once(agent, ctx_dirs, ctx, config)
        )
    finally:
        injection.discard_injections(ctx.session_id)
        asyncio.run(reset_agent_thread(thread_id))

    # 第一次模型调用即应看到注入的补充（作为 user 消息前置）
    assert model.seen, "模型应至少被调用一次"
    first_input = model.seen[0]
    assert any(
        entry["role"] == "user" and "加一个页脚与联系方式" in entry["content"]
        for entry in first_input
    ), f"注入内容应在模型输入中可见，实际: {first_input}"


def _interrupt_values_from_chunk(chunk) -> list:
    """从 updates 流里取 __interrupt__ 条目（langgraph 会解包成 Interrupt）。"""
    values: list = []
    if isinstance(chunk, dict):
        for item in chunk.get("__interrupt__", ()) or ():
            values.append(getattr(item, "value", item))
    return values


async def _stream_once(agent, workspace, ctx, config) -> None:
    async for _event in agent.astream(
        {"messages": [HumanMessage(content="给当前页面方案补充一下。")]},
        config=config,
        stream_mode="updates",
    ):
        pass
