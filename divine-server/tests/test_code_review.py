"""自动 code review（review_changes）测试：diff 收集 / 空改动 / LLM 调用 / 非仓库。"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tools.adapters.code_review import (  # noqa: E402
    ReviewChangesAdapter,
    build_review_prompt,
)


def _git(ws: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(ws), *args], check=True, capture_output=True
    )


@pytest.fixture()
def git_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    _git(ws, "init", "-q", "-b", "main")
    _git(ws, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    _git(ws, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    return ws


class _FakeLLM:
    last_prompt = ""

    async def ainvoke(self, messages):
        from langchain_core.messages import HumanMessage

        _FakeLLM.last_prompt = "\n".join(
            m.content if isinstance(m.content, str) else ""
            for m in messages
            if isinstance(m, HumanMessage)
        )
        return type("Resp", (), {"content": "审查通过，未发现明显问题"})()


def test_no_changes_short_circuits(git_workspace: Path, monkeypatch):
    called = False

    def _fake_llm(**kwargs):
        nonlocal called
        called = True
        return _FakeLLM()

    monkeypatch.setattr("app.agent.core._build_llm", _fake_llm)
    result = asyncio.run(
        ReviewChangesAdapter("review_changes", "", {}).run(git_workspace, {})
    )
    assert result.success is True
    assert "没有未提交的改动" in (result.content or "")
    assert called is False


def test_review_uses_llm_with_diff(git_workspace: Path, monkeypatch):
    (git_workspace / "a.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    monkeypatch.setattr("app.agent.core._build_llm", lambda **kw: _FakeLLM())
    result = asyncio.run(
        ReviewChangesAdapter("review_changes", "", {}).run(
            git_workspace, {"focus": "边界条件"}
        )
    )
    assert result.success is True
    assert "审查通过" in (result.content or "")
    assert "return 2" in _FakeLLM.last_prompt  # diff 进了提示词
    assert "边界条件" in _FakeLLM.last_prompt  # focus 传入


def test_build_review_prompt_contains_diff_and_focus():
    prompt = build_review_prompt("diff-body", "并发安全")
    assert "diff-body" in prompt
    assert "并发安全" in prompt


def test_not_a_git_repo_raises(tmp_path: Path):
    with pytest.raises(Exception) as exc_info:
        asyncio.run(
            ReviewChangesAdapter("review_changes", "", {}).run(tmp_path, {})
        )
    assert "git" in str(exc_info.value).lower()
