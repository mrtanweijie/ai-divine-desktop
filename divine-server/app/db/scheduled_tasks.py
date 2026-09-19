"""Scheduled task repository."""

from __future__ import annotations

import json
from typing import Any

from .connection import get_conn, _new_id, _now

def pause_tasks_for_session(session_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE scheduled_tasks SET status = 'paused', updated_at = ? "
            "WHERE session_id = ? AND status = 'active'",
            (_now(), session_id),
        )
        conn.commit()

def list_scheduled_tasks() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled_tasks ORDER BY created_at ASC, rowid ASC"
        ).fetchall()
    return [_normalize_task(dict(row)) for row in rows]

def get_scheduled_task(task_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM scheduled_tasks WHERE id = ?", (task_id,)
        ).fetchone()
    return _normalize_task(dict(row)) if row else None

def _normalize_task(task: dict[str, Any]) -> dict[str, Any]:
    try:
        task["days_of_week"] = json.loads(task.get("days_of_week") or "[]")
    except (json.JSONDecodeError, TypeError):
        task["days_of_week"] = []
    # 027 设计：把 JSON 列解码出来，避免上层到处 json.loads
    for key in ("delivery_json", "interactive_json"):
        raw = task.get(key) or "{}"
        try:
            task[key] = json.loads(raw)
        except json.JSONDecodeError:
            task[key] = {}
    if "allow_full_access" in task:
        task["allow_full_access"] = bool(task["allow_full_access"])
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
    prompt: str = "",
    model_id: str | None = None,
    allow_full_access: bool = False,
    delivery: dict[str, Any] | None = None,
    interactive: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_id = _new_id()
    now = _now()
    days = json.dumps(list(days_of_week or []), ensure_ascii=False)
    delivery_json = json.dumps(delivery or {}, ensure_ascii=False)
    interactive_json = json.dumps(interactive or {}, ensure_ascii=False)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO scheduled_tasks "
            "(id, session_id, title, description, task_type, frequency, "
            "interval_minutes, run_at, run_hour, run_minute, days_of_week, "
            "day_of_month, next_run_at, last_run_at, status, calendar_synced, "
            "prompt, model_id, allow_full_access, delivery_json, "
            "interactive_json, pending_user_action, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, 0, "
            "?, ?, ?, ?, ?, NULL, ?, ?)",
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
                prompt,
                model_id,
                1 if allow_full_access else 0,
                delivery_json,
                interactive_json,
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
        # 027 设计：下面 4 列把"执行 / 投递 / 交互"配置下沉到任务本身
        "prompt",
        "model_id",
        "allow_full_access",
        "delivery_json",
        "interactive_json",
        "pending_user_action",
    ]
    values: list[Any] = []
    assignments: list[str] = []
    for column in columns:
        if column in fields:
            value = fields[column]
            if column == "days_of_week":
                value = json.dumps(list(value or []), ensure_ascii=False)
            elif column == "delivery_json" and isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            elif column == "interactive_json" and isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            elif column == "allow_full_access":
                value = 1 if value else 0
            assignments.append(f"{column} = ?")
            values.append(value)
    if not assignments:
        return task
    values.append(_now())
    values.append(task_id)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE scheduled_tasks SET {', '.join(assignments)}, updated_at = ? "
            "WHERE id = ?",
            values,
        )
        conn.commit()
    return get_scheduled_task(task_id)

def delete_scheduled_task(task_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))
        conn.commit()
