from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .. import db
from ..agent.core.constants import approval_timeout_seconds
from ..agent import run_agent
from ..agent.core import normalize_ui_theme
from ..agent.core.injection import (
    MAX_CONTENT_LENGTH,
    MAX_PENDING_INJECTIONS,
    SUPPLEMENT_PREFIX,
    discard_injections,
    enqueue_injection,
    pending_count,
)
from ..config import settings_store, workspace_dir
from ..document_reader import read_file_text
from ..file_types import is_image_path
from ..localization import default_session_title, normalize_locale
from ..schemas import (
    Attachment,
    ChatAnswer,
    InjectRequest,
    RetryCloudRequest,
    StreamChatRequest,
)
from ..sse import error_event, sse_event
from .terminal import resolve_terminal_answer

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
    ui_theme = normalize_ui_theme(request.ui_theme)
    if request.session_id:
        existing_session = await asyncio.to_thread(
            db.get_session, request.session_id
        )
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
        if await asyncio.to_thread(db.get_session, session_id) is None:
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
            await asyncio.to_thread(
                db.update_session, session_id, locale=locale
            )
    else:
        if request.project_id and await asyncio.to_thread(
            db.get_project, request.project_id
        ) is None:
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
        session_id = (
            await asyncio.to_thread(
                db.create_session,
                title=default_session_title(locale),
                project_id=request.project_id,
                approval_mode=request.approval_mode,
                locale=locale,
            )
        )["id"]

    session = await asyncio.to_thread(db.get_session, session_id)
    approval_mode = (
        request.approval_mode
        or session.get("approval_mode")
        or "ask"
    )
    workspace = Path(
        await asyncio.to_thread(db.session_workspace, session_id)
        or workspace_dir()
    )
    # 本地预整理：长文本先由本地模型整理成结构化版本，原文转存附件
    # （见 docs/design/005-preprocess-20260829.md；失败/不可用一律原样上云）
    final_question = question
    original_attachment: Path | None = None
    organized = False
    attempted_question = False
    try:
        from ..agent.middleware import maybe_preprocess

        final_question, original_attachment, organized, attempted_question = (
            await asyncio.to_thread(
                maybe_preprocess, question, session_id, workspace
            )
        )
    except Exception as exc:  # noqa: BLE001 — 预整理失败绝不影响对话
        logger.warning("本地预整理异常，原样上云: %s", exc)
    messages = await asyncio.to_thread(db.list_messages, session_id)
    if not messages:
        title = question[:24] if len(question) > 24 else question
        await asyncio.to_thread(db.update_session, session_id, title=title)
    message = await asyncio.to_thread(
        db.add_message, session_id, "user", final_question
    )
    if organized and original_attachment is not None:
        try:
            # file 附件：只带路径，不注入原文内容（决策 3，省 token）。
            # preprocess_original 标记供前端过滤——UI 用 preprocess 部件展示
            # 可展开原文，这里只服务模型（history_for_model 读 path 引用）。
            await asyncio.to_thread(
                db.add_message_part,
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
            await asyncio.to_thread(
                db.add_message_part,
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
                from ..agent.middleware import maybe_preprocess_attachment

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
                    await asyncio.to_thread(
                        db.add_message_part,
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
        await asyncio.to_thread(
            db.add_message_part,
            message["id"],
            "file",
            json.dumps(meta, ensure_ascii=False),
            order=index,
        )

    settings = await asyncio.to_thread(settings_store.load)
    context_limit = int(settings.get("context_limit") or 20)
    history = await asyncio.to_thread(
        db.history_for_model, session_id, limit=context_limit
    )
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
            from ..agent.core import _resolve_model_entry

            entry = _resolve_model_entry(settings, request.model_id)
            if entry.get("provider") == "local":
                async for event in stream_local_chat(
                    session_id, final_question, history, locale
                ):
                    yield event
                return

            # 指代补全：短指代后续（"分别是"/"然后呢"）→ 模型侧用自包含补全版
            # （上一问+已回答+追问），历史/数据库仍保存原文。解决多轮断点。
            model_question = final_question
            model_history = history
            _expanded = (
                _expand_referential_followup(final_question, history)
                or _expand_choice_selection(final_question, history)
            )
            if _expanded:
                model_question = _expanded
                model_history = _replace_last_user(history, _expanded)

            # 本地能力路由：简单任务（翻译/闲聊/提取/改写/计算）本地模型直答，
            # 省 token。带附件时跳过（涉及文件的复杂任务交给预处理+云端）。
            # 模型没在跑时自动拉起（复用预整理 _start_local_model，最长 ~40s），
            # 避免"简单任务静默走云端"——起不来才回退云端。
            # 实时信息请求：系统层强制联网（不依赖模型自觉）。
            # 命中新闻/天气/股票等关键词 → 跳过本地路由、注入硬指令，
            # 禁止"无法提供实时信息"类拒绝（deepseek-v4-flash 常无视提示词）。
            if _is_realtime_request(model_question):
                model_question = (
                    "（用户请求实时信息，必须调用 web_search / web_fetch 工具"
                    "获取真实数据，禁止回复「无法提供实时信息」或建议用户自行查看。）"
                    f"\n{model_question}"
                )
                model_history = _replace_last_user(history, model_question)
            else:
                # 带附件时不做本地能力路由（task=None → 走云端 agent）
                task = None
                if not request.attachments:
                    # 用原始文本检测本地任务（扩展后文本可能超长导致误判），
                    # 但传给模型的仍是扩展后文本（含上下文补全）。
                    task = _detect_local_task(
                        final_question, _ai_asking_hint(history)
                    )
                if task:
                    from ..agent.core import get_manager
                    from ..agent.middleware import _start_local_model

                    manager = get_manager()
                    if not await asyncio.to_thread(manager.is_ready):
                        _start_local_model(manager)
                    if await asyncio.to_thread(manager.is_ready):
                        if task == "qa":
                            # 知识问答：护栏式本地答（不确定/拒答/空 → 回退云端）
                            reply = await asyncio.to_thread(
                                _local_answer,
                                model_question,
                                _LOCAL_TASK_PROMPTS["qa"],
                            )
                            if (
                                reply
                                and not _is_local_refusal(reply)
                                and len(reply) <= 500
                                and not (
                                    # 列表题护栏：要列表却只给短答/没列 → 回退云端
                                    _is_list_request(model_question)
                                    and not _has_list_items(reply)
                                )
                            ):
                                await asyncio.to_thread(
                                    db.add_message,
                                    session_id,
                                    "assistant",
                                    reply,
                                    source="local",
                                )
                                yield sse_event(
                                    "message", {"content": reply}
                                )
                                yield sse_event(
                                    "done",
                                    {
                                        "message": "回答完成",
                                        "messageKey": "tool.answerDone",
                                        "messageParams": {},
                                        "content": reply,
                                    },
                                )
                                return
                            # 本地拒答/不确定/空（"我无法提供实时信息…"）：
                            # 不落库、不提示，直接云端接管回答（本地这句拒答
                            # 不留痕）；挂"转云端"标记，云端回答落库时记
                            # source='local_fallback'（后端留痕）。
                            await asyncio.to_thread(
                                db.mark_fallback_pending, session_id
                            )
                        else:
                            # 流式本地答：defer_emit 攒完整回复再判——
                            # 正常回答一次性展示；本地拒答时拒答文本不闪现
                            # （不落库、不提示），直接云端接管。
                            local_replies: list[str] = []
                            async for event in stream_local_chat(
                                session_id,
                                model_question,
                                model_history,
                                locale,
                                system_prompt=_LOCAL_TASK_PROMPTS[task],
                                on_reply=local_replies.append,
                                defer_emit=True,
                            ):
                                yield event
                            if not local_replies:
                                # 本地失败/空：错误事件已发出 → 结束
                                return
                            reply = local_replies[0]
                            if not _is_local_refusal(reply):
                                await asyncio.to_thread(
                                    db.add_message,
                                    session_id,
                                    "assistant",
                                    reply,
                                    source="local",
                                )
                                yield sse_event(
                                    "message", {"content": reply}
                                )
                                yield sse_event(
                                    "done",
                                    {
                                        "message": "回答完成",
                                        "messageKey": "tool.answerDone",
                                        "messageParams": {},
                                        "content": reply,
                                    },
                                )
                                return
                            # 本地拒答 → 不落库、不提示，继续往下走云端模型回答；
                            # 挂"转云端"标记，云端回答落库时记 source='local_fallback'
                            db.mark_fallback_pending(session_id)

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
                        await asyncio.wait_for(
                            pending["event"].wait(),
                            approval_timeout_seconds(settings),
                        )
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

            from ..agent.core.constants import OPTIONS_CARD_HINT

            async for event in run_agent(
                session_id,
                model_history,
                request.think,
                output_hint=OPTIONS_CARD_HINT,
                workspace=workspace,
                approval_mode=approval_mode,
                locale=locale,
                effort=request.reasoning_effort,
                context_limit=context_limit,
                cancel_event=cancel_event,
                model_id=request.model_id,
                approved_paths=approved_paths,
                tool_mode=request.tool_mode,
                ui_theme=ui_theme,
            ):
                yield event
            # 兜底清理：云端没产出 assistant 消息时，转云端标记不泄漏到下一轮
            await asyncio.to_thread(
                db.clear_fallback_pending, session_id
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "stream_chat error session=%s: %s", session_id, exc
            )
            yield error_event("server_error", str(exc))
        finally:
            _CANCEL_EVENTS.pop(session_id, None)
            await asyncio.to_thread(db.touch_session, session_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/retry_cloud")
async def retry_cloud(request: RetryCloudRequest):
    """本地模型回答不满意 → 用户点【重答】：对同一问题直接用云端重答。

    不复述用户消息（历史里已有）：回溯到目标本地回答前面的用户问题，
    历史截断到该问题为止，直接跑云端 agent，追加一条云端回答。
    不做本地路由/预整理——用户已明确要云端。
    """
    from ..config import workspace_dir

    session = await asyncio.to_thread(db.get_session, request.session_id)
    if session is None:
        return StreamingResponse(
            iter([error_event("not_found", "会话不存在")]),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    messages = await asyncio.to_thread(db.list_messages, request.session_id)
    target_index = next(
        (
            index
            for index, message in enumerate(messages)
            if message["id"] == request.message_id
        ),
        None,
    )
    if target_index is None:
        return StreamingResponse(
            iter([error_event("not_found", "消息不存在")]),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    question_index = None
    for index in range(target_index - 1, -1, -1):
        if messages[index]["role"] == "user":
            question_index = index
            break
    if question_index is None:
        return StreamingResponse(
            iter([error_event("no_question", "未找到对应问题")]),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    settings = settings_store.load()
    context_limit = int(settings.get("context_limit") or 20)
    history = db.history_for_model(
        request.session_id,
        limit=context_limit,
        until_message_id=messages[question_index]["id"],
    )
    approval_mode = (
        request.approval_mode or session.get("approval_mode") or "ask"
    )
    locale = normalize_locale(
        request.locale or session.get("locale") or "zh-CN"
    )
    ui_theme = normalize_ui_theme(request.ui_theme)
    workspace = Path(
        db.session_workspace(request.session_id) or workspace_dir()
    )

    async def generate():
        cancel_event = asyncio.Event()
        _CANCEL_EVENTS[request.session_id] = cancel_event
        try:
            async for event in run_agent(
                request.session_id,
                history,
                request.think,
                workspace=workspace,
                approval_mode=approval_mode,
                locale=locale,
                effort=request.reasoning_effort,
                context_limit=context_limit,
                cancel_event=cancel_event,
                model_id=request.model_id,
                approved_paths=[],
                tool_mode=request.tool_mode,
                ui_theme=ui_theme,
            ):
                yield event
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "retry_cloud error session=%s: %s", request.session_id, exc
            )
            yield error_event("server_error", str(exc))
        finally:
            discard_injections(request.session_id)
            _CANCEL_EVENTS.pop(request.session_id, None)
            db.touch_session(request.session_id)

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


@router.post("/chat/answer")
async def answer_question(request: ChatAnswer) -> dict[str, object]:
    """ask_user：提交用户对执行中问题的回答，唤醒等待中的 agent。

    内部转写为对同一 session pending 槽位的 set（复用 terminal/decide 的
    asyncio.Event 生命周期，按 session 单槽位——orchestrator 逐 item
    串行 await，同刻仅一个未决）。call_id 由前端配对展示，不参与寻址。
    """
    if db.get_session(request.session_id) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    if not resolve_terminal_answer(request.session_id, request.answer):
        raise HTTPException(status_code=409, detail="no_pending_ask")
    return {"ok": True}


@router.post("/sessions/{session_id}/inject")
async def inject_message(session_id: str, request: InjectRequest) -> object:
    """用户插话（steering）：agent 执行中主动补充信息。

    无活跃流时返回 409，前端降级为常规发送（语义即新一轮消息）。
    有活跃流时落库 + 入队，由 UserInjectionMiddleware 在下一次
    模型调用前注入 state；run 收尾若仍未消费则 discard（消息已在
    DB，下一轮 history 自然携带，不跨 run 泄漏、不重复注入）。
    """
    content = request.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="内容不能为空")
    if len(content) > MAX_CONTENT_LENGTH:
        raise HTTPException(status_code=400, detail="内容过长")
    if db.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    if _CANCEL_EVENTS.get(session_id) is None:
        raise HTTPException(status_code=409, detail="no_active_stream")
    if pending_count(session_id) >= MAX_PENDING_INJECTIONS:
        raise HTTPException(status_code=429, detail="待处理补充过多")

    await asyncio.to_thread(
        db.add_message, session_id, "user", f"{SUPPLEMENT_PREFIX} {content}"
    )
    if not enqueue_injection(session_id, content):
        # 理论不可达（pending_count 已挡），双保险避免消息丢失
        raise HTTPException(status_code=429, detail="待处理补充过多")
    db.touch_session(session_id)
    return {"ok": True}

# --- 本地聊天子系统（已拆分至 chat_local.py，此处 re-export 兼容既有引用） ---
from .chat_local import (
    _AI_ASKING_MARKERS,
    _ACTION_WORDS,
    _CHAT_MARKERS,
    _DOC_TOOL_MARKERS,
    _ENTITY_KNOWLEDGE_MARKERS,
    _EXTRACT_MARKERS,
    _LIST_ITEM_PUNCT,
    _LIST_REQUEST_MARKERS,
    _LOCAL_TASK_DETECTORS,
    _LOCAL_TASK_PROMPTS,
    _NUMERIC_FACT_MARKERS,
    _OPTIONS_BLOCK_RE,
    _QA_FALLBACK_MARKERS,
    _QUESTION_MARKERS,
    _REALTIME_KEYWORDS,
    _REALTIME_PATTERNS,
    _REFERENTIAL_WORDS,
    _REFUSAL_PATTERNS,
    _REWRITE_MARKERS,
    _SMALL_LANGS,
    _ai_asking_hint,
    _build_local_chat_messages,
    _detect_calc,
    _detect_extract,
    _detect_local_task,
    _detect_qa,
    _detect_rewrite,
    _detect_simple_chat,
    _expand_choice_selection,
    _expand_referential_followup,
    _extract_choice_labels,
    _has_list_items,
    _is_list_request,
    _is_local_refusal,
    _is_realtime_request,
    _is_simple_translation,
    _local_answer,
    _replace_last_user,
    stream_local_chat,
)
