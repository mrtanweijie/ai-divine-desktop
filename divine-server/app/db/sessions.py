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
                "SELECT * FROM sessions WHERE project_id = ? "
                "ORDER BY updated_at DESC",
                (project_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC"
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
