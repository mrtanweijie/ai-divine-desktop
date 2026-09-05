import asyncio
from datetime import datetime, timedelta, timezone


def test_scheduler_advances_due_task(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    workspace_dir = tmp_path / "workspace"
    db_path = tmp_path / "smoke.db"
    monkeypatch.setenv("DIVINE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(workspace_dir))
    monkeypatch.setenv("DB_PATH", str(db_path))

    from app import db
    from app.scheduler import Scheduler

    db.init_db()
    project = db.create_project("Scheduler", str(workspace_dir))
    session = db.create_session("Timer", project["id"])
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    task = db.create_scheduled_task(
        title="提醒",
        description="到点提醒",
        session_id=session["id"],
        task_type="reminder",
        frequency="once",
        next_run_at=past,
    )

    asyncio.run(Scheduler()._advance(task))
    updated = db.get_scheduled_task(task["id"])
    assert updated["status"] == "done"
    assert updated["last_run_at"] is not None
    assert updated["next_run_at"] is None
