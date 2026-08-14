"""Message and message-part repository."""

from __future__ import annotations

from contextlib import closing
from typing import Any

from .connection import _connect, _new_id, _now

def clear_messages(session_id: str) -> None:
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM tool_runs WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM agent_todos WHERE session_id = ?", (session_id,))
        conn.execute(
            "UPDATE sessions SET title = '新对话', updated_at = ? WHERE id = ?",
            (_now(), session_id),
        )
        conn.commit()

def add_message(
    session_id: str, role: str, content: str, created_at: str | None = None
) -> dict[str, Any]:
    message_id = _new_id()
    now = created_at or _now()
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (message_id, session_id, role, content, now),
        )
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id)
        )
        conn.commit()
    return get_message(message_id)

def get_message(message_id: str) -> dict[str, Any]:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT * FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
    return dict(row)

def list_messages(session_id: str) -> list[dict[str, Any]]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC, rowid ASC",
            (session_id,),
        ).fetchall()
    return [dict(row) for row in rows]

def add_message_part(
    message_id: str, part_type: str, content: str, order: int = 0
) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO message_parts (id, message_id, type, content, \"order\") VALUES (?, ?, ?, ?, ?)",
            (_new_id(), message_id, part_type, content, order),
        )
        conn.commit()
