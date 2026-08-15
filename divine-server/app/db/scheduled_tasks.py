"""Scheduled task repository."""

from __future__ import annotations

import json
from contextlib import closing
from typing import Any

from .connection import _connect, _new_id, _now

def pause_tasks_for_session(session_id: str) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            "UPDATE scheduled_tasks SET status = 'paused', updated_at = ? "
            "WHERE session_id = ? AND status = 'active'",
            (_now(), session_id),
        )
        conn.commit()

def list_scheduled_tasks() -> list[dict[str, Any]]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled_tasks ORDER BY created_at ASC, rowid ASC"
        ).fetchall()
    return [_normalize_task(dict(row)) for row in rows]

def get_scheduled_task(task_id: str) -> dict[str, Any] | None:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT * FROM scheduled_tasks WHERE id = ?", (task_id,)
        ).fetchone()
    return _normalize_task(dict(row)) if row else None

def _normalize_task(task: dict[str, Any]) -> dict[str, Any]:
    try:
        task["days_of_week"] = json.loads(task.get("days_of_week") or "[]")
    except (json.JSONDecodeError, TypeError):
        task["days_of_week"] = []
    return task

def create_scheduled_task(
    *,
    title: str,
    description: str = "",
    session_id: str | None = None,
    task_type: str = "reminder",
    frequency: str = "interval",
    interval_minutes: int | None = None,
    run_at: str | None = None,
    run_hour: int | None = None,
    run_minute: int | None = None,
    days_of_week: list[int] | None = None,
    day_of_month: int | None = None,
    next_run_at: str | None = None,
    status: str = "active",
) -> dict[str, Any]:
    task_id = _new_id()
    now = _now()
    days = json.dumps(list(days_of_week or []), ensure_ascii=False)
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO scheduled_tasks "
            "(id, session_id, title, description, task_type, frequency, "
            "interval_minutes, run_at, run_hour, run_minute, days_of_week, "
            "day_of_month, next_run_at, last_run_at, status, calendar_synced, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, 0, ?, ?)",
            (
                task_id,
                session_id,
                title,
                description,
                task_type,
                frequency,
                interval_minutes,
                run_at,
                run_hour,
                run_minute,
                days,
                day_of_month,
                next_run_at,
                status,
                now,
                now,
            ),
        )
        conn.commit()
    return get_scheduled_task(task_id)

def update_scheduled_task(
    task_id: str,
    **fields: Any,
) -> dict[str, Any]:
    task = get_scheduled_task(task_id)
    if not task:
        raise KeyError(task_id)
    merged = {**task, **{k: v for k, v in fields.items() if v is not None}}
    columns = [
        "title",
        "description",
        "session_id",
        "task_type",
        "frequency",
        "interval_minutes",
        "run_at",
        "run_hour",
        "run_minute",
        "days_of_week",
        "day_of_month",
        "next_run_at",
        "last_run_at",
        "status",
        "calendar_synced",
    ]
    values: list[Any] = []
    assignments: list[str] = []
    for column in columns:
        if column in fields:
            value = fields[column]
            if column == "days_of_week":
                value = json.dumps(list(value or []), ensure_ascii=False)
            assignments.append(f"{column} = ?")
            values.append(value)
    if not assignments:
        return task
    values.append(_now())
    values.append(task_id)
    with closing(_connect()) as conn:
        conn.execute(
            f"UPDATE scheduled_tasks SET {', '.join(assignments)}, updated_at = ? "
            "WHERE id = ?",
            values,
        )
        conn.commit()
    return get_scheduled_task(task_id)

def delete_scheduled_task(task_id: str) -> None:
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))
        conn.commit()
