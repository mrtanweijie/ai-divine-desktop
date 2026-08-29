"""Token usage tracking for AI replies (per message + session totals)."""

from __future__ import annotations

from typing import Any

from .connection import get_conn


def save_token_usage(
    session_id: str,
    message_id: str,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    source: str = "real",
) -> None:
    """Record the token consumption of one assistant reply.

    ``source`` is "real" when reported by the model API, "estimated" when
    computed locally as a fallback.
    """
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO token_usage "
            "(session_id, message_id, input_tokens, output_tokens, total_tokens, source) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                session_id,
                message_id,
                int(input_tokens or 0),
                int(output_tokens or 0),
                int(total_tokens or 0),
                source,
            ),
        )
        conn.commit()


def token_usage_totals(session_id: str) -> dict[str, Any]:
    """Cumulative token usage for a session."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(input_tokens), 0) AS input_tokens, "
            "COALESCE(SUM(output_tokens), 0) AS output_tokens, "
            "COALESCE(SUM(total_tokens), 0) AS total_tokens, "
            "COUNT(*) AS turns "
            "FROM token_usage WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return dict(row) if row else {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "turns": 0,
    }
