"""Session repository."""

from __future__ import annotations

import logging
from typing import Any

from .connection import get_conn, _new_id, _now
from . import fts as fts_index
from . import fts_query
from .projects import default_project

logger = logging.getLogger(__name__)

def session_workspace(session_id: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT p.path FROM sessions s "
            "JOIN projects p ON p.id = s.project_id "
            "WHERE s.id = ?",
            (session_id,),
        ).fetchone()
    return str(row["path"]) if row else None

def create_session(
    title: str | None = None,
    project_id: str | None = None,
    approval_mode: str | None = None,
    locale: str | None = None,
) -> dict[str, Any]:
    session_id = _new_id()
    now = _now()
    if not project_id:
        project_id = default_project()["id"]
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions "
            "(id, title, project_id, approval_mode, locale, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                title or "新对话",
                project_id,
                approval_mode or "ask",
                locale or "zh-CN",
                now,
                now,
            ),
        )
        conn.commit()
    return get_session(session_id)

def get_session(session_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    return dict(row) if row else None

def list_sessions(project_id: str | None = None) -> list[dict[str, Any]]:
    with get_conn() as conn:
        if project_id:
            rows = conn.execute(
                "SELECT s.*, "
                "(SELECT m.content FROM messages m "
                "WHERE m.session_id = s.id AND m.role = 'user' "
                # 静默回合（面板动作）的消息不参与预览：会话列表不该显示
                # "提交参数（…）"这种面板回执（design 028 §8.5）。
                "AND m.source <> 'surface_action' "
                "ORDER BY m.created_at DESC LIMIT 1) AS last_message "
                "FROM sessions s WHERE s.project_id = ? "
                "ORDER BY s.updated_at DESC",
                (project_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT s.*, "
                "(SELECT m.content FROM messages m "
                "WHERE m.session_id = s.id AND m.role = 'user' "
                # 静默回合（面板动作）的消息不参与预览：会话列表不该显示
                # "提交参数（…）"这种面板回执（design 028 §8.5）。
                "AND m.source <> 'surface_action' "
                "ORDER BY m.created_at DESC LIMIT 1) AS last_message "
                "FROM sessions s ORDER BY s.updated_at DESC"
            ).fetchall()
    return [dict(row) for row in rows]

def update_session(
    session_id: str,
    title: str | None = None,
    approval_mode: str | None = None,
    plan_mode: str | None = None,
    locale: str | None = None,
) -> dict[str, Any]:
    session = get_session(session_id)
    if not session:
        raise KeyError(session_id)
    title_changed = title is not None and title != session["title"]
    with get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET title = ?, approval_mode = ?, "
            "plan_mode = ?, locale = ?, updated_at = ? "
            "WHERE id = ?",
            (
                title if title is not None else session["title"],
                approval_mode if approval_mode is not None else session["approval_mode"],
                plan_mode if plan_mode is not None else session.get(
                    "plan_mode", "ask"
                ),
                locale if locale is not None else session.get("locale", "zh-CN"),
                _now(),
                session_id,
            ),
        )
        if title_changed:
            # 标题参与全文索引，改名后按会话增量重建
            fts_index.sync_session(conn, session_id)
        conn.commit()
    return get_session(session_id)

def touch_session(session_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?", (_now(), session_id)
        )
        conn.commit()

def delete_session(session_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        fts_index.remove_session(conn, session_id)
        conn.commit()


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _title_like_rows(
    conn, query: str, project_id: str | None, limit: int
) -> list[dict[str, Any]]:
    """最终兜底：仅标题 LIKE。"""
    pattern = f"%{_escape_like(query)}%"
    if project_id:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE project_id = ? "
            "AND title LIKE ? ESCAPE '\\' ORDER BY updated_at DESC LIMIT ?",
            (project_id, pattern, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE title LIKE ? ESCAPE '\\' "
            "ORDER BY updated_at DESC LIMIT ?",
            (pattern, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def _short_query_rows(
    conn, query: str, project_id: str | None, limit: int
) -> list[dict[str, Any]]:
    """短于 trigram 下限（<3 字符）的查询：正文 LIKE 全表兜底。"""
    pattern = f"%{_escape_like(query)}%"
    sql = (
        "SELECT s.*, "
        "(SELECT m.content FROM messages m WHERE m.session_id = s.id "
        " AND m.content LIKE ? ESCAPE '\\' ORDER BY m.rowid LIMIT 1) AS snippet "
        "FROM sessions s WHERE EXISTS ("
        "  SELECT 1 FROM messages m2 WHERE m2.session_id = s.id "
        "  AND m2.content LIKE ? ESCAPE '\\')"
    )
    params: list[Any] = [pattern, pattern]
    if project_id:
        sql += " AND s.project_id = ?"
        params.append(project_id)
    sql += " ORDER BY s.updated_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item.setdefault("rank", 0)
        result.append(item)
    return result


def _match_rows(
    conn,
    match_expr: str,
    user_query: str,
    project_id: str | None,
    limit: int,
    include_pinyin: bool = True,
) -> list[dict[str, Any]]:
    """精确（trigram）+ 拼音两路 MATCH，按会话去重合并。"""
    merged: dict[str, dict[str, Any]] = {}

    sql = """
        SELECT s.*,
               snippet(sessions_fts, 2, '<mark>', '</mark>', '...', 32) AS snippet,
               rank
        FROM sessions_fts
        JOIN sessions s ON s.id = sessions_fts.session_id
        WHERE sessions_fts MATCH ?
    """
    params: list[Any] = [match_expr]
    if project_id:
        sql += " AND s.project_id = ?"
        params.append(project_id)
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)
    try:
        for row in conn.execute(sql, params).fetchall():
            merged[row["id"]] = dict(row)
    except Exception:
        # FTS 语法错误：该路放弃，由调用方走宽松/兜底路径
        return []

    if include_pinyin:
        pinyin_expr = fts_query.build_pinyin_match(user_query)
        if pinyin_expr and fts_index.pinyin_ready(conn):
            psql = """
                SELECT s.*, sessions_pinyin_fts.preview AS snippet, rank
                FROM sessions_pinyin_fts
                JOIN sessions s ON s.id = sessions_pinyin_fts.session_id
                WHERE sessions_pinyin_fts MATCH ?
            """
            pparams: list[Any] = [pinyin_expr]
            if project_id:
                psql += " AND s.project_id = ?"
                pparams.append(project_id)
            psql += " ORDER BY rank LIMIT ?"
            pparams.append(limit)
            try:
                for row in conn.execute(psql, pparams).fetchall():
                    merged.setdefault(row["id"], dict(row))
            except Exception:
                pass

    # 两段稳定排序：先 updated_at 新→旧，再 rank 升序（并列 rank 保留新→旧）
    result = sorted(
        merged.values(),
        key=lambda item: str(item.get("updated_at") or ""),
        reverse=True,
    )
    result.sort(
        key=lambda item: item.get("rank") if item.get("rank") is not None else 1e9
    )
    return result[:limit]


def search_sessions(
    query: str, project_id: str | None = None, limit: int = 20
) -> list[dict[str, Any]]:
    """全文搜索会话标题和消息内容。

    召回管线（依次降级）：
    1. trigram 精确子串 + 拼音副表（zhifu / zhi fu / 首字母缩写）；
    2. 中文多词 0 命中 → 词间 OR 宽松召回；
    3. <3 字符短查询 → 正文 LIKE（trigram 下限）；
    4. 标题 LIKE 兜底（也是 FTS 不可用/语法错误的降级路径）。
    """
    query = query.strip()
    if not query:
        return []

    with get_conn() as conn:
        try:
            # 惰性建表 / 版本升级 / 水位线对账（索引由写钩子增量维护）
            fts_index.ensure_schema(conn)
            fts_index.catchup(conn)
            fts_ok = True
        except Exception:
            logger.exception("FTS 索引初始化失败，降级标题搜索")
            conn.rollback()
            fts_ok = False

        if not fts_ok:
            return _title_like_rows(conn, query, project_id, limit)

        rows = _match_rows(conn, query, query, project_id, limit)
        if not rows:
            or_expr = fts_query.build_or_match(query)
            if or_expr:
                rows = _match_rows(
                    conn, or_expr, query, project_id, limit,
                    include_pinyin=False,
                )
        if not rows and fts_query.is_short_query(query):
            rows = _short_query_rows(conn, query, project_id, limit)
        if rows:
            return rows
        return _title_like_rows(conn, query, project_id, limit)
