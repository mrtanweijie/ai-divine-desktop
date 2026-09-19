"""定时任务执行分发器（design 027）。

每个 ``task_type`` 由一个 async handler 负责；新加任务类型 = 新建 handler
文件 + ``@register('xxx')`` 装饰器一行。
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger("divine.tasks")

Handler = Callable[[dict[str, Any]], Awaitable[None]]

HANDLERS: dict[str, Handler] = {}


def register(task_type: str) -> Callable[[Handler], Handler]:
    """注册 handler。后注册覆盖先注册（方便补丁场景）。"""

    def _deco(fn: Handler) -> Handler:
        if task_type in HANDLERS:
            logger.warning(
                "task handler override task_type=%s prev=%s new=%s",
                task_type,
                HANDLERS[task_type].__name__,
                fn.__name__,
            )
        HANDLERS[task_type] = fn
        return fn

    return _deco


async def run_task(task: dict[str, Any]) -> None:
    """调度器唯一入口：找 handler 执行。"""
    handler = HANDLERS.get(task.get("task_type"))
    if handler is None:
        logger.warning(
            "unknown task_type=%s task_id=%s",
            task.get("task_type"),
            task.get("id"),
        )
        return
    await handler(task)


# 副作用导入：让各 handler 自动注册到 HANDLERS
from . import builtins  # noqa: E402, F401
from . import webhook  # noqa: E402, F401
from . import digest  # noqa: E402, F401
from . import interactive  # noqa: E402, F401
from .channels import register_builtin_channels  # noqa: E402

register_builtin_channels()