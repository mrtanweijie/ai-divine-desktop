from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from .. import db, events
from ..schedule_utils import compute_next_run
from ..schemas import ScheduledTaskCreate, ScheduledTaskDecide, ScheduledTaskUpdate

router = APIRouter(prefix="/scheduled-tasks", tags=["scheduled-tasks"])
logger = logging.getLogger("divine.scheduled-tasks")


@router.get("")
def list_scheduled_tasks():
    return {"tasks": db.list_scheduled_tasks()}


# 需要真跑 Agent 的类型：它们必须有会话承载执行结果。
# reminder 只提醒、不跑 Agent，不需要会话。
_AGENT_TASK_TYPES = frozenset({"agent", "monitor", "webhook", "digest", "interactive"})


def _task_session_title(title: str) -> str:
    return f"定时任务 · {title.strip() or '未命名'}"


def _ensure_task_session(
    task_type: str, title: str, session_id: str | None
) -> tuple[str | None, bool]:
    """给需要跑 Agent 的任务准备会话。

    返回 ``(session_id, created)``。未指定会话时自动建一个**专属会话**，
    让定时任务跑出来的内容有地方可看；``reminder`` 不建。
    """
    if session_id:
        return session_id, False
    if task_type not in _AGENT_TASK_TYPES:
        return None, False
    # 归属项目取「列表第一个」（与前端侧栏顺序一致：pinned → sort_order → updated_at）。
    # 不用 default_project()——它取的是最早创建的项目，可能排在侧栏底部、用户看不到。
    project = db.first_project()
    session = db.create_session(
        title=_task_session_title(title),
        project_id=project["id"] if project else None,
    )
    return str(session["id"]), True


@router.post("", status_code=201)
def create_scheduled_task(body: ScheduledTaskCreate):
    if body.session_id and db.get_session(body.session_id) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    session_id, session_created = _ensure_task_session(
        body.task_type, body.title, body.session_id
    )
    schedule_values = body.model_dump(exclude_none=True)
    task = db.create_scheduled_task(
        title=body.title.strip(),
        description=body.description.strip(),
        session_id=session_id,
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
        prompt=body.prompt,
        model_id=body.model_id,
        allow_full_access=body.allow_full_access,
        delivery=body.delivery,
        interactive=body.interactive,
        digest=body.digest,
    )
    logger.info(
        "scheduled task created id=%s title=%s frequency=%s",
        task["id"],
        task["title"],
        task["frequency"],
    )
    if session_created:
        # 让前端侧栏立刻出现这个「任务专属会话」
        events.broadcast("sessions_changed", {"reason": "task_created"})
    return task


@router.patch("/{task_id}")
def update_scheduled_task(task_id: str, body: ScheduledTaskUpdate):
    current = db.get_scheduled_task(task_id)
    if not current:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    fields = body.model_dump(exclude_none=True)
    # 027 设计：把 schema 字段名映射到列名（update_scheduled_task 用 **fields，
    # 直接按列名匹配，schema 的 "delivery" / "interactive" 在此处转一下）。
    if "delivery" in fields:
        fields["delivery_json"] = fields.pop("delivery")
    if "interactive" in fields:
        fields["interactive_json"] = fields.pop("interactive")
    if "digest" in fields:
        fields["digest_json"] = fields.pop("digest")
    if "session_id" in fields and fields["session_id"]:
        if db.get_session(fields["session_id"]) is None:
            raise HTTPException(status_code=404, detail="会话不存在")
    # 任务改成需要跑 Agent 的类型（或原本就没有会话）时，补建专属会话
    session_created = False
    if not fields.get("session_id") and not current.get("session_id"):
        merged_type = fields.get("task_type") or current.get("task_type") or ""
        if merged_type in _AGENT_TASK_TYPES:
            fields["session_id"], session_created = _ensure_task_session(
                merged_type,
                fields.get("title") or current.get("title") or "",
                None,
            )
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
    if session_created:
        events.broadcast("sessions_changed", {"reason": "task_updated"})
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


@router.get("/{task_id}/runs")
def list_task_runs(task_id: str, limit: int = 5):
    """执行历史（design 027 §2.2）。

    只有 webhook / digest / interactive 会写 `task_runs`——reminder /
    agent / monitor 刻意不写（保持改前行为，历史从 `last_run_at` 推断）。
    """
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="limit 需在 1..100")
    task = db.get_scheduled_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    return {"runs": db.list_runs_for_task(task_id, limit=limit)}


@router.post("/{task_id}/decide")
def decide_scheduled_task(task_id: str, body: ScheduledTaskDecide):
    """交互任务的用户决策回包（design 027 §3.4）。

    只翻票据状态，真正的执行在 scheduler 那一侧——保持单一执行线程。
    """
    from ..agent.tasks.interactive import resolve_decision

    task = db.get_scheduled_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    if not resolve_decision(body.ticket, body.decision):
        raise HTTPException(status_code=409, detail="票据无效或已过期")
    logger.info(
        "scheduled task decided id=%s decision=%s",
        task_id,
        body.decision,
    )
    return {"ok": True, "decision": body.decision}
