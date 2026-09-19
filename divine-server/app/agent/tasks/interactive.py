"""``interactive`` 任务类型（design 027 §3.4）：先问用户，确认才执行。

流程：

```
到点 → 建 ticket → 落库 pending_user_action（前端据此显示询问卡片）
     → 等用户决策（或超时）
        ├─ approve → 跑 Agent → succeeded
        ├─ reject  → skipped
        └─ 超时    → skipped
     → 清 pending_user_action
```

决策用进程内 ``asyncio.Event`` 传递（decide 路由 set 回来），
``pending_user_action`` 只是给前端发现「有活等着你」的可见标记。
已知限制：server 重启会丢票（进程内字典），遗留的 pending 标记由下次触发时重建。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from . import register
from .common import (
    RunRecorder,
    final_answer_from_history,
    run_agent_with_user_prompt,
)

logger = logging.getLogger("divine.tasks.interactive")

# ticket → 等待中的事件；decide 路由 set 回来
_DECISIONS: dict[str, asyncio.Event] = {}
# ticket → 用户的选择（"approve" / "reject"）
_DECISION_RESULT: dict[str, str] = {}


def resolve_decision(ticket: str, decision: str) -> bool:
    """decide 路由调用。返回票据是否有效（无效=已过期或已决策过）。"""
    event = _DECISIONS.get(ticket)
    if event is None:
        return False
    _DECISION_RESULT[ticket] = decision
    event.set()
    return True


def pending_ticket(task: dict[str, Any]) -> str | None:
    return task.get("pending_user_action") or None


@register("interactive")
async def run_interactive_task(task: dict[str, Any]) -> None:
    from ... import db

    recorder = RunRecorder(task["id"])
    recorder.start()
    cfg = task.get("interactive_json") or {}
    try:
        expire = int(cfg.get("expire_seconds") or 600)
    except (TypeError, ValueError):
        expire = 600
    expire = max(expire, 1)

    ticket = uuid.uuid4().hex
    event = asyncio.Event()
    _DECISIONS[ticket] = event
    # 落库：前端靠这个字段发现有任务在等人决策
    await asyncio.to_thread(
        db.update_scheduled_task, task["id"], pending_user_action=ticket
    )
    try:
        try:
            await asyncio.wait_for(event.wait(), expire)
        except asyncio.TimeoutError:
            recorder.skip("等待用户确认超时")
            return

        decision = _DECISION_RESULT.pop(ticket, "reject")
        if decision != "approve":
            recorder.skip("用户选择跳过")
            return

        history = await run_agent_with_user_prompt(task)
        recorder.set_output(final_answer_from_history(history))
        recorder.finish("succeeded")
    except Exception as e:  # noqa: BLE001 — handler 异常不能冒到调度器
        logger.exception("interactive task failed task_id=%s", task.get("id"))
        recorder.fail(repr(e))
    finally:
        _DECISIONS.pop(ticket, None)
        _DECISION_RESULT.pop(ticket, None)
        # 无论走哪条分支都清掉标记，避免前端一直显示陈旧卡片
        try:
            await asyncio.to_thread(
                db.update_scheduled_task, task["id"], pending_user_action=None
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "clear pending_user_action failed task_id=%s", task.get("id")
            )


__all__ = [
    "pending_ticket",
    "resolve_decision",
    "run_interactive_task",
]
