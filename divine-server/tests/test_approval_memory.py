"""终端命令审批记忆（P3-3c）：同一条命令会话内只确认一次，不做前缀匹配。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.tools.execution import (  # noqa: E402
    _is_session_approved,
    _normalized_command,
    _remember_approved_command,
)


def test_exact_command_match_after_approval():
    _remember_approved_command("sess-a", "npm   run build")
    assert _is_session_approved("sess-a", "npm run build")
    assert _is_session_approved("sess-a", "  npm run build  ")


def test_no_prefix_matching():
    _remember_approved_command("sess-b", "git push")
    assert not _is_session_approved("sess-b", "git push --force")
    assert not _is_session_approved("sess-b", "git")


def test_sessions_are_isolated():
    _remember_approved_command("sess-c", "make test")
    assert _is_session_approved("sess-c", "make test")
    assert not _is_session_approved("sess-d", "make test")


def test_empty_command_never_recorded():
    _remember_approved_command("sess-e", "   ")
    assert not _is_session_approved("sess-e", "")
