from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from .. import db
from ..schedule_utils import compute_next_run
from ..schemas import ScheduledTaskCreate, ScheduledTaskUpdate

router = APIRouter(prefix="/scheduled-tasks", tags=["scheduled-tasks"])
logger = logging.getLogger("divine.scheduled-tasks")


@router.get("")
def list_scheduled_tasks():
    return {"tasks": db.list_scheduled_tasks()}


@router.post("", status_code=201)
def create_scheduled_task(body: ScheduledTaskCreate):
    if body.session_id and db.get_session(body.session_id) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    schedule_values = body.model_dump(exclude_none=True)
    task = db.create_scheduled_task(
        title=body.title.strip(),
        description=body.description.strip(),
        session_id=body.session_id,
        task_type=body.task_type,
        frequency=body.frequency,
        interval_minutes=body.interval_minutes,
        run_at=body.run_at,
        run_hour=body.run_hour,
        run_minute=body.run_minute,
        days_of_week=body.days_of_week,
        day_of_month=body.day_of_month,
        next_run_at=compute_next_run(schedule_values),
        status=body.status,
    )
    logger.info(
        "scheduled task created id=%s title=%s frequency=%s",
        task["id"],
        task["title"],
        task["frequency"],
    )
    return task


@router.patch("/{task_id}")
def update_scheduled_task(task_id: str, body: ScheduledTaskUpdate):
    current = db.get_scheduled_task(task_id)
    if not current:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    fields = body.model_dump(exclude_none=True)
    if "session_id" in fields and fields["session_id"]:
        if db.get_session(fields["session_id"]) is None:
            raise HTTPException(status_code=404, detail="会话不存在")
    reschedule_keys = {
        "frequency",
        "interval_minutes",
        "run_at",
        "run_hour",
        "run_minute",
        "days_of_week",
        "day_of_month",
    }
    if reschedule_keys.intersection(fields) and "next_run_at" not in fields:
        merged = {**current, **fields, "next_run_at": None}
        fields["next_run_at"] = compute_next_run(merged)
    updated = db.update_scheduled_task(task_id, **fields)
    logger.info(
        "scheduled task updated id=%s status=%s",
        task_id,
        updated.get("status"),
    )
    return updated


@router.delete("/{task_id}", status_code=204)
def delete_scheduled_task(task_id: str):
    task = db.get_scheduled_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    for event in db.list_calendar_events():
        if event.get("task_id") == task_id:
            db.delete_calendar_event(event["id"])
    db.delete_scheduled_task(task_id)
    logger.info("scheduled task deleted id=%s", task_id)
