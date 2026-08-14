from datetime import datetime, timedelta, timezone

from app.schedule_utils import compute_next_run, parse_dt


def test_parse_dt_accepts_iso_and_z_suffix():
    assert parse_dt("2026-08-15T08:00:00+00:00") is not None
    assert parse_dt("2026-08-15T08:00:00Z") is not None
    assert parse_dt("") is None
    assert parse_dt("bad") is None


def test_interval_uses_next_run_as_base():
    base = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    task = {
        "frequency": "interval",
        "interval_minutes": 30,
        "next_run_at": base,
    }
    next_run = compute_next_run(task)
    assert next_run is not None
    assert datetime.fromisoformat(next_run) >= datetime.fromisoformat(base)


def test_daily_returns_future_time():
    task = {
        "frequency": "daily",
        "run_hour": 8,
        "run_minute": 0,
    }
    next_run = compute_next_run(task)
    assert next_run is not None
    assert datetime.fromisoformat(next_run) > datetime.now(timezone.utc)


def test_once_returns_run_at():
    task = {
        "frequency": "once",
        "run_at": "2026-12-31T08:00:00+00:00",
    }
    assert compute_next_run(task) == "2026-12-31T08:00:00+00:00"
