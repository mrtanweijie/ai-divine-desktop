"""全局事件流（SSE）：``GET /api/events``。

与 ``/api/chat`` 的回合内流不同，这条连接**常驻**，用来把后台发生的事推给前端
（目前只有 ``sessions_changed``）。前端用 ``EventSource`` 连它。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from .. import events

router = APIRouter(prefix="/events", tags=["events"])
logger = logging.getLogger("divine.api.events")

# 心跳间隔：代理/系统可能掐掉长时间无数据的连接
HEARTBEAT_SECONDS = 15


@router.get("")
async def stream_events() -> StreamingResponse:
    async def generator() -> AsyncIterator[str]:
        # 订阅放在生成器内部：如果响应从未被迭代，就不该占用一个订阅者槽位。
        # （放在 handler 体里、unsubscribe 放在 finally 会出现"生成器没启动 →
        # finally 不执行 → 订阅者永久泄漏"。）
        queue = events.subscribe()
        try:
            # 先握手一条 ready，前端据此确认连接已建立（并触发一次首刷）
            yield events.format_sse("ready", {"subscribers": events.subscriber_count()})
            while True:
                try:
                    message = await asyncio.wait_for(
                        queue.get(), timeout=HEARTBEAT_SECONDS
                    )
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield message
        finally:
            events.unsubscribe(queue)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # 关掉 nginx 之类中间层的缓冲，否则事件会被攒着不发
            "X-Accel-Buffering": "no",
        },
    )
