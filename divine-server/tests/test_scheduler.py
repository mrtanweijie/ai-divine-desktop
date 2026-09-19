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


def test_migration_adds_027_columns(monkeypatch, tmp_path):
    """027 设计：init_db 后 scheduled_tasks 必有 6 个新列，task_runs 表存在。"""
    db_path = tmp_path / "migration.db"
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("DB_PATH", str(db_path))

    from app import db

    db.init_db()
    with db.get_conn() as conn:
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(scheduled_tasks)")
        }
    assert {
        "prompt",
        "model_id",
        "allow_full_access",
        "delivery_json",
        "interactive_json",
        "pending_user_action",
    } <= cols, f"missing 027 columns: {cols}"

    with db.get_conn() as conn:
        runs_exists = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='task_runs'"
        ).fetchone()
    assert runs_exists, "task_runs table not created"


def test_dispatch_routes_reminder_and_agent_through_handlers(
    monkeypatch, tmp_path,
):
    """stage 1 行为约束：reminder / agent / monitor 走 dispatcher 后行为不变。

    这里仅校验 dispatcher 找得到 handler、不抛异常；具体副作用在各自 handler
    的测试里覆盖。"""
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "smoke.db"))

    from app.agent import tasks as task_dispatcher

    assert "reminder" in task_dispatcher.HANDLERS, "reminder handler missing"
    assert "agent" in task_dispatcher.HANDLERS, "agent handler missing"
    assert "monitor" in task_dispatcher.HANDLERS, "monitor handler missing"

    # 未注册类型：不抛
    asyncio.run(task_dispatcher.run_task({"task_type": "nonsense", "id": "x"}))
