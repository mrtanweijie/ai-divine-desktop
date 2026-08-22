"""Tests for write-capable sub-agents (v2): claims, diffs, enforcement."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.agent.context import AgentRunContext
from app.agent.subagents import (
    _SUBAGENT_WRITE_TOOLS,
    _build_subagent_tools,
    _record_change,
    _resolve_write_claims,
    _run_subagent_tool_with_claims,
    _tool_target_paths,
    _validate_tasks,
    has_write_tasks,
)
from app.tools.registry import get_tool


def _ctx(workspace: Path) -> AgentRunContext:
    return AgentRunContext(
        session_id="s1",
        workspace=workspace,
        approval_mode="assist",
        locale="zh-CN",
    )


def _write_tasks() -> dict:
    return {
        "tasks": [
            {
                "id": "sa-w1",
                "name": "实现模块 A",
                "prompt": "创建 src/a.py",
                "write": True,
                "write_paths": ["src/a.py"],
            },
            {
                "id": "sa-w2",
                "name": "实现模块 B",
                "prompt": "创建 src/b.py",
                "write": True,
                "write_paths": ["src/b.py"],
            },
        ]
    }


# --- validation ---


def test_write_validation_passes(tmp_path: Path):
    tasks, error = _validate_tasks(_write_tasks(), workspace=tmp_path)
    assert error is None
    assert len(tasks) == 2
    assert has_write_tasks(tasks)
    assert all(task["write"] for task in tasks)
    assert tasks[0]["claims"] == [(tmp_path / "src" / "a.py").resolve()]


def test_write_requires_write_paths(tmp_path: Path):
    tasks = {
        "tasks": [
            {
                "id": "a",
                "name": "A",
                "prompt": "p",
                "write": True,
            },
            {"id": "b", "name": "B", "prompt": "p"},
        ]
    }
    tasks, error = _validate_tasks(tasks, workspace=tmp_path)
    assert error is not None
    assert "write_paths" in error


def test_write_paths_outside_workspace(tmp_path: Path):
    outside = tmp_path.parent / "outside"
    tasks = {
        "tasks": [
            {
                "id": "a",
                "name": "A",
                "prompt": "p",
                "write": True,
                "write_paths": [str(outside)],
            },
            {"id": "b", "name": "B", "prompt": "p"},
        ]
    }
    tasks, error = _validate_tasks(tasks, workspace=tmp_path)
    assert error is not None
    assert "超出工作区" in error


def test_overlapping_claims_rejected(tmp_path: Path):
    tasks = {
        "tasks": [
            {
                "id": "a",
                "name": "A",
                "prompt": "p",
                "write": True,
                "write_paths": ["src/"],
            },
            {
                "id": "b",
                "name": "B",
                "prompt": "p",
                "write": True,
                "write_paths": ["src/b.py"],
            },
        ]
    }
    tasks, error = _validate_tasks(tasks, workspace=tmp_path)
    assert error is not None
    assert "冲突" in error


def test_resolve_write_claims():
    ws = Path("/tmp/ws")
    claims, error = _resolve_write_claims(ws, ["src/a.py"])
    assert error is None
    assert claims == [(ws / "src" / "a.py").resolve()]


# --- tool enforcement ---


def test_tool_target_paths(tmp_path: Path):
    paths = _tool_target_paths(
        tmp_path,
        "write_file",
        {"path": "src/a.py"},
    )
    assert paths == [(tmp_path / "src" / "a.py").resolve()]
    paths2 = _tool_target_paths(
        tmp_path,
        "edit_files",
        {"files": [{"path": "a.py"}, {"path": "b.py"}]},
    )
    assert len(paths2) == 2


def test_write_within_claim_creates_file(tmp_path: Path):
    ctx = _ctx(tmp_path)
    adapter = get_tool("write_file")
    assert adapter is not None
    changes: list[dict] = []

    async def run():
        return await _run_subagent_tool_with_claims(
            ctx,
            adapter,
            "write_file",
            {"path": "src/a.py", "content": "x = 1\n"},
            claims=[(tmp_path / "src").resolve()],
            changes=changes,
        )

    result = asyncio.run(run())
    assert (tmp_path / "src" / "a.py").exists()
    assert json.loads(result)["success"] is True
    assert changes
    assert changes[0]["action"] == "created"
    assert changes[0]["path"] == "src/a.py"
    assert "+x = 1" in changes[0]["diff"]


def test_write_outside_claim_rejected(tmp_path: Path):
    ctx = _ctx(tmp_path)
    adapter = get_tool("write_file")
    assert adapter is not None
    changes: list[dict] = []

    async def run():
        return await _run_subagent_tool_with_claims(
            ctx,
            adapter,
            "write_file",
            {"path": "src/a.py", "content": "x = 1\n"},
            claims=[(tmp_path / "other").resolve()],
            changes=changes,
        )

    result = asyncio.run(run())
    payload = json.loads(result)
    assert payload["success"] is False
    assert "超出" in payload["message"]
    assert not (tmp_path / "src" / "a.py").exists()
    assert changes == []


def test_edit_within_claim_records_modified(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    ctx = _ctx(tmp_path)
    adapter = get_tool("edit_files")
    assert adapter is not None
    changes: list[dict] = []

    async def run():
        return await _run_subagent_tool_with_claims(
            ctx,
            adapter,
            "edit_files",
            {
                "files": [
                    {"path": "a.py", "search": "x = 1", "replace": "x = 2"}
                ]
            },
            claims=[(tmp_path / "a.py").resolve()],
            changes=changes,
        )

    result = asyncio.run(run())
    assert json.loads(result)["success"] is True
    assert changes[0]["action"] == "modified"
    assert "-x = 1" in changes[0]["diff"]
    assert "+x = 2" in changes[0]["diff"]


def test_record_change_dedupes_unchanged():
    changes: list[dict] = []
    ws = Path("/tmp/ws")
    _record_change(changes, ws, ws / "a.py", "same", "same")
    assert changes == []


def test_interrupt_sse_maps_subagents_write():
    from app.agent.sse import _interrupt_sse

    event = _interrupt_sse(
        {
            "type": "subagents_write",
            "session_id": "s1",
            "message": "确认并行写任务？",
            "subagent_write": {
                "tasks": [
                    {"id": "a", "name": "A", "write_paths": ["src/a.py"]}
                ]
            },
            "call_id": "call_1",
        }
    )
    assert '"confirm_type": "subagents_write"' in event
    assert '"subagent_write"' in event
    assert '"status": "confirm"' in event


# --- toolset construction ---


def test_write_tools_only_with_claims(tmp_path: Path):
    lock = asyncio.Lock()
    tools_readonly = _build_subagent_tools(_ctx(tmp_path), None, lock)
    names = {t.name for t in tools_readonly}
    assert not (_SUBAGENT_WRITE_TOOLS & names)

    changes: list[dict] = []
    tools_write = _build_subagent_tools(
        _ctx(tmp_path),
        None,
        lock,
        write_claims=[(tmp_path / "src").resolve()],
        changes=changes,
    )
    names_write = {t.name for t in tools_write}
    assert "write_file" in names_write
    assert "edit_files" in names_write
    # read-only tools remain available
    assert "read_file" in names_write
