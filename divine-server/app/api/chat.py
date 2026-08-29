from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from .. import db
from ..agent import run_agent
from ..config import settings_store
from ..document_reader import read_file_text
from ..file_types import is_image_path
from ..localization import default_session_title, normalize_locale
from ..schemas import Attachment, StreamChatRequest
from ..sse import error_event, sse_event

router = APIRouter(tags=["chat"])
logger = logging.getLogger("divine.chat")
# Session-id -> cancel event, used by POST /sessions/{id}/cancel to stop a stream.
_CANCEL_EVENTS: dict[str, asyncio.Event] = {}


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


def _extract_file_url_attachments(
    text: str,
) -> tuple[str, list[Attachment]]:
    """把消息文本里的 file:// URL 解码为本地路径附件。

    用户从地址栏/文本里粘贴的 file:// 链接（如
    file:///Users/.../xxx.html，含 percent 编码）若原样发给模型，会变成
    一串怪字符串导致工具调用异常（空工具名 / is not a valid tool）。
    这里在发送时自动提取：解码 → 校验文件存在 → 转为附件
    （走 approved_paths，agent 可直接 read_file），并从文本剔除 URL。

    返回 (清理后的文本, 附件列表)。文件不存在的 URL 保留原文（让模型
    告诉用户路径不存在）。
    """
    import re
    from urllib.parse import unquote

    found = re.findall(r"file://[^\s<>\"'`]+", text)
    if not found:
        return text, []
    cleaned = text
    attachments: list[Attachment] = []
    for url in dict.fromkeys(found):
        path = unquote(url[len("file://"):])
        # Windows file:///C:/... -> C:/...
        if path.startswith("/") and re.match(r"^/[A-Za-z]:", path):
            path = path[1:]
        p = Path(path)
        if not p.is_file():
            continue
        try:
            size = p.stat().st_size
        except OSError:
            size = None
        attachments.append(
            Attachment(name=p.name, file_path=str(p), size=size)
        )
        cleaned = cleaned.replace(url, "")
    return cleaned.strip(), attachments


@router.post("/stream_chat")
async def stream_chat(request: StreamChatRequest):
    question = request.question.strip()
    # 自动提取消息里的 file:// URL 为附件：模型直接读 percent 编码的怪字符串
    # 会工具调用异常（空工具名 / is not a valid tool），转成附件后可正常读取
    try:
        question, file_url_attachments = _extract_file_url_attachments(
            question
        )
        if file_url_attachments:
            request.attachments.extend(file_url_attachments)
            logger.info(
                "提取 file:// 附件 %d 个: %s",
                len(file_url_attachments),
                [a.file_path for a in file_url_attachments],
            )
    except Exception as exc:  # noqa: BLE001 — 提取失败不影响对话
        logger.warning("file:// 附件提取失败: %s", exc)
    locale = normalize_locale(request.locale)
    if request.session_id:
        existing_session = db.get_session(request.session_id)
        if existing_session is not None:
            locale = normalize_locale(
                request.locale or existing_session.get("locale")
            )
    if not question and not request.attachments:
        return StreamingResponse(
            iter(
                [
                    error_event(
                        "invalid_request",
                        "问题不能为空",
                        message_key="tool.questionEmpty",
                    )
                ]
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    if not question:
        question = {
            "zh-CN": "请分析附件",
            "zh-TW": "請分析附件",
            "en": "Analyze the attachment",
        }.get(locale, "请分析附件")

    session_id = request.session_id
    if session_id:
        if db.get_session(session_id) is None:
            return StreamingResponse(
                iter(
                    [
                        error_event(
                            "not_found",
                            "会话不存在",
                            message_key="tool.sessionNotFound",
                        )
                    ]
                ),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        if request.locale:
            db.update_session(session_id, locale=locale)
    else:
        if request.project_id and db.get_project(request.project_id) is None:
            return StreamingResponse(
                iter(
                    [
                        error_event(
                            "not_found",
                            "项目不存在",
                            message_key="tool.projectNotFound",
                        )
                    ]
                ),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        session_id = db.create_session(
            title=default_session_title(locale),
            project_id=request.project_id,
            approval_mode=request.approval_mode,
            locale=locale,
        )["id"]

    session = db.get_session(session_id)
    approval_mode = (
        request.approval_mode
        or session.get("approval_mode")
        or "ask"
    )
    workspace = Path(db.session_workspace(session_id) or workspace_dir())
    # 本地预整理：长文本先由本地模型整理成结构化版本，原文转存附件
    # （见 docs/preprocess-feature-design.md；失败/不可用一律原样上云）
    final_question = question
    original_attachment: Path | None = None
    organized = False
    attempted_question = False
    try:
        from ..agent.preprocess import maybe_preprocess

        final_question, original_attachment, organized, attempted_question = (
            await asyncio.to_thread(
                maybe_preprocess, question, session_id, workspace
            )
        )
    except Exception as exc:  # noqa: BLE001 — 预整理失败绝不影响对话
        logger.warning("本地预整理异常，原样上云: %s", exc)
    messages = db.list_messages(session_id)
    if not messages:
        title = question[:24] if len(question) > 24 else question
        db.update_session(session_id, title=title)
    message = db.add_message(session_id, "user", final_question)
    if organized and original_attachment is not None:
        try:
            # file 附件：只带路径，不注入原文内容（决策 3，省 token）。
            # preprocess_original 标记供前端过滤——UI 用 preprocess 部件展示
            # 可展开原文，这里只服务模型（history_for_model 读 path 引用）。
            db.add_message_part(
                message["id"],
                "file",
                json.dumps(
                    {
                        "name": "原文附件",
                        "path": str(original_attachment),
                        "size": original_attachment.stat().st_size,
                        "preprocess_original": True,
                    },
                    ensure_ascii=False,
                ),
                order=0,
            )
            # preprocess 标记：前端渲染「已整理」徽标 + 可展开原文。
            # history_for_model 只处理 type == "file" 的附件，不占模型上下文。
            try:
                original_text = original_attachment.read_text(
                    encoding="utf-8", errors="replace"
                )[:12000]
            except OSError:
                original_text = ""
            db.add_message_part(
                message["id"],
                "preprocess",
                json.dumps(
                    {
                        "organized": True,
                        "original_path": str(original_attachment),
                        "original": original_text,
                    },
                    ensure_ascii=False,
                ),
                order=1,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("预整理附件元信息写入失败: %s", exc)
    # 附件通道的预整理原文路径（无 file_path 的 content 附件会新写 original-*.md）
    preprocess_originals: list[str] = []
    attachment_attempted_fail = False
    for index, attachment in enumerate(request.attachments):
        meta: dict[str, object] = {
            "name": attachment.name,
            "size": attachment.size,
        }
        if attachment.file_path:
            meta["path"] = attachment.file_path
            if not attachment.size:
                try:
                    meta["size"] = Path(attachment.file_path).stat().st_size
                except OSError:
                    meta["size"] = None
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
        # 本地预整理：大文本附件（粘贴的 paste-*.txt 等）先本地整理再上云，
        # 上下文里换成整理版（省 token），原文仍是附件自身（云端可 read_file）。
        # 显式："帮我整理" + 附件（附件即指代对象）；自动：内容超阈值且非代码/表格。
        if isinstance(meta.get("content"), str) and meta["content"]:
            try:
                from ..agent.preprocess import maybe_preprocess_attachment

                original_text = meta["content"]
                att_original_path = (
                    str(Path(attachment.file_path))
                    if attachment.file_path
                    else None
                )
                new_content, att_orig, att_organized, att_attempted = (
                    await asyncio.to_thread(
                        maybe_preprocess_attachment,
                        question,
                        original_text,
                        session_id,
                        workspace,
                        att_original_path,
                    )
                )
                if att_attempted and not att_organized:
                    attachment_attempted_fail = True
                if att_organized and new_content:
                    meta["content"] = new_content
                    if att_orig:
                        preprocess_originals.append(att_orig)
                    db.add_message_part(
                        message["id"],
                        "preprocess",
                        json.dumps(
                            {
                                "organized": True,
                                "original_path": att_orig,
                                "original": original_text,
                            },
                            ensure_ascii=False,
                        ),
                        order=100 + index,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("附件预整理异常，按原样处理: %s", exc)
        db.add_message_part(
            message["id"],
            "file",
            json.dumps(meta, ensure_ascii=False),
            order=index,
        )

    settings = settings_store.load()
    context_limit = int(settings.get("context_limit") or 20)
    history = db.history_for_model(session_id, limit=context_limit)
    # Files the user selected or pasted as attachments are pre-approved: the
    # agent may read them without the external-file confirmation.
    approved_paths = [
        attachment.file_path
        for attachment in request.attachments
        if attachment.file_path
    ]
    if original_attachment is not None:
        approved_paths.append(str(original_attachment))
    approved_paths.extend(preprocess_originals)
    # 本地整理被触发但失败 → 询问用户是否仍走云端（避免静默烧 token）
    preprocess_attempted_fail = (
        attempted_question and not organized
    ) or attachment_attempted_fail
    logger.info(
        "chat request session=%s question_len=%d attachments=%d think=%s "
        "effort=%s history=%d model_id=%s tool_mode=%s",
        session_id,
        len(question),
        len(request.attachments),
        request.think,
        request.reasoning_effort,
        len(history),
        request.model_id,
        request.tool_mode,
    )

    async def generate():
        # Register a per-session cancel event so the UI can stop this stream.
        cancel_event = asyncio.Event()
        _CANCEL_EVENTS[session_id] = cancel_event
        try:
            # 本地模型：不走 agent（系统提示词 + 工具 schema 超过 0.5B 的
            # 上下文），直接与 llama-server 对话
            from ..agent.llm import _resolve_model_entry

            entry = _resolve_model_entry(settings, request.model_id)
            if entry.get("provider") == "local":
                async for event in stream_local_chat(
                    session_id, final_question, history, locale
                ):
                    yield event
                return

            # 本地整理被触发但失败 → 询问用户是否走云端（复用终端审批机制：
            # create_terminal_decision + POST /api/terminal/decide，前端零改动提交）
            if preprocess_attempted_fail:
                from ..api.terminal import (
                    create_terminal_decision,
                    remove_terminal_decision,
                )

                pending = create_terminal_decision(session_id)
                try:
                    yield sse_event(
                        "tool",
                        {
                            "tool": "preprocess_fallback",
                            "status": "confirm",
                            "message": "长文本本地整理失败，直接交给云端将消耗较多 token。是否继续？",
                            "messageKey": "tool.preprocessFallbackText",
                            "messageParams": {},
                            "confirm_type": "preprocess_fallback",
                            "call_id": "preprocess_confirm",
                            "session_id": session_id,
                        },
                    )
                    try:
                        await asyncio.wait_for(pending["event"].wait(), 180)
                        allowed = bool(pending["allowed"])
                    except asyncio.TimeoutError:
                        allowed = False
                finally:
                    remove_terminal_decision(session_id)
                if not allowed:
                    logger.info(
                        "预整理失败用户取消走云端 session=%s", session_id
                    )
                    # 同 call_id 的后续事件：确认卡 → 已取消（upsertTool 按 call_id 替换）
                    yield sse_event(
                        "tool",
                        {
                            "tool": "preprocess_fallback",
                            "status": "error",
                            "message": "已取消",
                            "messageKey": "tool.preprocessCancelled",
                            "messageParams": {},
                            "confirm_type": "preprocess_fallback",
                            "call_id": "preprocess_confirm",
                            "session_id": session_id,
                        },
                    )
                    cancel_text = (
                        "已取消：本地整理失败，本次未调用云端。"
                        "你可以重试，或直接发送原文让云端处理。"
                    )
                    # 持久化（与本地动作回复同款双写：db + SSE），刷新后仍可见
                    await asyncio.to_thread(
                        db.add_message, session_id, "assistant", cancel_text
                    )
                    yield sse_event("message", {"content": cancel_text})
                    yield sse_event(
                        "done",
                        {
                            "message": "已取消",
                            "messageKey": "tool.preprocessCancelled",
                            "messageParams": {},
                            "content": cancel_text,
                        },
                    )
                    return

                # 用户确认走云端：确认卡 → 处理中（同 call_id 替换）
                yield sse_event(
                    "tool",
                    {
                        "tool": "preprocess_fallback",
                        "status": "running",
                        "message": "已确认，继续处理",
                        "messageKey": "tool.preprocessConfirmed",
                        "messageParams": {},
                        "confirm_type": "preprocess_fallback",
                        "call_id": "preprocess_confirm",
                        "session_id": session_id,
                    },
                )

            async for event in run_agent(
                session_id,
                history,
                request.think,
                workspace=workspace,
                approval_mode=approval_mode,
                locale=locale,
                effort=request.reasoning_effort,
                context_limit=context_limit,
                cancel_event=cancel_event,
                model_id=request.model_id,
                approved_paths=approved_paths,
                tool_mode=request.tool_mode,
            ):
                yield event
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "stream_chat error session=%s: %s", session_id, exc
            )
            yield error_event("server_error", str(exc))
        finally:
            _CANCEL_EVENTS.pop(session_id, None)
            db.touch_session(session_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/sessions/{session_id}/cancel")
async def cancel_session(session_id: str) -> dict[str, object]:
    cancel_event = _CANCEL_EVENTS.get(session_id)
    if cancel_event is None:
        return {"ok": False, "message": "没有正在运行的会话"}
    cancel_event.set()
    return {"ok": True}


def _build_local_chat_messages(
    question: str,
    history: list[dict[str, Any]],
    locale: str | None,
    ctx_size: int = 4096,
) -> list[dict[str, str]]:
    """组装本地模型对话的 messages，按上下文预算裁剪历史。

    修复：history[-12:] 每条 2000 字符全塞会轻松超 4096 ctx，
    llama.cpp 返回 400 exceed_context_size_error。这里用 estimate_tokens
    从新到旧挑选历史，预算 = ctx - 系统提示 - 输出预留（1100 token）。
    """
    from ..agent.compact import estimate_tokens

    lang = "中文" if str(locale or "").startswith("zh") else "English"
    system_prompt = f"你是一个乐于助人的 AI 助手，请用{lang}简洁、准确地回答。"
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt}
    ]

    budget = ctx_size - estimate_tokens(system_prompt) - 1100
    if budget < 256:
        budget = 256

    question = str(question or "").strip()
    history_trim = history[-12:]
    # 最后一条可能是刚保存的当前问题（chat.py 预先 add_message），跳过避免重复
    if history_trim and (
        str(history_trim[-1].get("content") or "").strip() == question
    ):
        history_trim = history_trim[:-1]

    # 从新到旧挑选历史，直到预算不足（至少留 256 token 给当前问题）
    picked: list[dict[str, str]] = []
    for message in reversed(history_trim):
        role = message.get("role")
        content = str(message.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        content = content[:2000]
        tokens = estimate_tokens(content)
        if budget - tokens < 256:
            break
        budget -= tokens
        picked.append({"role": role, "content": content})
    messages.extend(reversed(picked))

    # 当前问题必放；极端超预算时按比例截断
    q_tokens = estimate_tokens(question)
    if budget < q_tokens and question:
        cut = max(int(len(question) * budget / max(q_tokens, 1)) - 32, 64)
        question = question[:cut]
    messages.append({"role": "user", "content": question})
    return messages


async def stream_local_chat(
    session_id: str,
    question: str,
    history: list[dict[str, Any]],
    locale: str | None,
) -> AsyncIterator[str]:
    """与本地模型直接对话：把最近会话发给 llama-server 流式回答。

    不走 agent（系统提示词 + 工具 schema 远超 0.5B 模型上下文），
    用精简系统提示词直连 llama.cpp 的 OpenAI 兼容接口。
    """
    from ..agent.local_llm import get_manager

    manager = get_manager()
    if not manager.is_ready():
        yield error_event(
            "local_model_not_running",
            "本地模型未运行，请先在设置-意图中启动",
        )
        return

    lang = "中文" if str(locale or "").startswith("zh") else "English"
    from ..config import settings_store

    ctx_size = int(settings_store.load().get("local_llm_ctx_size") or 4096)
    messages = _build_local_chat_messages(
        question, history, locale, ctx_size
    )

    payload = {
        "model": "local",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1024,
        "stream": True,
    }
    parts: list[str] = []
    try:
        import httpx

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(120, connect=5)
        ) as client:
            async with client.stream(
                "POST",
                f"http://127.0.0.1:{manager.port}/v1/chat/completions",
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)["choices"][0]["delta"]
                        chunk = delta.get("content") or ""
                    except Exception:  # noqa: BLE001
                        continue
                    if chunk:
                        parts.append(chunk)
                        yield sse_event("message", {"content": chunk})
    except Exception as exc:  # noqa: BLE001
        logger.warning("本地模型对话失败: %s", exc)
        yield error_event("local_chat_failed", f"本地模型对话失败: {exc}")
        return

    reply = "".join(parts).strip()
    if not reply:
        yield error_event("local_chat_empty", "本地模型没有返回内容")
        return
    await asyncio.to_thread(db.add_message, session_id, "assistant", reply)
    yield sse_event(
        "done",
        {
            "message": "回答完成",
            "messageKey": "tool.answerDone",
            "messageParams": {},
            "content": reply,
        },
    )
