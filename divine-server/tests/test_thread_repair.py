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


from app.agent.orchestrator import _repair_tool_groups  # noqa: E402
from app.db.history import _sanitize_tool_groups  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402


def _repair_ai(call_ids: list[str]) -> AIMessage:
    return AIMessage(
        content="",
        id=f"ai-{'-'.join(call_ids) or 'x'}",
        tool_calls=[
            {"id": cid, "name": "tool", "args": {}, "type": "tool_call"}
            for cid in call_ids
        ],
    )


def _repair_tool(call_id: str, index: int) -> ToolMessage:
    return ToolMessage(
        content="ok",
        tool_call_id=call_id,
        name="tool",
        id=f"tool-{index}",
    )


def _removed_ids(removes: list[Any]) -> list[str]:
    return sorted([str(r.id) for r in removes])


def test_repair_tail_orphan_appends_placeholder():
    messages = [
        HumanMessage(content="q1", id="h1"),
        _repair_ai(["a1"]),
    ]
    removes, appends = _repair_tool_groups(messages)
    assert removes == []
    assert len(appends) == 1
    assert appends[0].tool_call_id == "a1"
    assert "中断" in appends[0].content


def test_repair_mid_orphan_removes_whole_group():
    messages = [
        HumanMessage(content="q1", id="h1"),
        _repair_ai(["a1", "a2"]),
        _repair_tool("a1", 1),
        HumanMessage(content="q2", id="h2"),
    ]
    removes, appends = _repair_tool_groups(messages)
    assert appends == []
    # 中段残缺：assistant 与已落地的 tool 结果整组删除（无法原位补齐）
    assert _removed_ids(removes) == ["ai-a1-a2", "tool-1"]


def test_repair_intact_group_is_noop():
    messages = [
        HumanMessage(content="q1", id="h1"),
        _repair_ai(["a1"]),
        _repair_tool("a1", 1),
        HumanMessage(content="q2", id="h2"),
    ]
    removes, appends = _repair_tool_groups(messages)
    assert removes == []
    assert appends == []


def test_repair_interleaved_assistants_detected_as_orphan():
    # [A(a1), A(a2), T(a1), T(a2)] 全局按 id 配对"无 pending"，但协议要求
    # tool 紧跟 assistant —— A(a1) 后是 A(a2) 而非 tool，仍属残缺组。
    messages = [
        _repair_ai(["a1"]),
        _repair_ai(["a2"]),
        _repair_tool("a1", 1),
        _repair_tool("a2", 2),
    ]
    removes, appends = _repair_tool_groups(messages)
    assert _removed_ids(removes) == ["ai-a1"]
    assert appends == []


def _dai(call_ids: list[str]) -> dict:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": cid, "name": "tool", "type": "function"}
            for cid in call_ids
        ],
    }


def _dtool(call_id: str) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": "ok"}


def test_sanitize_tail_orphan_dropped():
    assert _sanitize_tool_groups([_dai(["a1"])]) == []


def test_sanitize_mid_orphan_dropped():
    messages = [
        {"role": "user", "content": "q1"},
        _dai(["a1"]),
        {"role": "user", "content": "q2"},
    ]
    out = _sanitize_tool_groups(messages)
    assert [m["role"] for m in out] == ["user", "user"]


def test_sanitize_partial_group_dropped():
    # 并行组只回了一条 → 整组剔除（assistant + 已回 tool 都不残留），
    # 与 test_history_window 的中段残缺语义一致。
    messages = [_dai(["a1", "a2"]), _dtool("a1"), {"role": "user", "content": "q2"}]
    out = _sanitize_tool_groups(messages)
    assert [m["role"] for m in out] == ["user"]


def test_sanitize_partial_group_at_tail_dropped():
    messages = [_dai(["a1", "a2"]), _dtool("a1")]
    out = _sanitize_tool_groups(messages)
    assert out == []


def test_sanitize_intact_group_kept():
    messages = [_dai(["a1", "a2"]), _dtool("a1"), _dtool("a2")]
    out = _sanitize_tool_groups(messages)
    assert len(out) == 3


def test_sanitize_stray_tool_dropped():
    messages = [_dtool("a9"), _dai(["a1"]), _dtool("a1")]
    out = _sanitize_tool_groups(messages)
    assert len(out) == 2
    assert out[0]["role"] == "assistant"

