"""Agent plan/todo repository."""

from __future__ import annotations

from contextlib import closing
from typing import Any

from .connection import _connect, _new_id, _now

def replace_todos(
    session_id: str, titles: list[str]
) -> list[dict[str, Any]]:
    now = _now()
    with closing(_connect()) as conn:
        conn.execute(
            "DELETE FROM agent_todos WHERE session_id = ?", (session_id,)
        )
        for index, title in enumerate(titles):
            conn.execute(
                "INSERT INTO agent_todos "
                "(id, session_id, \"index\", title, status, result, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'pending', NULL, ?, ?)",
                (_new_id(), session_id, index, title, now, now),
            )
        conn.commit()
    return list_todos(session_id)

def list_todos(session_id: str) -> list[dict[str, Any]]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM agent_todos WHERE session_id = ? "
            "ORDER BY \"index\" ASC, rowid ASC",
            (session_id,),
        ).fetchall()
    return [dict(row) for row in rows]

def update_todo_status(
    todo_id: str, status: str, result: str | None = None
) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            "UPDATE agent_todos SET status = ?, result = ?, updated_at = ? "
            "WHERE id = ?",
            (status, result, _now(), todo_id),
        )
        conn.commit()
