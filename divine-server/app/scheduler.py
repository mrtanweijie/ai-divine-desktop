"""Background scheduler for due scheduled tasks."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import db
from .config import workspace_dir
from .schedule_utils import compute_next_run

logger = logging.getLogger("divine.scheduler")

POLL_INTERVAL_SECONDS = 10


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Scheduler:
    """Background loop that advances due scheduled tasks.

    Reminder tasks only get bookkeeping updated here; the desktop frontend
    polls the updated last_run_at and shows the actual notification.
    Agent/monitor tasks run a real Agent turn when they have a session_id.
    """

    def __init__(self) -> None:
        self._loop_task: asyncio.Task[Any] | None = None
        self._run_tasks: dict[str, asyncio.Task[Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def start(self) -> None:
        if self._loop_task is not None:
            return
        self._loop_task = asyncio.create_task(self._poll())
        logger.info("scheduler started interval=%ss", POLL_INTERVAL_SECONDS)

    async def stop(self) -> None:
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None
        for run in list(self._run_tasks.values()):
            run.cancel()
        if self._run_tasks:
            await asyncio.gather(
                *self._run_tasks.values(), return_exceptions=True
            )
        self._run_tasks.clear()

    async def _poll(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("scheduler tick failed")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def _tick(self) -> None:
        now = _utc_now()
        for task in db.list_scheduled_tasks():
            if task.get("status") != "active":
                continue
            next_run = task.get("next_run_at")
            if not next_run or next_run > now:
                continue
            lock = self._locks.setdefault(task["id"], asyncio.Lock())
            if lock.locked():
                continue
            run = asyncio.create_task(self._run_due(task, lock))
            self._run_tasks[task["id"]] = run
            run.add_done_callback(
                lambda _done, task_id=task["id"]: self._run_tasks.pop(
                    task_id, None
                )
            )

    async def _run_due(
        self, task: dict[str, Any], lock: asyncio.Lock
    ) -> None:
        async with lock:
            try:
                if task.get("task_type") in ("agent", "monitor"):
                    await self._run_agent_task(task)
                elif task.get("task_type") == "reminder":
                    self._mark_reminder_due(task)
            except Exception:
                logger.exception(
                    "scheduled agent task failed task_id=%s", task["id"]
                )
            try:
                self._advance(task)
            except Exception:
                logger.exception(
                    "scheduled task bookkeeping failed task_id=%s",
                    task["id"],
                )

    def _mark_reminder_due(self, task: dict[str, Any]) -> None:
        logger.info(
            "reminder due task_id=%s title=%s",
            task["id"],
            task.get("title") or "定时任务提醒",
        )

    def _advance(self, task: dict[str, Any]) -> None:
        """Update last run time and compute the next occurrence in SQLite."""
        now = _utc_now()
        if task.get("frequency") == "once":
            db.update_scheduled_task(
                task["id"],
                status="done",
                last_run_at=now,
                next_run_at=None,
            )
            return
        merged = {**task, "next_run_at": None}
        db.update_scheduled_task(
            task["id"],
            last_run_at=now,
            next_run_at=compute_next_run(merged),
        )

    async def _run_agent_task(self, task: dict[str, Any]) -> None:
        """Run one real Agent turn for scheduled agent/monitor tasks."""
        session_id = task.get("session_id")
        if not session_id:
            logger.warning(
                "scheduled task has no session_id task_id=%s", task["id"]
            )
            return
        session = db.get_session(session_id)
        if session is None:
            return
        workspace = Path(
            db.session_workspace(session_id) or workspace_dir()
        )
        previous_plan_mode = session.get("plan_mode") or "ask"
        db.update_session(session_id, plan_mode="direct")
        try:
            db.add_message(
                session_id,
                "user",
                task.get("description") or task.get("title") or "定时任务",
            )
            history = db.history_for_model(session_id, limit=20)
            from .agent import run_agent

            async for _event in run_agent(
                session_id,
                history,
                think=False,
                workspace=workspace,
                approval_mode="full",
                locale=session.get("locale") or "zh-CN",
            ):
                pass
        finally:
            db.update_session(session_id, plan_mode=previous_plan_mode)


scheduler = Scheduler()
