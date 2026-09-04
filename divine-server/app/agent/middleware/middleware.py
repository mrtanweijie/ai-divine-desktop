"""LangChain middleware that syncs todo state back to SQLite."""

from __future__ import annotations

import asyncio
from typing import Any

from langchain.agents.middleware import AgentMiddleware

from ... import db
from ..core import AgentRunContext

class TodoSyncMiddleware(AgentMiddleware):
    """Persist LangGraph todo state back to SQLite and emit plan SSE events."""

    def __init__(self, ctx: AgentRunContext) -> None:
        super().__init__()
        self.ctx = ctx

    async def awrap_tool_call(
        self, request: Any, handler: Any
    ) -> Any:
        result = await handler(request)
        if request.tool_call.get("name") != "write_todos":
            return result
        self.ctx.plan_first_pending = False
        await asyncio.to_thread(
            db.update_session, self.ctx.session_id, plan_mode="direct"
        )
        raw_todos = (request.tool_call.get("args") or {}).get("todos") or []
        titles = [
            str(todo.get("content") or "").strip()
            for todo in raw_todos
            if str(todo.get("content") or "").strip()
        ]
        items = await asyncio.to_thread(db.replace_todos, self.ctx.session_id, titles)
        request.runtime.stream_writer({"event": "plan", "items": items})
        return result


class TurnCounterMiddleware(AgentMiddleware):
    """Count model turns per run so tool events can carry a turn index.

    ReAct 的每一轮 = 一次模型调用 + 其触发的工具调用。tool SSE 事件带上
    turn 后，前端可把工具调用按轮次分组、画出执行轨迹。
    """

    def __init__(self, ctx: AgentRunContext) -> None:
        super().__init__()
        self.ctx = ctx

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        self.ctx.turn_index += 1
        return await handler(request)
