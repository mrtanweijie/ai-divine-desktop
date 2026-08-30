"""P4 改造测试：子 Agent 分级超时 + 终端会话 cwd 记忆（持久 shell 廉价版）。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# --- 子 Agent 超时分级 ------------------------------------------------------


def test_subagent_timeout_by_task_type():
    from app.agent.tools.subagents import (
        SUBAGENT_TIMEOUT_BUILD,
        SUBAGENT_TIMEOUT_RESEARCH,
        subagent_timeout,
    )

    assert SUBAGENT_TIMEOUT_BUILD >= 600  # 编码/终端类需要跑构建与测试
    assert SUBAGENT_TIMEOUT_RESEARCH >= 300
    assert subagent_timeout({"write": True}) == SUBAGENT_TIMEOUT_BUILD
    assert subagent_timeout({"terminal": True}) == SUBAGENT_TIMEOUT_BUILD
    assert subagent_timeout({}) == SUBAGENT_TIMEOUT_RESEARCH


# --- 终端 cwd 记忆（直接跑脚本子进程，走真实 shell） ------------------------


def _run_terminal(tmp_path: Path, session_id: str, command: str, cwd: str | None = None):
    payload = {
        "workspace": str(tmp_path / "workspace"),
        "params": {"command": command, "session_id": session_id},
    }
    if cwd is not None:
        payload["params"]["cwd"] = cwd
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] / "app/tools/scripts/terminal.py")],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=60,
        env={
            "PATH": "/usr/bin:/bin",
            "DIVINE_DATA_DIR": str(tmp_path / "data"),
            "HOME": str(tmp_path),
        },
    )
    assert proc.returncode == 0, proc.stderr[-500:]
    return json.loads(proc.stdout)


def test_terminal_cwd_persists_across_calls(tmp_path):
    ws = tmp_path / "workspace"
    (ws / "sub").mkdir(parents=True)
    (ws / "sub" / "marker.txt").write_text("x", encoding="utf-8")

    # 第一条命令 cd 进 sub
    first = _run_terminal(tmp_path, "sess-cwd", "cd sub && pwd")
    assert first["success"] is True
    assert first["data"]["final_cwd"].endswith("sub")

    # 第二条命令不传 cwd：应从 sub 继续（能看到 marker）
    second = _run_terminal(tmp_path, "sess-cwd", "ls marker.txt")
    assert second["success"] is True
    assert "marker.txt" in second["stdout"]


def test_terminal_explicit_cwd_overrides_memory(tmp_path):
    ws = tmp_path / "workspace"
    (ws / "a").mkdir(parents=True)
    (ws / "b").mkdir(parents=True)

    _run_terminal(tmp_path, "sess-ovr", "cd a")
    explicit = _run_terminal(tmp_path, "sess-ovr", "pwd", cwd=str(ws / "b"))
    assert explicit["data"]["cwd"] == str(ws / "b")
    assert explicit["data"]["final_cwd"] == str(ws / "b")

    # 显式 cwd 后记忆更新为 b
    after = _run_terminal(tmp_path, "sess-ovr", "pwd")
    assert after["data"]["cwd"] == str(ws / "b")


def test_terminal_sessions_are_isolated(tmp_path):
    ws = tmp_path / "workspace"
    (ws / "only-s1").mkdir(parents=True)

    _run_terminal(tmp_path, "sess-1", "cd only-s1")
    other = _run_terminal(tmp_path, "sess-2", "pwd")
    assert other["data"]["cwd"] == str(ws)  # 未受 sess-1 影响


def test_terminal_exit_code_preserved_with_cwd_capture(tmp_path):
    result = _run_terminal(tmp_path, "sess-exit", "cd sub 2>/dev/null; exit 7")
    # 命令失败退出码必须透传（cwd 捕获不能吞掉它）
    (tmp_path / "workspace" / "sub").mkdir(parents=True, exist_ok=True)
    result = _run_terminal(tmp_path, "sess-exit", "exit 7")
    assert result["exit_code"] == 7
