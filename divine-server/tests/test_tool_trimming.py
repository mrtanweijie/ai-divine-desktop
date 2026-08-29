"""意图工具裁减：内容创作/技能类工具随意图注入，核心工具常驻。

目的：云端 agent 每次请求全带 60 个工具 schema ≈ 13.3k token；
按意图只带相关工具（意图=question 时裁掉 22 个内容创作/技能工具，省 ~6.3k）。
"""

from __future__ import annotations

import asyncio


def _ctx(tmp_path, monkeypatch):
    from app.agent.context import AgentRunContext

    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "ws"))
    (tmp_path / "ws").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    return AgentRunContext(
        session_id="s1",
        workspace=tmp_path / "ws",
        approval_mode="ask",
        locale="zh-CN",
        approved_paths=frozenset(),
        think=False,
        effort="high",
        model_id=None,
        cancel_event=asyncio.Event(),
        tool_mode="auto",
    )


def _names(ctx):
    from app.agent.tools import _build_tools

    return {t.name for t in _build_tools(ctx)}


def test_question_intent_trims_content_tools(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, monkeypatch)
    ctx.intents = {"question"}
    names = _names(ctx)
    assert "pdf_generate" not in names
    assert "word_document" not in names
    assert "image_generate" not in names
    assert "run_subagents" not in names
    # 核心工具常驻
    assert "read_file" in names
    assert "web_search" in names
    assert "notes" in names
    assert "terminal" in names


def test_pdf_intent_includes_pdf_tools(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, monkeypatch)
    ctx.intents = {"pdf"}
    names = _names(ctx)
    assert "pdf_generate" in names
    assert "pdf_render" in names
    # 其他内容类工具仍被裁
    assert "word_document" not in names
    assert "generate_chart" not in names


def test_no_intents_keeps_all_tools(tmp_path, monkeypatch):
    """无意图信号（首轮兜底）→ 全量工具，保守不裁。"""
    ctx = _ctx(tmp_path, monkeypatch)
    ctx.intents = None
    names = _names(ctx)
    assert "pdf_generate" in names
    assert "run_subagents" in names


def test_trimming_reduces_tool_count(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, monkeypatch)
    ctx.intents = {"question"}
    small = _names(ctx)
    ctx.intents = None
    full = _names(ctx)
    assert len(small) < len(full)
    assert len(full) - len(small) >= 20  # 裁掉 20+ 个内容创作/技能工具
