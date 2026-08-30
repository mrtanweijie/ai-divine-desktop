"""中断线程修复：_pending_tool_call_ids 识别未完成的 tool_calls。

修复策略（orchestrator.run_agent）：检测到线程里有 AIMessage 的 tool_calls
没有对应 ToolMessage 时，合成补齐消息让线程恢复一致，而不是整线清零。
这里锁定纯函数行为：多轮/并行调用/重复 id 的配对逻辑。
"""

from __future__ import annotations

import sys
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.orchestrator import (  # noqa: E402
    _has_incomplete_tool_calls,
    _pending_tool_call_ids,
)


def _ai(*calls: tuple[str, str]) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"id": call_id, "name": name, "args": {}, "type": "tool_call"}
            for call_id, name in calls
        ],
    )


def _tool(call_id: str) -> ToolMessage:
    return ToolMessage(content="ok", tool_call_id=call_id, name="tool")


def test_empty_thread_has_no_pending():
    assert _pending_tool_call_ids([]) == []
    assert not _has_incomplete_tool_calls([])


def test_answered_calls_are_not_pending():
    messages = [_ai(("a1", "read_file")), _tool("a1")]
    assert _pending_tool_call_ids(messages) == []
    assert not _has_incomplete_tool_calls(messages)


def test_interrupted_call_is_pending_with_name():
    messages = [_ai(("a1", "edit_files"))]
    assert _pending_tool_call_ids(messages) == [("a1", "edit_files")]
    assert _has_incomplete_tool_calls(messages)


def test_parallel_calls_partial_answered():
    messages = [_ai(("a1", "read_file"), ("a2", "grep_files")), _tool("a1")]
    assert _pending_tool_call_ids(messages) == [("a2", "grep_files")]


def test_pending_order_follows_thread_order():
    messages = [
        _ai(("a1", "read_file"), ("a2", "grep_files")),
        _ai(("a3", "terminal")),
    ]
    assert [call_id for call_id, _ in _pending_tool_call_ids(messages)] == [
        "a1",
        "a2",
        "a3",
    ]


def test_answered_in_later_turn_resolves():
    messages = [_ai(("a1", "read_file")), _ai(("a2", "write_file")), _tool("a1"), _tool("a2")]
    assert _pending_tool_call_ids(messages) == []
