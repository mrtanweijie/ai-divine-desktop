"""Session summary repository (context compaction state)."""

from __future__ import annotations

from typing import Any

from .connection import get_conn, _now

def get_summary(session_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM session_summaries WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return dict(row) if row else None

def save_summary(
    session_id: str,
    summary: str,
    cutoff_rowid: int,
    saved_tokens: int = 0,
) -> dict[str, Any]:
    now = _now()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO session_summaries "
            "(session_id, summary, cutoff_rowid, saved_tokens, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET "
            "summary = excluded.summary, "
            "cutoff_rowid = excluded.cutoff_rowid, "
            "saved_tokens = excluded.saved_tokens, "
            "updated_at = excluded.updated_at",
            (session_id, summary, int(cutoff_rowid), int(saved_tokens), now, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM session_summaries WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return dict(row)

def delete_summary(session_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM session_summaries WHERE session_id = ?",
            (session_id,),
        )
        conn.commit()
