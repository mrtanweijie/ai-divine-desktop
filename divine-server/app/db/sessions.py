"""Session repository."""

from __future__ import annotations

from contextlib import closing
from typing import Any

from .connection import _connect, _new_id, _now
from .projects import default_project

def session_workspace(session_id: str) -> str | None:
    with closing(_connect()) as conn:
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
    with closing(_connect()) as conn:
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
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    return dict(row) if row else None

def list_sessions(project_id: str | None = None) -> list[dict[str, Any]]:
    with closing(_connect()) as conn:
        if project_id:
            rows = conn.execute(
                "SELECT s.*, "
                "(SELECT m.content FROM messages m "
                "WHERE m.session_id = s.id AND m.role = 'user' "
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
    with closing(_connect()) as conn:
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
        conn.commit()
    return get_session(session_id)

def touch_session(session_id: str) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?", (_now(), session_id)
        )
        conn.commit()

def delete_session(session_id: str) -> None:
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()


def search_sessions(
    query: str, project_id: str | None = None, limit: int = 20
) -> list[dict[str, Any]]:
    """全文搜索会话标题和消息内容。"""
    query = query.strip()
    if not query:
        return []

    with closing(_connect()) as conn:
        # 检查 FTS5 表是否存在，不存在则惰性创建
        fts_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions_fts'"
        ).fetchone()
        if not fts_exists:
            try:
                from .migrations import FTS5_SCHEMA, rebuild_fts5
                conn.executescript(FTS5_SCHEMA)
                rebuild_fts5(conn)
                fts_exists = True
            except Exception:
                fts_exists = False

        if not fts_exists:
            # FTS5 不可用，降级为标题 LIKE 搜索
            if project_id:
                rows = conn.execute(
                    "SELECT * FROM sessions WHERE project_id = ? "
                    "AND title LIKE ? ORDER BY updated_at DESC LIMIT ?",
                    (project_id, f"%{query}%", limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM sessions WHERE title LIKE ? "
                    "ORDER BY updated_at DESC LIMIT ?",
                    (f"%{query}%", limit),
                ).fetchall()
            return [dict(row) for row in rows]

        # 重建 FTS5 索引以确保数据最新
        try:
            from .migrations import rebuild_fts5
            rebuild_fts5(conn)
        except Exception:
            pass

        # FTS5 搜索
        try:
            sql = """
                SELECT s.*,
                       snippet(sessions_fts, 2, '<mark>', '</mark>', '...', 32) AS snippet,
                       rank
                FROM sessions_fts
                JOIN sessions s ON s.id = sessions_fts.session_id
                WHERE sessions_fts MATCH ?
            """
            params: list[Any] = [query]
            if project_id:
                sql += " AND s.project_id = ?"
                params.append(project_id)
            sql += " ORDER BY rank LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]
        except Exception:
            # FTS5 查询语法错误时降级为 LIKE 搜索
            if project_id:
                rows = conn.execute(
                    "SELECT * FROM sessions WHERE project_id = ? "
                    "AND title LIKE ? ORDER BY updated_at DESC LIMIT ?",
                    (project_id, f"%{query}%", limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM sessions WHERE title LIKE ? "
                    "ORDER BY updated_at DESC LIMIT ?",
                    (f"%{query}%", limit),
                ).fetchall()
            return [dict(row) for row in rows]
