"""拼音/模糊搜索：查询改写器纯函数 + 拼音副表召回端到端。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.fts_query import (  # noqa: E402
    build_or_match,
    build_pinyin_match,
    is_pinyin_query,
    is_short_query,
    segment_syllables,
)


def test_segment_syllables():
    assert segment_syllables("zhifu") == ["zhi", "fu"]
    assert segment_syllables("zhifujiekou") == ["zhi", "fu", "jie", "kou"]
    # 贪心最长："xian" 优先整体音节（与输入法习惯一致）
    assert segment_syllables("xian") == ["xian"]
    assert segment_syllables("zhangsan") == ["zhang", "san"]
    # 无法切分
    assert segment_syllables("zhif") is None
    assert segment_syllables("hello") is None


def test_is_pinyin_query():
    assert is_pinyin_query("zhifu")
    assert is_pinyin_query("zhi fu")   # 带空格的分写
    assert is_pinyin_query("zs")       # 首字母缩写
    assert is_pinyin_query("wx")
    assert not is_pinyin_query("hello")   # 5 字母且不可切分
    assert not is_pinyin_query("zhifu123")
    assert not is_pinyin_query("支付")
    assert not is_pinyin_query("z")       # 单字符不召回


def test_build_pinyin_match_forms():
    expr = build_pinyin_match("zhifu")
    assert expr is not None
    # 连写 token + 前缀 + 分写短语 + 末音节前缀
    assert "zhifu" in expr
    assert "zhifu*" in expr
    assert "zhi fu" in expr
    assert "zhi fu*" in expr

    # 缩写形式
    expr = build_pinyin_match("zs")
    assert expr is not None
    assert "z* s*" in expr

    # 非拼音输入
    assert build_pinyin_match("支付") is None
    assert build_pinyin_match("hello") is None


def test_build_or_match():
    assert build_or_match("支付宝 微信") == '"支付宝" OR "微信"'
    assert build_or_match("单词条") is None
    assert build_or_match("") is None


def test_is_short_query():
    assert is_short_query("支付")
    assert is_short_query("zh")
    assert not is_short_query("支付宝")
    assert not is_short_query("zhifu")


def _setup_db(monkeypatch, tmp_path):
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "smoke.db"))
    from app import db

    db.init_db()
    return db


def test_pinyin_recall_end_to_end(monkeypatch, tmp_path):
    db = _setup_db(monkeypatch, tmp_path)
    session = db.create_session("支付会话")
    db.add_message(session["id"], "user", "帮我看看支付宝的账单")

    # 拼音整词命中中文内容
    results = db.search_sessions("zhifu")
    assert session["id"] in [r["id"] for r in results]

    # 拼音分写短语
    results = db.search_sessions("zhi fu")
    assert session["id"] in [r["id"] for r in results]

    # 拼音前缀（部分输入）
    results = db.search_sessions("zhif")
    assert session["id"] in [r["id"] for r in results]


def test_chinese_substring_recall(monkeypatch, tmp_path):
    """trigram：≥3 字中文子串（此前 unicode61 从未生效的能力）。"""
    db = _setup_db(monkeypatch, tmp_path)
    session = db.create_session("会话")
    db.add_message(session["id"], "user", "这是一条关于支付宝接口的长消息")

    for query in ("支付宝", "接口", "支付宝接口", "长消息"):
        results = db.search_sessions(query)
        assert session["id"] in [r["id"] for r in results], query


def test_short_cjk_query_like_fallback(monkeypatch, tmp_path):
    db = _setup_db(monkeypatch, tmp_path)
    session = db.create_session("会话")
    db.add_message(session["id"], "user", "合同金额为两万元整")

    results = db.search_sessions("金额")
    assert session["id"] in [r["id"] for r in results]


def test_pinyin_hits_return_preview_snippet(monkeypatch, tmp_path):
    db = _setup_db(monkeypatch, tmp_path)
    session = db.create_session("英文会话")
    db.add_message(session["id"], "user", "包含 zhifu 字样的英文原文")

    results = db.search_sessions("zhifu")
    hit = next(r for r in results if r["id"] == session["id"])
    assert hit["snippet"]  # 精确命中带 <mark>，拼音命中带 preview，非空即可


def test_pinyin_table_synced_on_write(monkeypatch, tmp_path):
    db = _setup_db(monkeypatch, tmp_path)
    session = db.create_session("同步测试")
    db.add_message(session["id"], "user", "测试数据内容")

    # 首次搜索触发 ensure_schema（建主表 + 拼音副表 + 全量灌索引）
    assert db.search_sessions("测试数据")

    from app.db.connection import get_conn

    with get_conn() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM sessions_pinyin_fts WHERE session_id = ?",
            (session["id"],),
        ).fetchone()["c"]
    assert count >= 1

    # 写钩子继续增量维护拼音副表
    db.add_message(session["id"], "user", "新加的 tianjia 内容")
    with get_conn() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM sessions_pinyin_fts WHERE session_id = ?",
            (session["id"],),
        ).fetchone()["c"]
    assert count >= 2

    db.delete_session(session["id"])
    with get_conn() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM sessions_pinyin_fts WHERE session_id = ?",
            (session["id"],),
        ).fetchone()["c"]
    assert count == 0


def test_fts_version_migration(monkeypatch, tmp_path):
    """旧版 unicode61 表（v1）在首次搜索时升级为 trigram 并重建。"""
    db = _setup_db(monkeypatch, tmp_path)
    session = db.create_session("迁移测试")
    db.add_message(session["id"], "user", "中文迁移内容")

    # 手工伪造 v1 状态：unicode61 表 + 版本标记
    from app.db.connection import get_conn
    from app.db.migrations import rebuild_fts5

    with get_conn() as conn:
        conn.executescript(
            "DROP TABLE IF EXISTS sessions_fts;"
            "CREATE VIRTUAL TABLE sessions_fts USING fts5("
            "  session_id UNINDEXED, title, content, tokenize='unicode61');"
        )
        conn.execute(
            "INSERT INTO fts_state (key, value) VALUES ('fts_version', '1') "
            "ON CONFLICT(key) DO UPDATE SET value = '1'"
        )
        conn.commit()
    rebuild_fts5()

    # 旧表下 3 字中文短语搜不到（unicode61 缺陷），升级后必须能搜到
    assert db.search_sessions("迁移内容")
    from app.db.fts import FTS_VERSION

    with get_conn() as conn:
        version = conn.execute(
            "SELECT value FROM fts_state WHERE key = 'fts_version'"
        ).fetchone()["value"]
    assert version == str(FTS_VERSION)


def test_english_substring_case_insensitive(monkeypatch, tmp_path):
    db = _setup_db(monkeypatch, tmp_path)
    session = db.create_session("英文测试")
    db.add_message(session["id"], "user", "the Dockerfile uses BuildKit")

    results = db.search_sessions("dockerfile")
    assert session["id"] in [r["id"] for r in results]
