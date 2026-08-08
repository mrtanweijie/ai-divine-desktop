from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from .. import db
from ..pdf_export import render_markdown_pdf
from ..schemas import SessionCreate, SessionUpdate

router = APIRouter(prefix="/sessions", tags=["sessions"])
logger = logging.getLogger("divine.sessions")


@router.get("")
def list_sessions():
    return {"sessions": db.list_sessions()}


@router.post("", status_code=201)
def create_session(body: SessionCreate):
    session = db.create_session(body.title)
    logger.info("session created id=%s title=%s", session["id"], body.title)
    return session


@router.get("/{session_id}")
def get_session(session_id: str):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return db.load_session(session_id)


@router.patch("/{session_id}")
def rename_session(session_id: str, body: SessionUpdate):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return db.update_session(session_id, title=body.title.strip() or "新对话")


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: str):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    db.delete_session(session_id)
    logger.info("session deleted id=%s", session_id)


@router.post("/{session_id}/clear")
def clear_session(session_id: str):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    db.clear_messages(session_id)
    logger.info("session cleared id=%s", session_id)
    return db.load_session(session_id)


@router.get("/{session_id}/export")
def export_session(session_id: str, format: str = "markdown"):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = db.list_messages(session_id)
    lines = [
        f"# {session['title']}",
        "",
        f"导出时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
    ]
    for message in messages:
        if message["role"] == "tool":
            continue
        if message["role"] == "assistant" and not message["content"]:
            parts = db.list_message_parts(message["id"])
            if any(part["type"] == "tool_calls" for part in parts):
                continue
        role = "用户" if message["role"] == "user" else "AI"
        lines.extend([f"## {role}", "", message["content"], ""])
    if format == "text":
        text = "\n".join(lines)
        return Response(
            text,
            media_type="text/plain",
            headers={"Content-Disposition": 'attachment; filename="chat.txt"'},
        )
    if format == "pdf":
        payload = render_markdown_pdf("\n".join(lines), session["title"])
        return Response(
            payload,
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="chat.pdf"'
            },
        )
    text = "\n".join(lines)
    return Response(
        text,
        media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="chat.md"'},
    )
