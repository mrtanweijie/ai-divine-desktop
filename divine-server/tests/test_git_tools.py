"""Tests for git tools (status/diff/log/commit/revert) against real repos."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.agent.core import _NO_PLAN_TOOLS, _READ_ONLY_TOOLS
from app.tools.registry import get_tool

SCRIPT = Path(__file__).resolve().parents[1] / "app" / "tools" / "scripts" / "git_tool.py"

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git is not installed"
)


def _run(workspace: Path, params: dict) -> dict:
    payload = {
        "workspace": str(workspace.resolve()),
        "output_dir": str(workspace.resolve() / "out"),
        "params": params,
        "locale": "zh-CN",
    }
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "initial")
    return tmp_path


def test_status_clean(repo: Path):
    out = _run(repo, {"action": "status"})
    assert out["success"] is True
    assert out["data"]["clean"] is True


def test_status_modified(repo: Path):
    (repo / "a.py").write_text("x = 2\n", encoding="utf-8")
    out = _run(repo, {"action": "status"})
    assert out["success"] is True
    assert out["data"]["clean"] is False
    assert "a.py" in out["content"]


def test_diff_shows_changes(repo: Path):
    (repo / "a.py").write_text("x = 2\n", encoding="utf-8")
    out = _run(repo, {"action": "diff"})
    assert out["success"] is True
    assert "-x = 1" in out["content"]
    assert "+x = 2" in out["content"]


def test_diff_empty_when_clean(repo: Path):
    out = _run(repo, {"action": "diff"})
    assert out["success"] is True
    assert out["data"]["empty"] is True


def test_diff_staged(repo: Path):
    (repo / "a.py").write_text("x = 3\n", encoding="utf-8")
    _git(repo, "add", "-A")
    out = _run(repo, {"action": "diff", "staged": True})
    assert out["success"] is True
    assert "+x = 3" in out["content"]


def test_log_shows_commits(repo: Path):
    out = _run(repo, {"action": "log", "n": 5})
    assert out["success"] is True
    assert "initial" in out["content"]


def test_commit(repo: Path):
    (repo / "a.py").write_text("x = 4\n", encoding="utf-8")
    (repo / "b.py").write_text("y = 1\n", encoding="utf-8")
    out = _run(repo, {"action": "commit", "message": "feat: update x"})
    assert out["success"] is True
    log = _run(repo, {"action": "log", "n": 3})
    assert "feat: update x" in log["content"]
    status = _run(repo, {"action": "status"})
    assert status["data"]["clean"] is True


def test_commit_requires_message(repo: Path):
    out = _run(repo, {"action": "commit"})
    assert out["success"] is False
    assert "message" in out["message"]


def test_revert_single_file(repo: Path):
    (repo / "a.py").write_text("x = 99\n", encoding="utf-8")
    out = _run(repo, {"action": "revert", "path": "a.py"})
    assert out["success"] is True
    assert (repo / "a.py").read_text(encoding="utf-8") == "x = 1\n"


def test_revert_all(repo: Path):
    (repo / "a.py").write_text("x = 99\n", encoding="utf-8")
    (repo / "b.py").write_text("y = 1\n", encoding="utf-8")
    out = _run(repo, {"action": "revert"})
    assert out["success"] is True
    # tracked file restored; untracked files are intentionally kept
    assert (repo / "a.py").read_text(encoding="utf-8") == "x = 1\n"
    assert (repo / "b.py").exists()


def test_not_a_repo(tmp_path: Path):
    out = _run(tmp_path, {"action": "status"})
    assert out["success"] is False
    assert "不是 git 仓库" in out["message"]


# --- adapter wiring ---


def test_adapters_registered():
    for name in ("git_status", "git_diff", "git_log", "git_commit", "git_revert"):
        assert get_tool(name) is not None, name


def test_read_only_and_no_plan_sets():
    for name in ("git_status", "git_diff", "git_log"):
        assert name in _READ_ONLY_TOOLS
    for name in ("git_commit", "git_revert"):
        assert name in _NO_PLAN_TOOLS


# ---------------------------------------------------------------------------
# git 写操作审批的 SSE 渲染：必须携带 confirm_type/command，
# 否则前端确认区匹配不到分支、不渲染按钮（历史 bug：卡死到超时）。
# ---------------------------------------------------------------------------


def test_interrupt_sse_git_branch_carries_confirm_type_and_command():
    import json

    from app.agent.core.sse import _interrupt_sse

    out = _interrupt_sse(
        {
            "type": "git",
            "session_id": "s1",
            "tool": "git_commit",
            "message": "确认执行 git 写操作？",
            "command": "git_commit：初始化提交",
            "call_id": "c1",
        }
    )
    assert out.startswith("event: tool")
    data = json.loads(out.split("data:", 1)[1].strip())
    assert data["status"] == "confirm"
    assert data["confirm_type"] == "git"
    assert data["command"] == "git_commit：初始化提交"
    assert data["tool"] == "git_commit"
    assert data["call_id"] == "c1"
    assert data["session_id"] == "s1"
