"""Tests for agent thread context management (P3-2: token-budget trim + stub).

新语义（_thread_context_actions）：
- 硬删除由 token 预算（默认窗口 70%，测试里显式传入小预算）或条数上限
  （limit*4）触发，删除边界仍推进到 HumanMessage 起点；
- ``limit`` 是"最近 N 条完整保留"：这之外的旧长工具结果用同 id 的占位
  消息置换（stub），结构保留、字节缩小。
"""

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    RemoveMessage,
    ToolMessage,
)
from langgraph.graph.message import add_messages

from app.agent.orchestrator import (
    _TOOL_STUB_MIN_CHARS,
    _thread_context_actions,
)


def _assign_ids(messages):
    for index, message in enumerate(messages):
        message.id = f"msg-{index}"
    return messages


def _turn(question: str, answer: str, call_id: str = "c1", tool_out: str = "file content"):
    """One human turn: question -> tool call -> tool result -> final answer."""
    return [
        HumanMessage(content=question),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": call_id,
                    "name": "read_file",
                    "args": {"file_path": "a.md"},
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(content=tool_out, tool_call_id=call_id, name="read_file"),
        AIMessage(content=answer),
    ]


def _history(n_turns: int, tool_out: str = "file content"):
    messages = []
    for i in range(n_turns):
        messages.extend(
            _turn(f"q{i}", f"a{i}", call_id=f"c{i}", tool_out=tool_out)
        )
    return _assign_ids(messages)


def test_small_thread_untouched():
    messages = _history(4)  # 16 messages, tiny tokens
    removals, stubs = _thread_context_actions(messages, 20, token_budget=100_000)
    assert removals == []
    assert stubs == []


def test_token_budget_cuts_at_human_boundary():
    messages = _history(6)  # 24 messages
    # 预算只够最近 8 条 → 原始切点落在 turn 中间，必须推进到 HumanMessage
    removals, stubs = _thread_context_actions(messages, 20, token_budget=80)
    kept = add_messages(messages, removals)
    assert isinstance(kept[0], HumanMessage)
    # 配对完整性：每个带 tool_calls 的 AI 消息后面都有对应 ToolMessage
    for index, message in enumerate(kept):
        if isinstance(message, AIMessage) and message.tool_calls:
            assert any(
                isinstance(m, ToolMessage)
                and m.tool_call_id == message.tool_calls[0]["id"]
                for m in kept[index + 1 :]
            )
    assert all(isinstance(r, RemoveMessage) for r in removals)
    assert stubs == []  # 短工具结果不置换


def test_old_long_tool_results_are_stubbed():
    long_out = "x" * (_TOOL_STUB_MIN_CHARS + 100)
    messages = _history(6, tool_out=long_out)  # 6 turns × 4
    removals, stubs = _thread_context_actions(messages, 20, token_budget=1_000_000)
    assert removals == []
    # 最近 12 条（turn 4-6）不动，更早的 3 条长工具结果被置换
    assert len(stubs) == 3
    for stub in stubs:
        assert isinstance(stub, ToolMessage)
        assert "已清理" in stub.content
        assert stub.id  # 同 id 才能在 reducer 里原位替换
    merged = add_messages(messages, stubs)
    stub_ids = {stub.id for stub in stubs}
    for message in merged:
        if message.id in stub_ids:
            assert "已清理" in message.content
            assert len(message.content) < _TOOL_STUB_MIN_CHARS


def test_recent_tail_never_stubbed():
    long_out = "x" * (_TOOL_STUB_MIN_CHARS + 100)
    # 只有 3 个 turn（12 条消息），全部在"最近 12 条"保护区内
    messages = _history(3, tool_out=long_out)
    removals, stubs = _thread_context_actions(messages, 20, token_budget=1_000_000)
    assert removals == []
    assert stubs == []


def test_count_cap_kicks_in_for_structural_growth():
    # limit=5 → 条数上限 max(20, 80)=80；120 条线程应裁到 80 并对齐 Human 边界
    messages = _history(30)
    removals, stubs = _thread_context_actions(messages, 5, token_budget=1_000_000)
    kept = add_messages(messages, removals)
    assert len(kept) <= 80
    assert isinstance(kept[0], HumanMessage)


def test_budget_floor_keeps_recent_exchange():
    # 预算极小也不允许全删：至少保留最后两条
    messages = _history(2)
    removals, stubs = _thread_context_actions(messages, 20, token_budget=1)
    kept = add_messages(messages, removals)
    assert len(kept) >= 2
