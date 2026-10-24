from __future__ import annotations

import asyncio
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
from ..docgen.pdf.export import render_markdown_pdf
from ..schemas import (
    ChoiceStateUpdate,
    SessionCreate,
    SessionUpdate,
    UiSurfaceStateUpdate,
)

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
    # 面板编辑态没有外键（surface_id 是主键，不指向 messages），
    # 必须与会话一起显式清理，否则会残留成孤儿数据。
    db.clear_session_ui_surface_states(session_id)
    db.delete_session(session_id)
    # 会话结束即回收浏览器专属 tab（031 §4 tab 管理）：
    # 同步路由里只做标记，实际关闭在事件循环的 drain_pending 里执行
    try:
        from ..tools.browser_engine.session import manager

        manager.request_close(session_id)
    except Exception:  # noqa: BLE001 — 回收失败不影响会话删除
        pass
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


@router.post("/{session_id}/ui-surface-state")
def update_ui_surface_state(session_id: str, payload: UiSurfaceStateUpdate):
    """保存 A2UI 面板的编辑态（用户改了但还没提交的值），抗刷新。

    design 028 §5.5 ②。前端是**防抖写**（400ms），失败不阻塞交互 ——
    所以这里只做最朴素的覆盖写，不做任何业务校验（面板已经在渲染期
    校验过了，这里存的是用户输入值）。

    **为什么按会话而不是按消息**：`ui_surface_states` 的主键是
    `surface_id`（§5.5 的 B 方案），会话只是它的归属范围。而消息 id 在
    流式期间还是前端乐观 id（`local-assistant-*`），拿它当写入口会让
    "面板刚出现、回合还没结束时的编辑"直接 404；`done` 恢复后 id 换成
    服务端 id，同一块面板又会换一个 key。按会话写就绕开了这层漂移。
    写入的 `message_id` 只作回放定位用的元信息，**不参与校验**。
    """
    if db.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    db.save_ui_surface_state(
        payload.surface_id,
        payload.data or {},
        message_id=payload.message_id or "",
        session_id=session_id,
    )
    return {"ok": True}


@router.get("/{session_id}/ui-surface-states")
def list_ui_surface_states(session_id: str):
    """取该会话下全部面板编辑态（前端加载历史后一次性恢复）。

    design 028 §5.5 ② 的读取端。按会话一次性返回，而不是每个面板一次请求 ——
    长会话里几十块面板逐个拉会把恢复变成几十次往返。
    """
    if db.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"states": db.list_session_ui_surface_states(session_id)}


@router.post("/{session_id}/clear")
def clear_session(session_id: str):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    db.clear_messages(session_id)
    # A2UI 面板编辑态一并清空（消息没了，编辑态就失去宿主）。
    db.clear_session_ui_surface_states(session_id)
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
    # 本文件只有这一个 async 路由（其余是同步 def，FastAPI 会自动放进
    # 线程池，不需要也不应该改成 async）。所以只有这里要显式卸载。
    session = await asyncio.to_thread(db.get_session, session_id)
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
            # CPU 型（全量 token 估算），搬进线程池后不占事件循环
            "usage": await asyncio.to_thread(
                build_context_breakdown, session_id
            ),
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
        # CPU 型（全量 token 估算），搬进线程池后不占事件循环
        "usage": await asyncio.to_thread(build_context_breakdown, session_id),
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
