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
        tasks = await asyncio.to_thread(db.list_scheduled_tasks)
        for task in tasks:
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
            # 027 设计：分派到 app.agent.tasks 注册的 handler；
            # reminder / agent / monitor 走 builtins.py 默认实现，行为不变。
            from .agent import tasks as task_dispatcher

            ok = True
            error = ""
            try:
                await task_dispatcher.run_task(task)
            except Exception as exc:
                ok = False
                error = repr(exc)
                logger.exception(
                    "scheduled task handler failed task_id=%s",
                    task["id"],
                )
            # 跑完立刻通知前端（用户此时往往在做别的事）
            fresh = await asyncio.to_thread(db.get_scheduled_task, task["id"]) or task
            self._notify_finished(fresh, ok, error)
            try:
                await self._advance(task)
            except Exception:
                logger.exception(
                    "scheduled task bookkeeping failed task_id=%s",
                    task["id"],
                )

    def _notify_finished(
        self, task: dict[str, Any], ok: bool, error: str
    ) -> None:
        """广播「这个任务跑完了」，前端据此弹系统通知。

        ``reminder`` 跳过：它有自己的提醒通道（前端按 ``next_run_at`` 提前弹），
        再发一条就重复打扰了。其余类型（agent / monitor / webhook / digest /
        interactive）跑完时用户通常不在这个会话里，需要一条"跑完了"的提示。
        """
        if task.get("task_type") == "reminder":
            return
        from . import events

        events.broadcast(
            "task_finished",
            {
                "task_id": task["id"],
                "title": task.get("title") or "定时任务",
                "task_type": task.get("task_type"),
                "session_id": task.get("session_id"),
                "ok": ok,
                "error": error,
            },
        )

    def _mark_reminder_due(self, task: dict[str, Any]) -> None:
        logger.info(
            "reminder due task_id=%s title=%s",
            task["id"],
            task.get("title") or "定时任务提醒",
        )

    async def _advance(self, task: dict[str, Any]) -> None:
        """Update last run time and compute the next occurrence in SQLite."""
        now = _utc_now()
        if task.get("frequency") == "once":
            await asyncio.to_thread(
                db.update_scheduled_task,
                task["id"],
                status="done",
                last_run_at=now,
                next_run_at=None,
            )
            return
        merged = {**task, "next_run_at": None}
        await asyncio.to_thread(
            db.update_scheduled_task,
            task["id"],
            last_run_at=now,
            next_run_at=compute_next_run(merged),
        )

    async def _run_agent_task(self, task: dict[str, Any]) -> None:
        """Run one real Agent turn for scheduled agent/monitor tasks."""
        # 延迟导入：避免 scheduler ←→ agent.tasks 的模块级循环依赖
        from .agent.tasks.common import ensure_task_session, notify_session_messages

        session_id = await asyncio.to_thread(ensure_task_session, task)
        if not session_id:
            logger.warning(
                "scheduled task session unavailable task_id=%s", task["id"]
            )
            return
        session = await asyncio.to_thread(db.get_session, session_id)
        if session is None:
            return
        workspace = Path(
            await asyncio.to_thread(db.session_workspace, session_id)
            or workspace_dir()
        )
        previous_plan_mode = session.get("plan_mode") or "ask"
        await asyncio.to_thread(db.update_session, session_id, plan_mode="direct")
        try:
            await asyncio.to_thread(
                db.add_message,
                session_id,
                "user",
                task.get("description") or task.get("title") or "定时任务",
            )
            notify_session_messages(session_id)
            history = await asyncio.to_thread(
                db.history_for_model, session_id, limit=20
            )
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
            await asyncio.to_thread(
                db.update_session, session_id, plan_mode=previous_plan_mode
            )
            # 无论成功还是抛异常都再通知一次（run_agent 失败时用户也能看到 user 消息）
            notify_session_messages(session_id)


scheduler = Scheduler()
