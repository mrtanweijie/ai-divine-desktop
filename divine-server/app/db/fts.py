"""Incremental FTS5 index maintenance for session search.

两个索引表，均由本模块增量维护（每行对应一条消息）：

- ``sessions_fts``（trigram）：标题 + 正文原文，支持 ≥3 字符中英文子串；
- ``sessions_pinyin_fts``（unicode61）：标题 + 正文（截断）的拼音转写，
  支持拼音检索（zhifu / zhi fu / zs 前缀缩写），preview 列存正文摘要
  供前端展示（拼音命中时正文列没有可高亮的原文）。

维护策略：

- 写路径钩子按会话增量同步（:func:`sync_session` / :func:`remove_session`），
  挂在 add_message / clear_messages / update_session(改名) / delete_session /
  delete_project 上；
- 搜索前用水位线（``fts_state.last_rowid``）对账（:func:`catchup`）：
  绕过钩子的新增被增量补齐，rowid 回退（未走钩子的删除）触发一次全量
  重建自愈——最坏情况等价于旧的"每次全量重建"；
- 拼音副表由后台线程一次性回填（:func:`_backfill_worker`），完成前
  拼音召回部分可用、精确召回始终全覆盖。

注意：不得使用 FTS5 'delete' 特殊命令（旧触发器曾把 TEXT session_id 当
rowid 传入导致 "SQL logic error"，见 migrations._BROKEN_FTS_TRIGGERS），
本模块全部按普通列 DELETE。
"""

from __future__ import annotations

import logging
import threading

from .connection import get_conn

logger = logging.getLogger(__name__)

FTS_VERSION = 2

_STATE_KEY = "last_rowid"
_VERSION_KEY = "fts_version"
_BACKFILL_DONE_KEY = "pinyin_backfill_done"

# 拼音转写的正文截断长度：平衡召回与回填/写入成本
_PINYIN_CONTENT_CAP = 2000

_INSERT_SQL = (
    "INSERT INTO sessions_fts(session_id, title, content) "
    "SELECT s.id, s.title, m.content "
    "FROM sessions s JOIN messages m ON m.session_id = s.id "
)

PINYIN_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS sessions_pinyin_fts USING fts5(
    session_id UNINDEXED,
    pinyin,
    preview UNINDEXED,
    tokenize='unicode61'
);
"""

try:  # pypinyin 为可选增强依赖，缺失时拼音检索整体禁用
    from pypinyin import lazy_pinyin

    _PINYIN_AVAILABLE = True
except ImportError:  # pragma: no cover
    lazy_pinyin = None
    _PINYIN_AVAILABLE = False

_backfill_lock = threading.Lock()
_backfill_started = False


def to_pinyin_text(text: str, cap: int = _PINYIN_CONTENT_CAP) -> str:
    """中文转无声调拼音（音节空格分隔），非中文字符原样保留小写。"""
    if not text:
        return ""
    if not _PINYIN_AVAILABLE:  # pragma: no cover
        return ""
    text = text[:cap]
    pieces = lazy_pinyin(text)
    return " ".join(piece.lower() for piece in pieces if piece.strip())


def _fts_ready(conn) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions_fts'"
    ).fetchone() is not None


def _pinyin_table_ready(conn) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='sessions_pinyin_fts'"
    ).fetchone() is not None


def pinyin_ready(conn) -> bool:
    """拼音召回是否可用（表 + 转写库）。回填未完成时部分可用。"""
    return _PINYIN_AVAILABLE and _pinyin_table_ready(conn)


def _get_state(conn, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM fts_state WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else None


def _set_state(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO fts_state (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def _session_rows(conn, session_id: str):
    return conn.execute(
        "SELECT s.title AS title, m.content AS content "
        "FROM sessions s JOIN messages m ON m.session_id = s.id "
        "WHERE s.id = ?",
        (session_id,),
    ).fetchall()


def _sync_pinyin_rows(conn, session_id: str) -> None:
    """按会话重建拼音副表行（调用方事务内）。"""
    conn.execute(
        "DELETE FROM sessions_pinyin_fts WHERE session_id = ?", (session_id,)
    )
    data = []
    for row in _session_rows(conn, session_id):
        pinyin_text = to_pinyin_text(row["title"] or "")
        content_pinyin = to_pinyin_text(row["content"] or "")
        if content_pinyin:
            pinyin_text = f"{pinyin_text} {content_pinyin}".strip()
        if not pinyin_text:
            continue
        preview = (row["content"] or row["title"] or "")[:120]
        data.append((session_id, pinyin_text, preview))
    if data:
        conn.executemany(
            "INSERT INTO sessions_pinyin_fts(session_id, pinyin, preview) "
            "VALUES (?, ?, ?)",
            data,
        )


def sync_session(conn, session_id: str) -> None:
    """会话级增量重建两张索引（在调用方事务内执行；表未就绪时跳过）。"""
    if not _fts_ready(conn):
        return
    conn.execute("DELETE FROM sessions_fts WHERE session_id = ?", (session_id,))
    conn.execute(_INSERT_SQL + "WHERE s.id = ?", (session_id,))
    if _pinyin_table_ready(conn) and _PINYIN_AVAILABLE:
        _sync_pinyin_rows(conn, session_id)


def remove_session(conn, session_id: str) -> None:
    """删除会话在两张索引中的行。"""
    if not _fts_ready(conn):
        return
    conn.execute("DELETE FROM sessions_fts WHERE session_id = ?", (session_id,))
    if _pinyin_table_ready(conn):
        conn.execute(
            "DELETE FROM sessions_pinyin_fts WHERE session_id = ?", (session_id,)
        )


def purge_orphans(conn) -> None:
    """清理指向已删除会话的索引残行（批量级联删除场景的兜底）。"""
    if not _fts_ready(conn):
        return
    conn.execute(
        "DELETE FROM sessions_fts "
        "WHERE session_id NOT IN (SELECT id FROM sessions)"
    )
    if _pinyin_table_ready(conn):
        conn.execute(
            "DELETE FROM sessions_pinyin_fts "
            "WHERE session_id NOT IN (SELECT id FROM sessions)"
        )


def rebuild(conn) -> None:
    """全量重建（首次接管 / 版本升级 / 水位线自愈）。"""
    if not _fts_ready(conn):
        return
    conn.execute("DELETE FROM sessions_fts")
    conn.execute(_INSERT_SQL)
    if _pinyin_table_ready(conn) and _PINYIN_AVAILABLE:
        conn.execute("DELETE FROM sessions_pinyin_fts")
        for row in conn.execute("SELECT id FROM sessions").fetchall():
            _sync_pinyin_rows(conn, row["id"])


def ensure_schema(conn) -> None:
    """确保索引表为当前版本；旧版/缺失时（重）建并全量灌一次。

    - 主表是 trigram（v2）；v1 的 unicode61 旧表中文短语匹配无效，需重建；
    - 建好后立刻记录水位线，后续靠写钩子 + catchup 维护；
    - 拼音副表回填放后台线程，不阻塞启动与首搜。
    """
    exists = _fts_ready(conn)
    version = _get_state(conn, _VERSION_KEY)
    if exists and version == str(FTS_VERSION):
        conn.executescript(PINYIN_FTS_SCHEMA)
        _kick_backfill_async(conn)
        return
    if exists:
        logger.info("FTS 索引版本升级（%s -> %s），重建一次", version, FTS_VERSION)
        conn.execute("DROP TABLE IF EXISTS sessions_fts")
    from .migrations import FTS5_SCHEMA

    conn.executescript(FTS5_SCHEMA)
    conn.executescript(PINYIN_FTS_SCHEMA)
    rebuild(conn)
    _set_state(conn, _VERSION_KEY, str(FTS_VERSION))
    max_rowid = conn.execute(
        "SELECT COALESCE(MAX(rowid), 0) AS m FROM messages"
    ).fetchone()["m"]
    _set_state(conn, _STATE_KEY, str(max_rowid))
    _kick_backfill_async(conn)


def catchup(conn) -> None:
    """搜索前对账：正常情况只是一次 MAX(rowid)，纳秒级。

    - 无水位线（首次接管）：全量重建一次并记录；
    - 水位线落后：增量补齐 rowid > 水位线的新消息所在会话；
    - 水位线回退：存在绕过钩子的删除，全量重建自愈。
    """
    if not _fts_ready(conn):
        return
    max_rowid = conn.execute(
        "SELECT COALESCE(MAX(rowid), 0) AS m FROM messages"
    ).fetchone()["m"]
    raw = _get_state(conn, _STATE_KEY)
    if raw is None:
        rebuild(conn)
        _set_state(conn, _STATE_KEY, str(max_rowid))
        return
    try:
        last = int(raw)
    except ValueError:
        last = 0
    if max_rowid == last:
        return
    if max_rowid < last:
        logger.info(
            "FTS 水位线回退（%s -> %s），全量重建自愈", last, max_rowid
        )
        rebuild(conn)
    else:
        session_ids = [
            row["session_id"]
            for row in conn.execute(
                "SELECT DISTINCT session_id FROM messages WHERE rowid > ?",
                (last,),
            )
        ]
        for sid in session_ids:
            sync_session(conn, sid)
    _set_state(conn, _STATE_KEY, str(max_rowid))


def _kick_backfill_async(conn) -> None:
    """拼音副表未回填完成时，启动一次性后台线程（进程内至多一个）。"""
    global _backfill_started
    if not _PINYIN_AVAILABLE:
        return
    if _get_state(conn, _BACKFILL_DONE_KEY) == "1":
        return
    with _backfill_lock:
        if _backfill_started:
            return
        _backfill_started = True
    thread = threading.Thread(
        target=_backfill_worker, name="fts-pinyin-backfill", daemon=True
    )
    thread.start()


def _backfill_worker() -> None:
    try:
        with get_conn() as conn:
            done_ids = {
                row["session_id"]
                for row in conn.execute(
                    "SELECT DISTINCT session_id FROM sessions_pinyin_fts"
                )
            }
            while True:
                pending = [
                    row["id"]
                    for row in conn.execute("SELECT id FROM sessions").fetchall()
                    if row["id"] not in done_ids
                ]
                if not pending:
                    _set_state(conn, _BACKFILL_DONE_KEY, "1")
                    conn.commit()
                    break
                for sid in pending[:50]:
                    _sync_pinyin_rows(conn, sid)
                    done_ids.add(sid)
                conn.commit()
        logger.info("FTS 拼音副表回填完成")
    except Exception:  # noqa: BLE001 — 回填失败不影响精确搜索，下次启动重试
        logger.exception("FTS 拼音副表回填失败，将在下次启动重试")
