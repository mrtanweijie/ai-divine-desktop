"""内置 handler：把 reminder / agent / monitor 的执行语义原样迁过来。

design 027 stage 1 只迁移路径，不动行为。新加 handler（webhook / digest /
interactive）在 stage 2+ 单独写文件、调这里共用的 ``Scheduler._run_agent_task``
或者 stage 2 抽取的 ``_run_agent_with_user_prompt``。
"""

from __future__ import annotations

import logging
from typing import Any

from . import register

logger = logging.getLogger("divine.tasks.builtins")


@register("reminder")
async def _run_reminder(task: dict[str, Any]) -> None:
    """reminder 仅做账：与改前 ``Scheduler._mark_reminder_due`` 一致。"""
    logger.info(
        "reminder due task_id=%s title=%s",
        task["id"],
        task.get("title") or "定时任务提醒",
    )


@register("agent")
@register("monitor")
async def _run_agent(task: dict[str, Any]) -> None:
    """agent / monitor 共用一个执行入口（与改前完全一致）。"""
    from ... import scheduler as scheduler_module

    await scheduler_module.scheduler._run_agent_task(task)