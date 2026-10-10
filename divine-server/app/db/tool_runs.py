"""Tool run and tool-turn repository."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from .connection import get_conn, _json, _new_id, _now
from .messages import add_message, add_message_part

def save_tool_turn(
    session_id: str,
    tool_calls: list[dict[str, Any]],
    think: str,
    results: list[tuple[str, str]],
) -> str:
    """落一轮工具调用（assistant 空正文 + tool 结果），返回承载消息 id。

    返回值供 ``_persist_new_messages`` 在"本轮没有 assistant 正文"时兜底承载
    A2UI 面板（design 028 §8.5）：以前面板在这种情况下会被整块丢掉。
    """
    if not tool_calls:
        return ""
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
    return str(message["id"])

def list_message_parts(message_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
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
    turn: int | None = None,
) -> dict[str, Any]:
    run_id = _new_id()
    now = _now()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO tool_runs (id, session_id, tool_name, status, input, output, started_at, finished_at, turn) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                session_id,
                tool_name,
                status,
                _json(input_data),
                _json(output) if output else None,
                now,
                now if status in ("done", "error") else None,
                turn,
            ),
        )
        conn.commit()
    return get_tool_run(run_id)

def update_tool_run(
    run_id: str,
    status: str,
    output: dict[str, Any] | None = None,
    duration_ms: int | None = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE tool_runs SET status = ?, output = ?, finished_at = ?, duration_ms = ? WHERE id = ?",
            (status, _json(output) if output else None, _now(), duration_ms, run_id),
        )
        conn.commit()

def list_tool_runs(session_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM tool_runs WHERE session_id = ? ORDER BY started_at ASC, rowid ASC",
            (session_id,),
        ).fetchall()
    return [dict(row) for row in rows]

def recent_tool_runs(
    session_id: str, limit: int = 5
) -> list[dict[str, Any]]:
    """Most recent tool runs for a session, oldest-first within the window."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM tool_runs WHERE session_id = ? "
            "ORDER BY started_at DESC, rowid DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]

def get_tool_run(run_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM tool_runs WHERE id = ?", (run_id,)
        ).fetchone()
    return dict(row) if row else None


def prune_tool_runs(keep_days: int = 30, max_rows: int = 50_000) -> int:
    """清理过期工具运行记录，防止 tool_runs 无限膨胀。

    每次工具调用落一行（含 input/output JSON），长期使用会拖慢查询与
    备份。保留最近 keep_days 天内的记录，且全表最多保留最新 max_rows 行。
    返回删除的行数。
    """
    deleted = 0
    # _now() 为 ISO-UTC 文本，与列内格式一致，可直接字符串比较
    cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).isoformat(
        timespec="seconds"
    )
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM tool_runs WHERE started_at IS NOT NULL AND started_at < ?",
            (cutoff,),
        )
        deleted += cur.rowcount
        total = conn.execute("SELECT COUNT(*) FROM tool_runs").fetchone()[0]
        if total > max_rows:
            cur = conn.execute(
                "DELETE FROM tool_runs WHERE id IN ("
                "SELECT id FROM tool_runs ORDER BY started_at DESC "
                "LIMIT -1 OFFSET ?)",
                (max_rows,),
            )
            deleted += cur.rowcount
    return deleted
