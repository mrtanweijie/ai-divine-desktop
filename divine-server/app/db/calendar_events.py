"""Calendar event repository."""

from __future__ import annotations

from typing import Any

from .connection import get_conn, _new_id, _now

def list_calendar_events() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM calendar_events ORDER BY start_at ASC, rowid ASC"
        ).fetchall()
    return [dict(row) for row in rows]

def get_calendar_event(event_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM calendar_events WHERE id = ?", (event_id,)
        ).fetchone()
    return dict(row) if row else None

def create_calendar_event(
    *,
    title: str,
    start_at: str,
    end_at: str | None = None,
    notes: str = "",
    location: str = "",
    task_id: str | None = None,
) -> dict[str, Any]:
    event_id = _new_id()
    now = _now()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO calendar_events "
            "(id, title, start_at, end_at, notes, location, task_id, "
            "system_event_id, synced, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 0, ?, ?)",
            (event_id, title, start_at, end_at, notes, location, task_id, now, now),
        )
        conn.commit()
    return get_calendar_event(event_id)

def update_calendar_event(
    event_id: str,
    **fields: Any,
) -> dict[str, Any]:
    event = get_calendar_event(event_id)
    if not event:
        raise KeyError(event_id)
    columns = [
        "title",
        "start_at",
        "end_at",
        "notes",
        "location",
        "task_id",
        "system_event_id",
        "synced",
    ]
    values: list[Any] = []
    assignments: list[str] = []
    for column in columns:
        if column in fields and fields[column] is not None:
            assignments.append(f"{column} = ?")
            values.append(fields[column])
    if not assignments:
        return event
    values.append(_now())
    values.append(event_id)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE calendar_events SET {', '.join(assignments)}, updated_at = ? "
            "WHERE id = ?",
            values,
        )
        conn.commit()
    return get_calendar_event(event_id)

def delete_calendar_event(event_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM calendar_events WHERE id = ?", (event_id,))
        conn.commit()
