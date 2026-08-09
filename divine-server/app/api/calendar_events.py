from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from .. import db
from ..schedule_utils import parse_dt
from ..schemas import CalendarEventCreate, CalendarEventUpdate

router = APIRouter(prefix="/calendar-events", tags=["calendar-events"])
logger = logging.getLogger("divine.calendar-events")


def _validate_window(start_at: str, end_at: str | None) -> None:
    start = parse_dt(start_at)
    if start is None:
        raise HTTPException(status_code=400, detail="开始时间格式不正确")
    if end_at:
        end = parse_dt(end_at)
        if end is None:
            raise HTTPException(status_code=400, detail="结束时间格式不正确")
        if end <= start:
            raise HTTPException(status_code=400, detail="结束时间必须晚于开始时间")


@router.get("")
def list_calendar_events():
    return {"events": db.list_calendar_events()}


@router.post("", status_code=201)
def create_calendar_event(body: CalendarEventCreate):
    _validate_window(body.start_at, body.end_at)
    if body.task_id and db.get_scheduled_task(body.task_id) is None:
        raise HTTPException(status_code=404, detail="关联的定时任务不存在")
    event = db.create_calendar_event(
        title=body.title.strip(),
        start_at=body.start_at,
        end_at=body.end_at,
        notes=body.notes.strip(),
        location=body.location.strip(),
        task_id=body.task_id,
    )
    logger.info(
        "calendar event created id=%s title=%s start=%s",
        event["id"],
        event["title"],
        event["start_at"],
    )
    return event


@router.patch("/{event_id}")
def update_calendar_event(event_id: str, body: CalendarEventUpdate):
    event = db.get_calendar_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="日程不存在")
    fields = body.model_dump(exclude_none=True)
    start_at = fields.get("start_at", event["start_at"])
    end_at = fields.get("end_at", event["end_at"])
    _validate_window(start_at, end_at)
    if "task_id" in fields and fields["task_id"]:
        if db.get_scheduled_task(fields["task_id"]) is None:
            raise HTTPException(status_code=404, detail="关联的定时任务不存在")
    updated = db.update_calendar_event(event_id, **fields)
    logger.info("calendar event updated id=%s", event_id)
    return updated


@router.delete("/{event_id}", status_code=204)
def delete_calendar_event(event_id: str):
    event = db.get_calendar_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="日程不存在")
    db.delete_calendar_event(event_id)
    logger.info("calendar event deleted id=%s", event_id)
