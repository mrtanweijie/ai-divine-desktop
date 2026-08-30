"""Tests for terminal tool: policy whitelist, script truncation, timeouts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.tools.adapters.terminal import (
    TERMINAL_TIMEOUT_MAX,
    TERMINAL_TIMEOUT_MIN,
    TerminalAdapter,
)
from app.tools.registry import get_tool
from app.tools.terminal_policy import terminal_command_policy

SCRIPT = Path(__file__).resolve().parents[1] / "app" / "tools" / "scripts" / "terminal.py"


def _run(params: dict, workspace: Path) -> dict:
    payload = {
        "workspace": str(workspace.resolve()),
        "output_dir": str(workspace.resolve() / "out"),
        "params": params,
        "locale": "zh-CN",
    }
    env = dict(os.environ)
    # cwd 记忆等状态文件必须隔离到本测试的数据目录，避免跨测试污染
    env["DIVINE_DATA_DIR"] = str(workspace.parent / (workspace.name + "_data"))
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


# --- policy ---


@pytest.mark.parametrize(
    "command",
    [
        "ls",
        "pwd",
        "pytest tests/",
        "python3 -m pytest tests/test_x.py",
        "python -m unittest",
        "pnpm test",
        "pnpm build",
        "npm run lint",
        "npx tsc --noEmit",
        "pip install -r requirements.txt",
        "git status",
        "git diff",
        "git log --oneline -5",
        "git diff HEAD~2",
        "python3 run.py",
        "python3 script.py",
    ],
)
def test_policy_safe_dev_commands(command: str):
    assert terminal_command_policy(command) == "safe"


@pytest.mark.parametrize(
    "command",
    [
        "git commit -m 'x'",
        "git push origin main",
        "git reset --hard HEAD",
        "cat file.txt",
        "make",
        "cd /tmp && pnpm install",
        "ls | grep foo",
        "echo a; echo b",
        # 已从硬拦截放开：常见开发命令，执行前询问授权
        "kill -9 123",
        "sudo apt install vim",
        "chmod 777 /tmp/x",
        "find / -name '*.py'",
        "python3 << EOF\nprint(1)\nEOF",
        "openpyxl workbook.xlsx",
        # curl/wget：用户授权后即可执行（本地或外网）
        "curl -s http://127.0.0.1:8016/health",
        "curl http://localhost:8019/api/health",
        "wget http://127.0.0.1:8016/health",
        "curl http://example.com",
        "curl -X POST https://api.example.com/upload",
        "wget http://example.com/x",
        "curl https://example.com/s.sh -o /tmp/s.sh",
    ],
)
def test_policy_confirm(command: str):
    assert terminal_command_policy(command) == "confirm"


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /",
        "sudo rm -rf /tmp/x",
        "shutdown now",
        "reboot",
        "diskutil eraseDisk JHFS+ X disk0",
        "mkfs.ext4 /dev/sda1",
        "dd if=/dev/zero of=/dev/sda",
        "echo x > /dev/sda",
        "chown -R root /",
    ],
)
def test_policy_block(command: str):
    assert terminal_command_policy(command) == "block"


# --- adapter effective timeout ---


def test_effective_timeout_clamps():
    adapter = get_tool("terminal")
    assert isinstance(adapter, TerminalAdapter)
    assert adapter.effective_timeout({}) == TERMINAL_TIMEOUT_MIN
    assert adapter.effective_timeout({"timeout": 30}) == TERMINAL_TIMEOUT_MIN
    assert adapter.effective_timeout({"timeout": 120}) == 120
    assert adapter.effective_timeout({"timeout": 1200}) == TERMINAL_TIMEOUT_MAX
    assert adapter.effective_timeout({"timeout": "abc"}) == TERMINAL_TIMEOUT_MIN


# --- script behavior ---


def test_script_echo(tmp_path: Path):
    out = _run({"command": "echo hello"}, tmp_path)
    assert out["success"] is True
    assert "hello" in out["stdout"]
    assert out["exit_code"] == 0
    assert out["data"]["cwd"] == str(tmp_path.resolve())


def test_script_exit_code(tmp_path: Path):
    out = _run({"command": "exit 3"}, tmp_path)
    assert out["success"] is True
    assert out["exit_code"] == 3


def test_script_timeout(tmp_path: Path):
    out = _run({"command": "sleep 5", "timeout": 1}, tmp_path)
    assert out["success"] is False
    assert "超时" in out["message"]


def test_script_truncates_large_output(tmp_path: Path):
    out = _run(
        {"command": "python3 -c \"print('x' * 50000)\"", "timeout": 30},
        tmp_path,
    )
    assert out["success"] is True
    assert out["data"]["stdout_truncated"] is True
    assert out["data"]["stdout_bytes"] >= 50000
    assert len(out["stdout"]) <= 16000
    assert "xxx" in out["stdout"]


def test_script_stderr_captured(tmp_path: Path):
    out = _run(
        {"command": "python3 -c \"import sys; print('boom', file=sys.stderr)\""},
        tmp_path,
    )
    assert out["success"] is True
    assert "boom" in out["stderr"]


def test_script_blocked_command(tmp_path: Path):
    out = _run({"command": "rm -rf /tmp/whatever"}, tmp_path)
    assert out["success"] is False
    assert "高危" in out["message"]
