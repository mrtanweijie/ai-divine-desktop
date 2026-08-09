from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def compute_next_run(task: dict[str, Any]) -> str | None:
    """Return the next UTC run time for a scheduled task."""
    now = datetime.now(timezone.utc)
    frequency = task.get("frequency") or "interval"
    if frequency == "once":
        parsed = parse_dt(task.get("run_at"))
        return iso(parsed) if parsed else None

    if frequency == "interval":
        try:
            minutes = int(task.get("interval_minutes") or 0)
        except (TypeError, ValueError):
            return None
        if minutes <= 0:
            return None
        base = parse_dt(task.get("next_run_at")) or now
        if base <= now:
            base = now
        return iso(base + timedelta(minutes=minutes))

    try:
        hour = int(task.get("run_hour") if task.get("run_hour") is not None else 8)
        minute = int(
            task.get("run_minute") if task.get("run_minute") is not None else 0
        )
    except (TypeError, ValueError):
        return None

    if frequency == "daily":
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return iso(candidate)

    if frequency == "weekly":
        days = task.get("days_of_week") or []
        if not days:
            days = [now.weekday()]
        for offset in range(1, 8):
            candidate = now + timedelta(days=offset)
            if candidate.weekday() in days:
                candidate = candidate.replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                return iso(candidate)
        return None

    if frequency == "monthly":
        try:
            day = int(task.get("day_of_month") or 1)
        except (TypeError, ValueError):
            return None
        for offset in range(0, 62):
            candidate = now + timedelta(days=offset)
            if candidate.day != day:
                continue
            candidate = candidate.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            if candidate > now:
                return iso(candidate)
        return None

    return None
