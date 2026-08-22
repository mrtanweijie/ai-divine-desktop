"""Tests for background process management (terminal background + bg tools).

A persistent event loop is used for all tests because asyncio subprocesses
are bound to the loop that created them; a fresh ``asyncio.run`` per test
would leave processes attached to a closed loop.
"""

from __future__ import annotations

import asyncio
import shlex
import sys
from pathlib import Path

import pytest

from app.agent.constants import _NO_PLAN_TOOLS, _READ_ONLY_TOOLS
from app.tools.base import ToolExecutionError
from app.tools.bg_process import bg_manager
from app.tools.registry import get_tool

PY = shlex.quote(sys.executable)

_LOOP = asyncio.new_event_loop()


def _run(coro):
    return _LOOP.run_until_complete(coro)


def _py(code: str) -> str:
    return f"{PY} -c {shlex.quote(code)}"


@pytest.fixture(autouse=True)
def _cleanup_bg():
    yield
    _run(bg_manager.shutdown_all())


# --- manager ---


def test_start_exit_and_output(tmp_path: Path):
    bg = _run(
        bg_manager.start(
            "s1",
            _py("import time; print('hello-bg', flush=True); time.sleep(0.2)"),
            str(tmp_path),
        )
    )
    assert bg.status in ("running", "exited")
    _run(asyncio.sleep(0.9))
    assert bg.status == "exited"
    assert bg.exit_code == 0
    output, truncated, total = bg.tail_output()
    assert "hello-bg" in output
    assert total >= len("hello-bg\n")


def test_kill_running(tmp_path: Path):
    bg = _run(
        bg_manager.start(
            "s1", _py("import time; time.sleep(60)"), str(tmp_path)
        )
    )
    _run(asyncio.sleep(0.3))
    assert bg.status == "running"
    killed = _run(bg_manager.kill(bg.bg_id, "s1"))
    assert killed is not None
    assert bg.status == "killed"


def test_session_scoping(tmp_path: Path):
    bg = _run(bg_manager.start("s1", "echo hi", str(tmp_path)))
    assert bg_manager.get(bg.bg_id, "s2") is None
    assert bg_manager.get(bg.bg_id, "s1") is not None
    assert len(bg_manager.list_for_session("s1")) == 1
    assert len(bg_manager.list_for_session("s2")) == 0
    _run(bg_manager.kill(bg.bg_id, "s1"))


def test_exit_code_captured(tmp_path: Path):
    bg = _run(
        bg_manager.start(
            "s1", _py("import sys; sys.exit(3)"), str(tmp_path)
        )
    )
    _run(asyncio.sleep(0.6))
    assert bg.status == "exited"
    assert bg.exit_code == 3


# --- adapters end to end ---


def test_terminal_background_and_bg_tools(tmp_path: Path):
    async def run():
        terminal = get_tool("terminal")
        out = await terminal.run(
            tmp_path,
            {
                "command": _py(
                    "import time; [print(i, flush=True) for i in range(3)]; time.sleep(30)"
                ),
                "background": True,
                "session_id": "s1",
            },
        )
        assert out.success is True
        bg_id = out.data["bg_id"]
        assert out.data["background"] is True

        status = get_tool("bg_status")
        res = await status.run(tmp_path, {"bg_id": bg_id, "session_id": "s1"})
        assert res.success is True
        assert res.data["status"] in ("running", "exited")

        await asyncio.sleep(0.8)
        out_tool = get_tool("bg_output")
        res2 = await out_tool.run(tmp_path, {"bg_id": bg_id, "session_id": "s1"})
        assert res2.success is True
        assert "0" in res2.content and "2" in res2.content

        kill_tool = get_tool("bg_kill")
        res3 = await kill_tool.run(tmp_path, {"bg_id": bg_id, "session_id": "s1"})
        assert res3.success is True
        assert res3.data["status"] == "killed"

    _run(run())


def test_bg_status_lists_session(tmp_path: Path):
    async def run():
        terminal = get_tool("terminal")
        await terminal.run(
            tmp_path,
            {"command": "echo a", "background": True, "session_id": "s9"},
        )
        status = get_tool("bg_status")
        res = await status.run(tmp_path, {"session_id": "s9"})
        assert res.success is True
        assert res.data["count"] >= 1

    _run(run())


def test_bg_unknown_id_rejected(tmp_path: Path):
    async def run():
        kill_tool = get_tool("bg_kill")
        try:
            await kill_tool.run(tmp_path, {"bg_id": "nope", "session_id": "s1"})
        except ToolExecutionError as exc:
            return str(exc)
        return None

    message = _run(run())
    assert message is not None
    assert "不存在" in message


def test_registration_and_policy_sets():
    for name in ("bg_status", "bg_output", "bg_kill"):
        assert get_tool(name) is not None, name
    assert "bg_status" in _READ_ONLY_TOOLS
    assert "bg_output" in _READ_ONLY_TOOLS
    assert "bg_kill" in _NO_PLAN_TOOLS
