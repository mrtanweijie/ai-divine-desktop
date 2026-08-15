"""Tests for agent thread context trimming (context_limit setting)."""

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    RemoveMessage,
    ToolMessage,
)
from langgraph.graph.message import add_messages

from app.agent.orchestrator import _thread_trim_removals


def _assign_ids(messages):
    """LangGraph's state reducer assigns ids to thread messages; replicate so
    the trim helper (RemoveMessage-based) sees the same shape as production."""
    for index, message in enumerate(messages):
        message.id = f"msg-{index}"
    return messages


def _turn(question: str, answer: str, call_id: str = "c1"):
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
        ToolMessage(content="file content", tool_call_id=call_id),
        AIMessage(content=answer),
    ]


def _history(n_turns: int):
    messages = []
    for i in range(n_turns):
        messages.extend(_turn(f"q{i}", f"a{i}", call_id=f"c{i}"))
    return _assign_ids(messages)


def test_no_trim_within_limit():
    messages = _history(4)  # 16 messages
    assert _thread_trim_removals(messages, 20) == []


def test_trim_keeps_newest_within_turn_boundary():
    messages = _history(6)  # 24 messages
    removals = _thread_trim_removals(messages, 20)
    assert len(removals) == 4  # drops one full turn (4 messages)
    kept = add_messages(messages, removals)
    assert len(kept) == 20
    assert isinstance(kept[0], HumanMessage)
    assert kept[0].content == "q1"  # oldest surviving message


def test_trim_never_splits_tool_call_pair():
    # Production threads always end on a completed turn (unfinished tool calls
    # are reset before running), so simulate 4 complete turns: the raw cut for
    # limit 6 falls inside a tool-call exchange and must advance to a
    # HumanMessage boundary.
    messages = _history(4)  # 16 messages: q0..q3 complete turns
    removals = _thread_trim_removals(messages, 6)
    kept = add_messages(messages, removals)
    # Kept suffix starts at a HumanMessage boundary.
    assert isinstance(kept[0], HumanMessage)
    # No leading orphan ToolMessage.
    assert not isinstance(kept[0], ToolMessage)
    # Tool-call pairs inside the kept suffix stay intact.
    for index, message in enumerate(kept):
        if isinstance(message, AIMessage) and message.tool_calls:
            assert any(
                isinstance(m, ToolMessage)
                and m.tool_call_id == message.tool_calls[0]["id"]
                for m in kept[index + 1 :]
            )
    assert len(kept) <= 6


def test_trim_returns_removals_with_ids():
    messages = _history(5)  # 20 messages
    removals = _thread_trim_removals(messages, 10)
    assert removals
    assert all(isinstance(r, RemoveMessage) for r in removals)
    assert all(r.id for r in removals)


def test_no_trim_when_single_turn_exceeds_limit():
    # One giant tool loop larger than the limit: trimming would split the
    # turn, so the helper must refuse to trim rather than corrupt context.
    messages = [HumanMessage(content="q")]
    for i in range(30):
        messages.append(
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": f"c{i}",
                        "name": "tool",
                        "args": {},
                        "type": "tool_call",
                    }
                ],
            )
        )
        messages.append(
            ToolMessage(content="ok", tool_call_id=f"c{i}")
        )
    messages = _assign_ids(messages)
    assert _thread_trim_removals(messages, 10) == []
