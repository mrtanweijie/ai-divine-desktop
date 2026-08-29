"""Message and message-part repository."""

from __future__ import annotations

import json
from typing import Any

from .connection import get_conn, _new_id, _now

def clear_messages(session_id: str) -> None:
    with get_conn() as conn:
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
    with get_conn() as conn:
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
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
    return dict(row)

def _attach_token_usage(message: dict[str, Any], row) -> None:
    """Attach token_usage (if any) from a LEFT JOIN row onto the message dict."""
    usage_total = row["usage_total"]
    for key in ("usage_input", "usage_output", "usage_total", "usage_source"):
        message.pop(key, None)
    if usage_total is not None:
        message["token_usage"] = {
            "input_tokens": int(row["usage_input"] or 0),
            "output_tokens": int(row["usage_output"] or 0),
            "total_tokens": int(usage_total or 0),
            "source": row["usage_source"] or "real",
        }


def list_messages(session_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT m.*, u.input_tokens AS usage_input, "
            "u.output_tokens AS usage_output, u.total_tokens AS usage_total, "
            "u.source AS usage_source "
            "FROM messages m "
            "LEFT JOIN token_usage u ON u.message_id = m.id "
            "WHERE m.session_id = ? ORDER BY m.created_at ASC, m.rowid ASC",
            (session_id,),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        message = _decode_choice_state(dict(row))
        _attach_token_usage(message, row)
        result.append(message)
    return result


def get_message(message_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
    return _decode_choice_state(dict(row)) if row else {}


def _decode_choice_state(message: dict[str, Any]) -> dict[str, Any]:
    """把 messages.choice_state（JSON 文本）解析为 dict 字段 choice_state。"""
    raw = message.get("choice_state")
    if isinstance(raw, str) and raw:
        try:
            message["choice_state"] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            message["choice_state"] = {}
    else:
        message["choice_state"] = {}
    return message


def update_choice_state(message_id: str, state: dict[str, Any]) -> dict[str, Any]:
    """保存选项卡片的已选状态（selected/sentCustom 等），返回更新后的消息。"""
    payload = json.dumps(state or {}, ensure_ascii=False)
    with get_conn() as conn:
        conn.execute(
            "UPDATE messages SET choice_state = ? WHERE id = ?",
            (payload, message_id),
        )
        conn.commit()
    return get_message(message_id)

def add_message_part(
    message_id: str, part_type: str, content: str, order: int = 0
) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO message_parts (id, message_id, type, content, \"order\") VALUES (?, ?, ?, ?, ?)",
            (_new_id(), message_id, part_type, content, order),
        )
        conn.commit()
