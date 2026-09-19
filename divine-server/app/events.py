"""进程内事件广播（供 ``/api/events`` SSE 端点使用）。

对话回合内的 SSE 只在回合进行期间存在，覆盖不到**后台**发生的事（例如调度器
跑完一个定时任务、顺手建了专属会话）。这里做一个最小的进程内 pub/sub：
每个订阅者持一个 ``asyncio.Queue``，``broadcast`` 往里投递。

**线程安全**：调度器在事件循环里跑，但 FastAPI 的同步端点（如创建定时任务）
跑在 worker 线程里，两边都会调 ``broadcast``。``asyncio.Queue.put_nowait``
不是线程安全的，所以统一走 ``loop.call_soon_threadsafe``。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger("divine.events")

# 订阅者队列容量：满了丢最旧的，保证新事件总能进来（前端断线时不该拖垮后端）
_QUEUE_MAXSIZE = 100

_subscribers: set[asyncio.Queue[str]] = set()
_loop: asyncio.AbstractEventLoop | None = None


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    """应用启动时记下主事件循环，供跨线程投递使用。"""
    global _loop
    _loop = loop


def subscribe() -> asyncio.Queue[str]:
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
    _subscribers.add(queue)
    logger.debug("events subscriber added total=%d", len(_subscribers))
    return queue


def unsubscribe(queue: asyncio.Queue[str]) -> None:
    _subscribers.discard(queue)
    logger.debug("events subscriber removed total=%d", len(_subscribers))


def subscriber_count() -> int:
    return len(_subscribers)


def format_sse(event: str, data: dict[str, Any] | None = None) -> str:
    payload = json.dumps(data or {}, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _put(queue: asyncio.Queue[str], message: str) -> None:
    """在事件循环线程里真正入队；队列满则丢最旧的一条。"""
    try:
        queue.put_nowait(message)
        return
    except asyncio.QueueFull:
        pass
    try:
        queue.get_nowait()
        queue.put_nowait(message)
    except Exception:  # noqa: BLE001 — 单条事件丢失不值得影响任何流程
        logger.debug("event dropped (queue full)", exc_info=True)


def broadcast(event: str, data: dict[str, Any] | None = None) -> None:
    """向所有订阅者投递一条事件；无订阅者时是 no-op。

    可在任意线程调用。任何异常都在此吞掉——广播失败绝不能让业务逻辑挂掉。
    """
    if not _subscribers:
        return
    message = format_sse(event, data)
    loop = _loop
    for queue in list(_subscribers):
        try:
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(_put, queue, message)
            else:
                # 没有可用循环（测试或启动早期）：直接入队
                _put(queue, message)
        except Exception:  # noqa: BLE001
            logger.debug("broadcast failed event=%s", event, exc_info=True)
