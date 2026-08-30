from __future__ import annotations

import logging
import re
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from .. import db
from ..localization import (
    default_session_title,
    export_labels,
    normalize_locale,
)
from ..pdf_export import render_markdown_pdf
from ..schemas import ChoiceStateUpdate, SessionCreate, SessionUpdate

router = APIRouter(prefix="/sessions", tags=["sessions"])
logger = logging.getLogger("divine.sessions")


def _export_filename(title: str, extension: str) -> str:
    safe_title = re.sub(r'[\\/:*?"<>|]+', "-", title).strip().strip(".")
    safe_title = safe_title or "chat"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{safe_title}_{timestamp}.{extension}"


def _download_disposition(filename: str, fallback: str) -> str:
    encoded = quote(filename, safe="")
    return f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{encoded}'


@router.get("")
def list_sessions(project_id: str | None = None):
    return {"sessions": db.list_sessions(project_id)}


@router.get("/search")
def search_sessions(q: str, project_id: str | None = None, limit: int = 20):
    """全文搜索会话标题和消息内容。"""
    return {"sessions": db.search_sessions(q, project_id, limit)}


@router.post("", status_code=201)
def create_session(body: SessionCreate):
    if body.project_id and db.get_project(body.project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    if body.approval_mode and body.approval_mode not in ("ask", "assist", "full"):
        raise HTTPException(status_code=400, detail="审批模式不支持")
    locale = normalize_locale(body.locale)
    session = db.create_session(
        body.title or default_session_title(locale),
        body.project_id,
        body.approval_mode,
        locale,
    )
    logger.info("session created id=%s title=%s", session["id"], body.title)
    return session


@router.get("/{session_id}")
def get_session(
    session_id: str,
    limit: int | None = None,
    before_id: str | None = None,
):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if limit is not None:
        return db.load_session_page(session_id, before_id, limit)
    return db.load_session(session_id)


@router.patch("/{session_id}")
def rename_session(session_id: str, body: SessionUpdate):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    updates: dict[str, str] = {}
    if body.title is not None:
        updates["title"] = (
            body.title.strip()
            or default_session_title(session.get("locale") or "zh-CN")
        )
    if body.approval_mode is not None:
        if body.approval_mode not in ("ask", "assist", "full"):
            raise HTTPException(status_code=400, detail="审批模式不支持")
        updates["approval_mode"] = body.approval_mode
    if not updates:
        return session
    return db.update_session(session_id, **updates)


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: str):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    db.pause_tasks_for_session(session_id)
    db.delete_session(session_id)
    logger.info("session deleted id=%s", session_id)


@router.post("/messages/{message_id}/choice_state")
def update_message_choice_state(message_id: str, payload: ChoiceStateUpdate):
    """保存选项卡片的已选状态（选择后置灰，刷新/重开会话后保持）。"""
    message = db.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")
    state = db.update_choice_state(message_id, payload.state or {})
    logger.info("choice_state updated message=%s", message_id)
    return {"message": state}


@router.post("/{session_id}/clear")
def clear_session(session_id: str):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    db.clear_messages(session_id)
    # 决策 4：预整理原文附件随会话清空删除。
    # 路径必须与 preprocess.py 落盘位置一致：
    # workspace/sessions/{session_id}/attachments/
    try:
        import shutil
        from pathlib import Path

        from ..config import workspace_dir

        ws = Path(db.session_workspace(session_id) or workspace_dir())
        att_dir = ws / "sessions" / session_id / "attachments"
        if att_dir.is_dir():
            shutil.rmtree(att_dir, ignore_errors=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("会话附件清理失败: %s", exc)
    logger.info("session cleared id=%s", session_id)
    return db.load_session(session_id)


@router.get("/{session_id}/context-usage")
def session_context_usage(session_id: str):
    """Token usage breakdown for the context ring in the composer."""
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    from ..agent.state import build_context_breakdown

    return build_context_breakdown(session_id)


@router.post("/{session_id}/compact")
async def compact_session(session_id: str):
    """Manually compact the session's early conversation into a summary."""
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    from ..agent.state import compact_session as run_compact

    saved = await run_compact(session_id)
    if saved is None:
        from ..agent.state import build_context_breakdown

        return {
            "ok": True,
            "compacted": False,
            "message": "会话内容还不多，暂无需压缩",
            "usage": build_context_breakdown(session_id),
        }
    logger.info(
        "session manually compacted id=%s saved_tokens=%s",
        session_id,
        saved.get("saved_tokens", 0),
    )
    from ..agent.state import build_context_breakdown

    return {
        "ok": True,
        "compacted": True,
        "summary": saved.get("summary", ""),
        "savedTokens": int(saved.get("saved_tokens") or 0),
        "usage": build_context_breakdown(session_id),
    }


@router.get("/{session_id}/export")
def export_session(
    session_id: str, format: str = "markdown", locale: str = "zh-CN"
):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    labels = export_labels(locale)
    messages = db.list_messages(session_id)
    lines = [
        f"# {session['title']}",
        "",
        f"{labels['exported_at']}：{datetime.now().isoformat(timespec='seconds')}",
        "",
    ]
    for message in messages:
        if message["role"] == "tool":
            continue
        if message["role"] == "assistant" and not message["content"]:
            parts = db.list_message_parts(message["id"])
            if any(part["type"] == "tool_calls" for part in parts):
                continue
        role = labels["user"] if message["role"] == "user" else labels["ai"]
        lines.extend([f"## {role}", "", message["content"], ""])
    if format == "text":
        text = "\n".join(lines)
        return Response(
            text,
            media_type="text/plain",
            headers={
                "Content-Disposition": _download_disposition(
                    _export_filename(session["title"], "txt"), "chat.txt"
                )
            },
        )
    if format == "pdf":
        payload = render_markdown_pdf(
            "\n".join(lines), labels["title"]
        )
        return Response(
            payload,
            media_type="application/pdf",
            headers={
                "Content-Disposition": _download_disposition(
                    _export_filename(session["title"], "pdf"), "chat.pdf"
                )
            },
        )
    text = "\n".join(lines)
    return Response(
        text,
        media_type="text/markdown",
        headers={
            "Content-Disposition": _download_disposition(
                _export_filename(session["title"], "md"), "chat.md"
            )
        },
    )
