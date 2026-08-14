"""Tool run and tool-turn repository."""

from __future__ import annotations

import json
from contextlib import closing
from typing import Any

from .connection import _connect, _json, _new_id, _now
from .messages import add_message, add_message_part

def save_tool_turn(
    session_id: str,
    tool_calls: list[dict[str, Any]],
    think: str,
    results: list[tuple[str, str]],
) -> None:
    if not tool_calls:
        return
    message = add_message(session_id, "assistant", "")
    order = 0
    add_message_part(
        message["id"],
        "tool_calls",
        json.dumps(tool_calls, ensure_ascii=False),
        order=order,
    )
    order += 1
    if think:
        add_message_part(message["id"], "think", think, order=order)
        order += 1
    for call_id, content in results:
        tool_message = add_message(session_id, "tool", content)
        add_message_part(
            tool_message["id"],
            "tool_result",
            json.dumps({"tool_call_id": call_id}, ensure_ascii=False),
            order=0,
        )

def list_message_parts(message_id: str) -> list[dict[str, Any]]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM message_parts WHERE message_id = ? ORDER BY \"order\" ASC, rowid ASC",
            (message_id,),
        ).fetchall()
    return [dict(row) for row in rows]

def add_tool_run(
    session_id: str,
    tool_name: str,
    status: str,
    input_data: dict[str, Any],
    output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_id = _new_id()
    now = _now()
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO tool_runs (id, session_id, tool_name, status, input, output, started_at, finished_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                session_id,
                tool_name,
                status,
                _json(input_data),
                _json(output) if output else None,
                now,
                now if status in ("done", "error") else None,
            ),
        )
        conn.commit()
    return get_tool_run(run_id)

def update_tool_run(
    run_id: str, status: str, output: dict[str, Any] | None = None
) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            "UPDATE tool_runs SET status = ?, output = ?, finished_at = ? WHERE id = ?",
            (status, _json(output) if output else None, _now(), run_id),
        )
        conn.commit()

def list_tool_runs(session_id: str) -> list[dict[str, Any]]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM tool_runs WHERE session_id = ? ORDER BY started_at ASC, rowid ASC",
            (session_id,),
        ).fetchall()
    return [dict(row) for row in rows]

def get_tool_run(run_id: str) -> dict[str, Any]:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT * FROM tool_runs WHERE id = ?", (run_id,)
        ).fetchone()
    return dict(row)
