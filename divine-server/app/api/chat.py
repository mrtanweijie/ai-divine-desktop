from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from .. import db
from ..agent import run_agent
from ..config import settings_store
from ..document_reader import read_file_text
from ..file_types import is_image_path
from ..schemas import Attachment, StreamChatRequest
from ..sse import error_event, sse_event

router = APIRouter(tags=["chat"])
logger = logging.getLogger("divine.chat")


def _read_text_fallback(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    if not text.strip():
        return ""
    printable = sum(1 for ch in text if ch.isprintable() or ch in "\r\n\t")
    return text if printable / len(text) >= 0.9 else ""


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
    message = db.add_message(session_id, "user", question)
    for index, attachment in enumerate(request.attachments):
        meta: dict[str, str] = {"name": attachment.name}
        if attachment.file_path:
            meta["path"] = attachment.file_path
            if not is_image_path(attachment.file_path):
                try:
                    meta["content"] = read_file_text(
                        Path(attachment.file_path)
                    )[:12000]
                except Exception as exc:  # noqa: BLE001
                    meta["error"] = str(exc)
                    text = _read_text_fallback(Path(attachment.file_path))
                    if text:
                        meta["content"] = text[:12000]
        elif attachment.content:
            meta["content"] = attachment.content[:12000]
        db.add_message_part(
            message["id"],
            "file",
            json.dumps(meta, ensure_ascii=False),
            order=index,
        )

    settings = settings_store.load()
    context_limit = int(settings.get("context_limit") or 20)
    history = db.history_for_model(session_id, limit=context_limit)
    logger.info(
        "chat request session=%s question_len=%d attachments=%d think=%s history=%d",
        session_id,
        len(question),
        len(request.attachments),
        request.think,
        len(history),
    )

    async def generate():
        try:
            async for event in run_agent(session_id, history, request.think):
                yield event
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "stream_chat error session=%s: %s", session_id, exc
            )
            yield error_event("server_error", str(exc))
        finally:
            db.touch_session(session_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
