"""LangChain middleware that syncs todo state back to SQLite."""

from __future__ import annotations

from langchain.agents.middleware import AgentMiddleware

from ... import db
from ...sse import sse_event
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
        db.update_session(self.ctx.session_id, plan_mode="direct")
        raw_todos = (request.tool_call.get("args") or {}).get("todos") or []
        titles = [
            str(todo.get("content") or "").strip()
            for todo in raw_todos
            if str(todo.get("content") or "").strip()
        ]
        items = db.replace_todos(self.ctx.session_id, titles)
        request.runtime.stream_writer({"event": "plan", "items": items})
        return result
