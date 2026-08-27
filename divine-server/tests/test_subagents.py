"""Tests for the parallel sub-agent runner (run_subagents meta tool)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.agent.context import AgentRunContext
from app.agent.subagents import (
    MAX_SUBAGENTS,
    _SUBAGENT_COMMAND_TOOLS,
    _SUBAGENT_FORBIDDEN_TOOLS,
    _SUBAGENT_READ_ONLY_TOOLS,
    _build_subagent_tools,
    _run_subagent_tool,
    _run_subagents,
    _validate_tasks,
    has_terminal_tasks,
)


def _init_db(tmp_path, monkeypatch) -> str:
    """Point the app at an isolated DB and create a real session row, since
    the batch path persists a tool_run (FK -> sessions)."""
    data_dir = tmp_path / "data"
    workspace_dir = tmp_path / "workspace"
    db_path = tmp_path / "subagents.db"
    monkeypatch.setenv("DIVINE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(workspace_dir))
    monkeypatch.setenv("DB_PATH", str(db_path))

    from app import db

    db.init_db()
    project = db.create_project("测试项目", str(workspace_dir))
    return db.create_session("测试会话", project["id"])["id"]


class FakeRuntime:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []
        self.tool_call_id = "call_test"

    def stream_writer(self, payload: dict[str, object]) -> None:
        self.events.append(payload)


def _ctx(session_id: str = "s1", workspace: str = "/tmp/dw") -> AgentRunContext:
    return AgentRunContext(
        session_id=session_id,
        workspace=Path(workspace),
        approval_mode="ask",
        locale="zh-CN",
    )


def _two_tasks() -> dict[str, object]:
    return {
        "tasks": [
            {"id": "sa-1", "name": "调研 A", "prompt": "总结 A"},
            {"id": "sa-2", "name": "调研 B", "prompt": "总结 B"},
        ],
        "max_parallel": 2,
    }


# --- validation ---


def test_validate_accepts_two_tasks():
    tasks, error = _validate_tasks(_two_tasks())
    assert error is None
    assert len(tasks) == 2


def test_validate_rejects_empty():
    tasks, error = _validate_tasks({"tasks": []})
    assert tasks == []
    assert "非空" in error


def test_validate_rejects_single_task():
    tasks, error = _validate_tasks({"tasks": [{"id": "a", "name": "A", "prompt": "p"}]})
    assert tasks == []
    assert "至少需要 2 个" in error


def test_validate_rejects_too_many():
    tasks_list = [
        {"id": f"sa-{i}", "name": f"T{i}", "prompt": f"p{i}"}
        for i in range(MAX_SUBAGENTS + 1)
    ]
    tasks, error = _validate_tasks({"tasks": tasks_list})
    assert tasks == []
    assert "最多委托" in error


def test_validate_requires_fields():
    tasks, error = _validate_tasks(
        {"tasks": [{"id": "a", "name": "A"}, {"id": "b", "name": "B", "prompt": "p"}]}
    )
    assert tasks == []
    assert "缺少 id / name / prompt" in error


def test_validate_rejects_non_object_task():
    tasks, error = _validate_tasks(
        {"tasks": ["not-an-object", {"id": "b", "name": "B", "prompt": "p"}]}
    )
    assert tasks == []
    assert "必须是对象" in error


# --- toolset construction ---


def test_subagent_tools_are_read_only():
    tools = _build_subagent_tools(_ctx(), None, asyncio.Lock())
    names = {tool.name for tool in tools}
    assert names.issubset(_SUBAGENT_READ_ONLY_TOOLS)
    assert not names.intersection(_SUBAGENT_FORBIDDEN_TOOLS)
    assert "terminal" not in names
    assert "edit_files" not in names


def test_validate_accepts_terminal_flag():
    tasks, error = _validate_tasks(
        {
            "tasks": [
                {"id": "a", "name": "A", "prompt": "p", "terminal": True},
                {"id": "b", "name": "B", "prompt": "p"},
            ]
        }
    )
    assert error is None
    assert tasks[0]["terminal"] is True
    assert tasks[1]["terminal"] is False
    assert has_terminal_tasks(tasks) is True
    assert has_terminal_tasks([tasks[1]]) is False


def test_terminal_enabled_build_includes_command_tools():
    tools = _build_subagent_tools(_ctx(), None, asyncio.Lock(), terminal_enabled=True)
    names = {tool.name for tool in tools}
    assert "terminal" in names
    assert _SUBAGENT_COMMAND_TOOLS.issubset(names)


def test_terminal_disabled_excludes_command_tools():
    tools = _build_subagent_tools(_ctx(), None, asyncio.Lock())
    names = {tool.name for tool in tools}
    assert "terminal" not in names
    assert not (_SUBAGENT_COMMAND_TOOLS & names)


class _NeverRunAdapter:
    """Stub that fails the test if the underlying tool actually runs."""

    name = "terminal"
    timeout = 5

    def external_paths(self, workspace, arguments):
        return []

    async def run(self, workspace, arguments, locale=None, progress_callback=None):
        raise AssertionError("terminal should have been rejected before run")


@pytest.mark.anyio
async def test_terminal_rejects_non_safe_policy(tmp_path):
    ctx = _ctx(workspace=str(tmp_path))
    result = await _run_subagent_tool(
        ctx, _NeverRunAdapter(), "terminal", {"command": "rm -rf /tmp/x"}
    )
    payload = json.loads(result)
    assert payload["rejected"] is True
    assert "安全只读命令" in payload["message"]


@pytest.mark.anyio
async def test_terminal_allows_safe_command(tmp_path):
    """safe 级命令正常执行（echo），证明白名单不是全禁。"""
    from app.tools.adapters.terminal import TerminalAdapter

    ctx = AgentRunContext(
        session_id="s1",
        workspace=tmp_path,
        approval_mode="ask",
        locale="zh-CN",
    )
    result = await _run_subagent_tool(
        ctx, TerminalAdapter("terminal", ""), "terminal", {"command": "echo sub-ok"}
    )
    assert "sub-ok" in result


def test_allowlist_narrows_toolset():
    tools = _build_subagent_tools(_ctx(), ["web_fetch"], asyncio.Lock())
    names = {tool.name for tool in tools}
    assert names == {"web_fetch"}


def test_forbidden_tools_never_included_even_when_allowlisted():
    tools = _build_subagent_tools(_ctx(), ["web_fetch", "terminal", "edit_files"], asyncio.Lock())
    names = {tool.name for tool in tools}
    assert "terminal" not in names
    assert "edit_files" not in names
    assert "web_fetch" in names


# --- end-to-end batch (Mock LLM, no API key needed) ---


def test_batch_runs_and_aggregates(tmp_path, monkeypatch):
    session_id = _init_db(tmp_path, monkeypatch)

    async def run() -> dict[str, object]:
        rt = FakeRuntime()
        ctx = AgentRunContext(
            session_id=session_id,
            workspace=tmp_path / "workspace",
            approval_mode="ask",
            locale="zh-CN",
        )
        output = await _run_subagents(ctx, rt, _two_tasks())
        return json.loads(output)

    payload = asyncio.run(run())
    assert payload["success"] is True
    assert len(payload["results"]) == 2
    for item in payload["results"]:
        assert item["status"] in {"done", "error"}
        assert item["id"]
        assert item["name"]
    assert payload["message"] == "2 个子任务全部完成"


def test_batch_emits_subagent_events(tmp_path, monkeypatch):
    session_id = _init_db(tmp_path, monkeypatch)

    async def run() -> list[dict[str, object]]:
        rt = FakeRuntime()
        ctx = AgentRunContext(
            session_id=session_id,
            workspace=tmp_path / "workspace",
            approval_mode="ask",
            locale="zh-CN",
        )
        await _run_subagents(ctx, rt, _two_tasks())
        return rt.events

    events = asyncio.run(run())
    subagent_events = [e for e in events if e.get("event") == "subagent"]
    running = [e for e in subagent_events if e.get("status") == "running"]
    done = [e for e in subagent_events if e.get("status") == "done"]
    assert len(running) == 2
    assert len(done) == 2
    assert all("sub_id" in e for e in subagent_events)
    # tool events bracket the batch
    tool_events = [e for e in events if e.get("event") == "tool"]
    assert tool_events[0]["status"] == "running"
    assert tool_events[-1]["status"] == "done"
    assert tool_events[-1]["tool"] == "run_subagents"


def test_batch_persists_tool_run(tmp_path, monkeypatch):
    from app import db

    session_id = _init_db(tmp_path, monkeypatch)

    async def run() -> None:
        rt = FakeRuntime()
        ctx = AgentRunContext(
            session_id=session_id,
            workspace=tmp_path / "workspace",
            approval_mode="ask",
            locale="zh-CN",
        )
        await _run_subagents(ctx, rt, _two_tasks())

    asyncio.run(run())
    runs = db.list_tool_runs(session_id)
    assert len(runs) == 1
    assert runs[0]["tool_name"] == "run_subagents"
    assert runs[0]["status"] == "done"
    output = json.loads(runs[0]["output"])
    assert len(output["results"]) == 2


def test_cancel_event_aborts_batch(tmp_path, monkeypatch):
    session_id = _init_db(tmp_path, monkeypatch)

    async def run() -> list[dict[str, object]]:
        rt = FakeRuntime()
        cancel = asyncio.Event()
        ctx = AgentRunContext(
            session_id=session_id,
            workspace=tmp_path / "workspace",
            approval_mode="ask",
            locale="zh-CN",
            cancel_event=cancel,
        )

        async def delayed_run():
            # Simulate an in-flight batch: cancel after the first task starts.
            await asyncio.sleep(0.05)
            cancel.set()

        await asyncio.gather(delayed_run(), _run_subagents(ctx, rt, _two_tasks()))
        return rt.events

    events = asyncio.run(run())
    tool_done = [e for e in events if e.get("event") == "tool"][-1]
    assert tool_done["status"] == "done" or tool_done["status"] == "error"


def test_timeout_marks_error(tmp_path, monkeypatch):
    import app.agent.subagents as module

    session_id = _init_db(tmp_path, monkeypatch)

    async def run() -> dict[str, object]:
        rt = FakeRuntime()
        ctx = AgentRunContext(
            session_id=session_id,
            workspace=tmp_path / "workspace",
            approval_mode="ask",
            locale="zh-CN",
        )
        monkeypatch.setattr(module, "SUBAGENT_TIMEOUT", 0.01)

        async def slow_ainvoke(self, *args, **kwargs):
            await asyncio.sleep(10)

        monkeypatch.setattr(module, "create_agent", lambda **kwargs: type(
            "FakeAgent", (), {"ainvoke": slow_ainvoke}
        )())
        output = await _run_subagents(ctx, rt, _two_tasks())
        return json.loads(output)

    payload = asyncio.run(run())
    assert all(item["status"] == "error" for item in payload["results"])
    assert any("超时" in item["error"] for item in payload["results"])
