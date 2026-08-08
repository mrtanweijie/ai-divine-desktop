from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from .. import db
from ..agent import run_agent
from ..config import settings_store
from ..schemas import StreamChatRequest
from ..sse import error_event, sse_event

router = APIRouter(tags=["chat"])


@router.post("/stream_chat")
async def stream_chat(request: StreamChatRequest):
    question = request.question.strip()
    if not question:
        return StreamingResponse(
            iter([error_event("invalid_request", "问题不能为空")]),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    session_id = request.session_id
    if session_id:
        if db.get_session(session_id) is None:
            return StreamingResponse(
                iter([error_event("not_found", "会话不存在")]),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
    else:
        session_id = db.create_session()["id"]

    session = db.get_session(session_id)
    messages = db.list_messages(session_id)
    if not messages:
        title = question[:24] if len(question) > 24 else question
        db.update_session(session_id, title=title)
    db.add_message(session_id, "user", question)

    settings = settings_store.load()
    context_limit = int(settings.get("context_limit") or 20)
    history = db.history_for_model(session_id, limit=context_limit)

    async def generate():
        try:
            async for event in run_agent(session_id, history, request.think):
                yield event
        except Exception as exc:  # noqa: BLE001
            yield error_event("server_error", str(exc))
        finally:
            db.touch_session(session_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
