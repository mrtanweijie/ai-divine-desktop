"""task 单委派入口与 browser 子 agent 工具表构建的离线单测（031 §3/§4）。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.agent.core import AgentRunContext
from app.agent.tools import subagents as subagents_mod
from app.agent.tools.subagents import (
    _SUBAGENT_BROWSER_TOOLS,
    _build_subagent_tools,
    _run_browser_task,
    _validate_tasks,
    subagent_timeout,
)


def _ctx(session_id: str = "s1", workspace: str = "/tmp/dw") -> AgentRunContext:
    return AgentRunContext(
        session_id=session_id,
        workspace=Path(workspace),
        approval_mode="ask",
        locale="zh-CN",
    )


class FakeRuntime:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []
        self.tool_call_id = "call_test"

    def stream_writer(self, payload: dict[str, object]) -> None:
        self.events.append(payload)


# ---------------------------------------------------------------------------
# 工具表隔离：browser 工具只进 browser 分支，其余子 agent 不可见
# ---------------------------------------------------------------------------


def test_browser_tools_registered_in_registry():
    from app.tools.registry import registry

    assert _SUBAGENT_BROWSER_TOOLS <= registry.names()
    assert len(_SUBAGENT_BROWSER_TOOLS) == 10


def test_browser_tools_forbidden_for_normal_subagents():
    assert _SUBAGENT_BROWSER_TOOLS <= subagents_mod._SUBAGENT_FORBIDDEN_TOOLS
    assert "web_task" in subagents_mod._SUBAGENT_FORBIDDEN_TOOLS


def test_browser_branch_builds_only_browser_tools():
    tools = _build_subagent_tools(_ctx(), None, asyncio.Lock(), browser_enabled=True)
    names = {tool.name for tool in tools}
    assert names == set(_SUBAGENT_BROWSER_TOOLS)
    click = next(tool for tool in tools if tool.name == "browser_click")
    assert "intent" in click.args_schema.model_fields


def test_default_branch_has_no_browser_tools():
    tools = _build_subagent_tools(_ctx(), None, asyncio.Lock())
    assert not ({tool.name for tool in tools} & _SUBAGENT_BROWSER_TOOLS)


def test_browser_task_timeout_is_build_level():
    # 逐步操作任务单段常见 5-10 分钟，与写文件类共用 600s
    assert subagent_timeout({"browser": True}) == subagents_mod.SUBAGENT_TIMEOUT_BUILD


def test_browser_turn_limit_doubles_research():
    # 48 回合与 40 步工具上限配套；工具轮 ≈ 模型轮
    assert (
        subagents_mod.SUBAGENT_BROWSER_MAX_TOOL_TURNS
        == subagents_mod.SUBAGENT_MAX_TOOL_TURNS * 2
    )


# ---------------------------------------------------------------------------
# _run_browser_task — 参数校验与委派路径
# ---------------------------------------------------------------------------


def _parse(payload: str) -> dict:
    return json.loads(payload)


def test_task_rejects_unknown_subagent_type():
    payload = _parse(
        asyncio.run(
            _run_browser_task(_ctx(), FakeRuntime(), {"subagent_type": "research", "prompt": "x"})
        )
    )
    assert payload["success"] is False
    assert payload["rejected"] is True


def test_task_rejects_empty_prompt():
    payload = _parse(
        asyncio.run(_run_browser_task(_ctx(), FakeRuntime(), {"subagent_type": "browser", "prompt": " "}))
    )
    assert payload["rejected"] is True


def test_task_delegates_with_confirmed_flag(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("DIVINE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    from app import db

    db.init_db()
    project = db.create_project("测试项目", str(tmp_path / "workspace"))
    session_id = db.create_session("测试会话", project["id"])["id"]

    captured: dict = {}

    async def fake_run_subagent(ctx, task, emit=None):
        captured["task"] = task
        captured["emit"] = emit
        return {"id": task["id"], "name": task["name"], "status": "done", "summary": "ok"}

    monkeypatch.setattr(subagents_mod, "_run_subagent", fake_run_subagent)

    runtime = FakeRuntime()
    payload = _parse(
        asyncio.run(
            _run_browser_task(
                _ctx(session_id=session_id),
                runtime,
                {"subagent_type": "browser", "prompt": "打开 X 并抽取结算字段", "confirmed": True},
            )
        )
    )
    assert payload["success"] is True
    assert captured["task"]["browser"] is True
    assert captured["task"]["confirmed"] is True
    assert captured["emit"] is not None
    kinds = [event.get("event") for event in runtime.events]
    assert "subagent" in kinds


# ---------------------------------------------------------------------------
# _validate_tasks 回归：browser 标志不影响原有批量校验
# ---------------------------------------------------------------------------


def test_validate_tasks_still_requires_two_tasks():
    tasks, error = _validate_tasks({"tasks": [{"id": "a", "name": "n", "prompt": "p"}]})
    assert tasks == []
    assert error and "至少需要 2 个子任务" in error
