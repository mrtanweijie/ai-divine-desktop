"""Tests for in-session history backtracking.

Covers ``prompts._history_backtrack_context`` (B-scheme: keyword fast-path +
retrieval-gap fallback) and the shared ``app.db.retrieval`` scoring primitives.
Message source is stubbed so no real DB fixture is required.
"""

from __future__ import annotations

from app import db
from app.agent.core import prompts
from app.db import retrieval


def _run(query: str, messages: list[tuple[str, str]], session_id: str = "s1"):
    """Call the backtrack helper with a stubbed message source."""
    rows = [
        {"role": role, "content": text} for role, text in messages
    ]
    original = db.list_messages
    db.list_messages = lambda sid: rows  # type: ignore[assignment]
    try:
        return prompts._history_backtrack_context(session_id, query)
    finally:
        db.list_messages = original


def _long_rows() -> list[tuple[str, str]]:
    """30 条消息：巴黎出差事实在窗口外（前 2 条），窗口内（后 12 条）全是电影闲聊。"""
    rows = [
        ("user", "下周三我要去巴黎出差，住香街的万豪酒店"),
        ("assistant", "好的，已记下巴黎出差安排"),
    ]
    for index in range(14):
        rows.append(("user", f"继续聊聊最近上映的电影怎么样{index}"))
        rows.append(("assistant", f"好的，这部电影{index}口碑不错"))
    return rows


def test_backtrack_keyword_hits_out_of_window_fact():
    result = _run("我之前说的巴黎酒店叫什么来着", _long_rows())
    assert result is not None
    assert "巴黎" in result
    assert "万豪" in result
    # 窗口内无关的"电影"内容不应出现在命中片段里（相关度阈值过滤）
    assert "电影" not in result


def test_backtrack_without_keyword_via_score_gap():
    # 无回溯关键词，但早期片段显著优于窗口 → 检索对比触发
    result = _run("巴黎酒店住在哪里", _long_rows())
    assert result is not None
    assert "巴黎" in result
    assert "万豪" in result


def test_no_backtrack_no_history_match_returns_none():
    # 无关键词、早期也无相关内容 → 不注入
    assert _run("今天天气怎么样", _long_rows()) is None


def test_backtrack_keyword_but_no_relevant_hit_returns_none():
    # 有关键词但历史里没有相关内容 → 相关度低于阈值 → 不注入
    assert _run("之前说的那个机器学习论文", _long_rows()) is None


def test_backtrack_window_relevant_skips_without_keyword():
    # 无关键词且窗口内已足够贴切（当前话题直接能答）→ 跳过回溯，省成本
    rows = [
        ("user", f"巴黎酒店位置在香街{index}") for index in range(14)
    ]
    assert _run("巴黎酒店在哪", rows) is None


def test_backtrack_skips_tool_messages():
    rows = [
        ("user", "下周三去巴黎出差住万豪"),
        ("tool", "工具结果：天气晴朗"),  # 不应进入候选
        ("assistant", "好的"),
    ]
    rows += [
        ("user", f"继续聊电影{index}") for index in range(14)
    ]
    result = _run("我之前说的巴黎酒店", rows)
    assert result is not None
    assert "巴黎" in result
    assert "天气晴朗" not in result


def test_backtrack_respects_budget():
    # 构造一条超长但相关的窗口外消息：单条片段应被截断到 200 字以内
    long_text = "巴黎酒店" * 100  # 与 query 强相关，避免被相关度阈值过滤
    rows = [
        ("user", "第一次说的巴黎酒店" + long_text),
        ("assistant", "好的"),
    ]
    rows += [
        ("user", f"继续聊电影{index}") for index in range(14)
    ]
    result = _run("我第一次说的巴黎酒店", rows)
    assert result is not None
    # 每条命中片段不超过 _HISTORY_SNIPPET_CHAR_LIMIT
    for line in result.splitlines():
        if line.startswith("- (相关度"):
            assert len(line) <= (
                prompts._HISTORY_SNIPPET_CHAR_LIMIT + 32
            )
    # 整块不超过预算 + 块头
    assert len(result) <= (
        prompts._HISTORY_BACKTRACK_CHAR_LIMIT + 80
    )


def test_backtrack_db_error_returns_none():
    original = db.list_messages
    db.list_messages = lambda sid: (_ for _ in ()).throw(  # type: ignore[assignment]
        RuntimeError("db down")
    )
    try:
        assert prompts._history_backtrack_context("s1", "之前说过什么") is None
    finally:
        db.list_messages = original


def test_backtrack_empty_session_returns_none():
    assert _run("之前说过什么", []) is None


def test_backtrack_blank_query_returns_none():
    assert _run("  ", _long_rows()) is None


# ---- 公共检索模块（app.db.retrieval） ----

def test_retrieval_tokenize_covers_words_cjk_bigrams():
    tokens = retrieval.tokenize("巴黎出差 Paris2024")
    assert "巴黎" in tokens
    assert "黎出" in tokens
    assert "paris2024" in tokens  # 连续字母数字被整体切为一个小写词


def test_retrieval_rank_documents_relevant_first():
    docs = [
        "下周三去巴黎出差住万豪酒店",
        "写一首关于大海的诗",
        "帮我查一下今天股票行情",
    ]
    hits = retrieval.rank_documents("之前说的巴黎酒店", docs, top_k=3)
    assert hits and hits[0][1] == 0  # 巴黎文档排第一


def test_retrieval_rank_documents_empty_query():
    assert retrieval.rank_documents("", ["任意内容"]) == []
    assert retrieval.rank_documents("  ", ["任意内容"]) == []
