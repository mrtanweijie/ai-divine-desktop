from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app import db  # noqa: E402
from app.schedule_utils import compute_next_run  # noqa: E402


def _ok(message: str, data: dict | None = None) -> None:
    print(
        json.dumps(
            {"success": True, "message": message, "data": data},
            ensure_ascii=False,
        )
    )


def _err(message: str) -> None:
    print(json.dumps({"success": False, "message": message}, ensure_ascii=False))


def _int(value, default=None):
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _create(params: dict) -> None:
    title = str(params.get("title") or "").strip()
    if not title:
        _err("创建定时任务需要 title")
        return
    frequency = str(params.get("frequency") or "interval")
    interval_minutes = _int(params.get("interval_minutes"))
    run_at = params.get("run_at")
    run_hour = _int(params.get("run_hour"))
    run_minute = _int(params.get("run_minute"))
    days_of_week = params.get("days_of_week") or []
    day_of_month = _int(params.get("day_of_month"))

    if frequency == "interval" and (interval_minutes is None or interval_minutes <= 0):
        _err("interval 模式需要有效的 interval_minutes")
        return
    if frequency == "once" and not run_at:
        _err("once 模式需要 run_at")
        return
    if frequency == "weekly" and not days_of_week:
        _err("weekly 模式需要 days_of_week")
        return
    if frequency == "monthly" and day_of_month is None:
        _err("monthly 模式需要 day_of_month")
        return

    values = {
        "frequency": frequency,
        "interval_minutes": interval_minutes,
        "run_at": run_at,
        "run_hour": run_hour if run_hour is not None else 8,
        "run_minute": run_minute if run_minute is not None else 0,
        "days_of_week": list(days_of_week),
        "day_of_month": day_of_month,
    }
    task = db.create_scheduled_task(
        title=title,
        description=str(params.get("description") or "").strip(),
        frequency=frequency,
        interval_minutes=interval_minutes,
        run_at=run_at,
        run_hour=values["run_hour"],
        run_minute=values["run_minute"],
        days_of_week=values["days_of_week"],
        day_of_month=day_of_month,
        next_run_at=compute_next_run(values),
    )
    _ok(
        f"定时任务已创建：{task['title']}",
        {"task": task, "tasks": db.list_scheduled_tasks()},
    )


def _update(params: dict) -> None:
    task_id = str(params.get("task_id") or "")
    if not task_id or db.get_scheduled_task(task_id) is None:
        _err("更新定时任务需要有效的 task_id")
        return
    fields: dict = {}
    for key in (
        "title",
        "description",
        "frequency",
        "run_at",
        "days_of_week",
        "day_of_month",
    ):
        if params.get(key) is not None:
            fields[key] = params[key]
    for key in ("interval_minutes", "run_hour", "run_minute"):
        if params.get(key) is not None:
            fields[key] = _int(params[key])
    if fields:
        current = db.get_scheduled_task(task_id)
        schedule_keys = {
            "frequency",
            "interval_minutes",
            "run_at",
            "run_hour",
            "run_minute",
            "days_of_week",
            "day_of_month",
        }
        if schedule_keys.intersection(fields):
            merged = {**current, **fields, "next_run_at": None}
            fields["next_run_at"] = compute_next_run(merged)
        task = db.update_scheduled_task(task_id, **fields)
        _ok(f"定时任务已更新：{task['title']}", {"task": task})
    else:
        _ok("没有需要更新的字段", {"task": db.get_scheduled_task(task_id)})


def _set_status(params: dict, status: str) -> None:
    task_id = str(params.get("task_id") or "")
    if not task_id or db.get_scheduled_task(task_id) is None:
        _err("需要有效的 task_id")
        return
    task = db.update_scheduled_task(task_id, status=status)
    label = "已暂停" if status == "paused" else "已恢复"
    _ok(f"定时任务{label}：{task['title']}", {"task": task})


def main() -> None:
    data = json.load(sys.stdin)
    params = data.get("params") or {}
    action = str(params.get("action") or "list")
    try:
        if action == "create":
            _create(params)
        elif action == "update":
            _update(params)
        elif action == "pause":
            _set_status(params, "paused")
        elif action == "resume":
            _set_status(params, "active")
        elif action == "delete":
            task_id = str(params.get("task_id") or "")
            if not task_id or db.get_scheduled_task(task_id) is None:
                _err("删除定时任务需要有效的 task_id")
                return
            for event in db.list_calendar_events():
                if event.get("task_id") == task_id:
                    db.delete_calendar_event(event["id"])
            db.delete_scheduled_task(task_id)
            _ok("定时任务已删除", {"tasks": db.list_scheduled_tasks()})
        else:
            _ok("当前定时任务", {"tasks": db.list_scheduled_tasks()})
    except Exception as exc:  # noqa: BLE001
        _err(f"操作失败: {exc}")


if __name__ == "__main__":
    main()
