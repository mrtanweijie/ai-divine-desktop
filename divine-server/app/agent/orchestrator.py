"""Top-level agent streaming orchestration and SSE persistence."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, AsyncIterator

from langchain_core.messages import convert_to_messages
from langgraph.errors import GraphRecursionError
from langgraph.types import Command

from .. import db
from ..api.terminal import create_terminal_decision, remove_terminal_decision
from ..config import settings_store
from ..localization import default_session_title, normalize_locale
from ..sse import error_event, sse_event
from .context import AgentRunContext, canonical_path
from .llm import _build_llm, _resolve_tool_mode, generate_session_title
from .intent import classify_intents
from .persistence import (
    _extract_final_content,
    _extract_token_usage,
    _persist_new_messages,
    _sync_todos_from_state,
)
from .schema import _content_text
from .sse import _interrupt_sse, _stream_agent_run
from .tools import _build_agent, _build_tools, reset_agent_thread

logger = logging.getLogger("divine.agent.orchestrator")

# 本地可直接处理的意图（不需要调云端 LLM）
_LOCAL_INTENTS = {"open_app", "screenshot", "lock_screen", "search_file"}


def _can_handle_locally(
    intents: set[str],
    local_result: dict | None,
    threshold: float = 0.75,
) -> bool:
    """判断是否可以本地直接处理（不调云端 LLM）。"""
    if not intents:
        return False
    # 只要有一个意图属于本地可处理的，且本地模型置信度高
    if local_result and local_result.get("confidence", 0) >= threshold:
        return bool(intents & _LOCAL_INTENTS)
    return False

def _has_incomplete_tool_calls(messages: list[Any]) -> bool:
    from langchain_core.messages import AIMessage, ToolMessage

    pending: dict[str, int] = {}
    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls or []:
                call_id = (
                    call.get("id")
                    if isinstance(call, dict)
                    else getattr(call, "id", "")
                )
                if call_id:
                    pending[call_id] = pending.get(call_id, 0) + 1
        elif isinstance(message, ToolMessage):
            call_id = getattr(message, "tool_call_id", "") or ""
            if call_id in pending:
                pending[call_id] -= 1
                if pending[call_id] <= 0:
                    del pending[call_id]
    return bool(pending)

def _thread_trim_removals(
    messages: list[Any], limit: int
) -> list[Any]:
    """RemoveMessage entries dropping the oldest thread messages beyond limit.

    The kept suffix always starts at a HumanMessage boundary so tool-call
    pairs (AIMessage -> ToolMessage) are never split, which would otherwise
    make DeepSeek reject the request with a 400.
    """
    from langchain_core.messages import HumanMessage, RemoveMessage

    if limit <= 0 or len(messages) <= limit:
        return []
    keep_from = len(messages) - limit
    while keep_from < len(messages) and not isinstance(
        messages[keep_from], HumanMessage
    ):
        keep_from += 1
    if keep_from >= len(messages):
        return []
    return [
        RemoveMessage(id=message.id)
        for message in messages[:keep_from]
        if getattr(message, "id", None)
    ]

def _parse_stream_event(event: str) -> tuple[str, dict[str, Any]] | None:
    event_name = ""
    data_text = ""
    for line in event.splitlines():
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_text = line[5:].strip()
    if not data_text:
        return None
    try:
        return event_name, json.loads(data_text)
    except json.JSONDecodeError:
        return None

async def _persist_partial_generation(
    session_id: str, content: str, think: str
) -> None:
    if not content and not think:
        return
    saved = await asyncio.to_thread(
        db.add_message, session_id, "assistant", content
    )
    if think:
        await asyncio.to_thread(
            db.add_message_part, saved["id"], "think", think, order=0
        )

async def run_agent(
    session_id: str,
    history: list[dict[str, Any]],
    think: bool,
    workspace: Any,
    approval_mode: str = "ask",
    locale: str | None = None,
    effort: str | None = None,
    context_limit: int | None = None,
    cancel_event: asyncio.Event | None = None,
    model_id: str | None = None,
    approved_paths: list[str] | None = None,
    tool_mode: str | None = None,
) -> AsyncIterator[str]:
    """Stream one agent turn as SSE strings, handling interrupts and persistence."""
    workspace_path = workspace if isinstance(workspace, Path) else Path(workspace)
    session = db.get_session(session_id)
    resolved_tool_mode = _resolve_tool_mode(tool_mode, model_id)
    ctx = AgentRunContext(
        session_id=session_id,
        workspace=workspace_path,
        approval_mode=approval_mode,
        locale=normalize_locale(
            locale or (session or {}).get("locale") or "zh-CN"
        ),
        approved_paths=frozenset(
            canonical_path(path, workspace_path) for path in (approved_paths or [])
        ),
        think=think,
        effort=effort,
        model_id=model_id,
        cancel_event=cancel_event,
        tool_mode=resolved_tool_mode,
    )
    plan_mode = (session or {}).get("plan_mode") or "ask"
    if plan_mode == "direct":
        ctx.plan_choice_resolved = True
        ctx.plan_approved = True
    elif plan_mode == "plan_first":
        ctx.plan_choice_resolved = True
        ctx.plan_first_pending = True
    llm = _build_llm(think=think, effort=effort, model_id=model_id)
    tools = _build_tools(ctx)
    agent = _build_agent(llm, tools, ctx)
    config = {
        "configurable": {"thread_id": session_id},
        "recursion_limit": 256,
    }

    snapshot = await agent.aget_state(config)
    thread_messages = (snapshot.values or {}).get("messages") or []
    has_thread = bool(thread_messages)
    if has_thread and _has_incomplete_tool_calls(thread_messages):
        logger.warning(
            "agent thread has incomplete tool calls, resetting session=%s",
            session_id,
        )
        await reset_agent_thread(session_id)
        has_thread = False
    if has_thread:
        # Keep only the newest `context_limit` messages in the thread so long
        # sessions do not grow unbounded; trimming happens before this turn.
        limit = int(context_limit or 20)
        removals = _thread_trim_removals(thread_messages, limit)
        if removals:
            try:
                await agent.aupdate_state(config, {"messages": removals})
                logger.info(
                    "agent thread trimmed session=%s removed=%d kept<=%d",
                    session_id,
                    len(removals),
                    limit,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "agent thread trim failed session=%s: %s", session_id, exc
                )
        user_messages = [
            message
            for message in history
            if message.get("role") == "user"
        ]
        last_user = user_messages[-1] if user_messages else history[-1]
        input_messages = convert_to_messages([last_user])
        # Thread keeps only the recent window; re-inject the compacted
        # summary (if any) so early context survives the trim.
        summary = db.get_summary(session_id)
        if summary and summary.get("summary"):
            from langchain_core.messages import SystemMessage

            input_messages.insert(
                0,
                SystemMessage(
                    content=(
                        "以下是本次会话早期对话的摘要（已压缩，帮助理解上下文）：\n"
                        f"{summary['summary']}"
                    )
                ),
            )
    else:
        input_messages = convert_to_messages(history)
    question_text = _content_text(input_messages[-1].content) if input_messages else ""
    existing_messages = db.list_messages(session_id)
    has_assistant_content = any(
        message["role"] == "assistant"
        and str(message.get("content") or "").strip()
        for message in existing_messages
    )
    needs_title_summary = (
        not has_assistant_content
        and session is not None
        and session.get("title")
        in {
            default_session_title(ctx.locale),
            question_text[:24],
        }
    )

    # 本地意图识别 + 路由判断
    settings = settings_store.load()
    local_llm_enabled = settings.get("local_llm_enabled", False)
    local_llm_mode = settings.get("local_llm_mode", "keyword")
    local_llm_threshold = settings.get("local_llm_threshold", 0.75)
    history_context = ""
    if len(history) >= 2:
        last_ai = history[-2].get("content", "") if history[-2].get("role") == "assistant" else ""
        history_context = str(last_ai)[:500]

    intents, local_result = classify_intents(
        question_text,
        history_context=history_context,
        local_llm_enabled=local_llm_enabled,
        local_llm_mode=local_llm_mode,
        local_llm_threshold=local_llm_threshold,
    )

    # 更新上下文
    ctx.intents = intents
    ctx.local_intent_result = local_result

    # 如果可以本地处理，执行真实本地动作；执行不了就回退云端，绝不吞消息
    if _can_handle_locally(intents, local_result, local_llm_threshold):
        logger.info(
            "local intent handled session=%s intents=%s confidence=%.2f",
            session_id,
            intents,
            local_result.get("confidence", 0) if local_result else 0,
        )
        reply = None
        try:
            from .local_actions import execute_local_action

            # 截图保存到当前会话工作区 screenshots/，方便用户在工作区里
            # 直接找到/管理截图文件
            screenshot_dir = workspace_path / "screenshots"
            reply = await asyncio.to_thread(
                execute_local_action,
                intents,
                question_text,
                screenshot_dir,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("本地动作执行异常，回退云端: %s", e)

        if reply is None:
            # 目标不明 / 命令失败 / 模型误判 → 交给云端 agent 正常回答
            logger.info(
                "local intent 无法本地执行，回退云端 session=%s intents=%s",
                session_id,
                intents,
            )
        else:
            # 注意：用户消息已由调用方（api/chat.py:123 / scheduler）预先保存，
            # 这里不要重复 db.add_message("user")，否则每条消息会入库两次。
            # 只持久化 assistant 回复，保证会话历史与前端刷新一致。
            await asyncio.to_thread(
                db.add_message, session_id, "assistant", reply
            )
            yield sse_event("message", {"content": reply})
            # 正常收尾：前端依赖 done 事件结束流式状态并从服务端刷新消息列表
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

    logger.info(
        "agent start session=%s history=%d thread=%s tool_mode=%s",
        session_id,
        len(history),
        has_thread,
        resolved_tool_mode,
    )

    graph_input: Any = {"messages": input_messages}
    final_state: dict[str, Any] | None = None
    think_by_id: dict[str, str] = {}
    partial_think: list[str] = []
    partial_content: list[str] = []
    try:
        while True:
            interrupted = False
            async for kind, data in _stream_agent_run(
                agent,
                graph_input,
                config,
                react=(resolved_tool_mode == "react"),
            ):
                if cancel_event is not None and cancel_event.is_set():
                    await _persist_partial_generation(
                        session_id,
                        "".join(partial_content),
                        "".join(partial_think),
                    )
                    yield error_event(
                        "cancelled",
                        "任务已取消",
                        message_key="tool.taskCancelled",
                    )
                    return
                if kind == "sse":
                    parsed = _parse_stream_event(data)
                    if parsed:
                        event_name, payload = parsed
                        if event_name == "think":
                            partial_think.append(
                                str(payload.get("content") or "")
                            )
                        elif event_name == "message":
                            partial_content.append(
                                str(payload.get("content") or "")
                            )
                    yield data
                    continue
                if kind == "interrupts":
                    interrupted = True
                    resume_values: dict[str, dict[str, Any]] = {}
                    for item in data:
                        payload = dict(item.value)
                        if not payload.get("call_id"):
                            payload["call_id"] = f"confirm_{item.id}"
                        pending = create_terminal_decision(session_id)
                        try:
                            yield _interrupt_sse(payload, session_id)
                            await asyncio.wait_for(
                                pending["event"].wait(), 180
                            )
                            allowed = bool(pending["allowed"])
                        except asyncio.TimeoutError:
                            allowed = False
                        finally:
                            remove_terminal_decision(session_id)
                        if (
                            allowed
                            and payload.get("type")
                            in {
                                "skill_migrate",
                                "skill_migrate_batch",
                                "skill_install",
                            }
                        ):
                            tool_name = "migrate_skills"
                            if payload.get("type") == "skill_migrate":
                                tool_name = "migrate_skill"
                            elif payload.get("type") == "skill_install":
                                tool_name = "install_skill"
                            yield sse_event(
                                "tool",
                                {
                                    "tool": tool_name,
                                    "status": "running",
                                    "message": "正在执行，请稍候",
                                    "messageKey": "tool.executingWait",
                                    "messageParams": {},
                                    "call_id": payload.get("call_id", ""),
                                    "session_id": session_id,
                                },
                            )
                        if payload.get("action_requests"):
                            if allowed:
                                ctx.plan_approved = True
                                yield sse_event(
                                    "tool",
                                    {
                                        "tool": "write_todos",
                                        "status": "done",
                                        "message": "计划已确认，开始执行",
                                        "messageKey": "tool.planConfirmedStart",
                                        "messageParams": {},
                                        "confirm_type": "plan",
                                        "call_id": payload.get("call_id", ""),
                                        "session_id": session_id,
                                    },
                                )
                            else:
                                yield sse_event(
                                    "tool",
                                    {
                                        "tool": "write_todos",
                                        "status": "error",
                                        "message": "已取消执行计划",
                                        "messageKey": "tool.planCancelled",
                                        "messageParams": {},
                                        "confirm_type": "plan",
                                        "call_id": payload.get("call_id", ""),
                                        "session_id": session_id,
                                    },
                                )
                            resume_values[item.id] = {
                                "decisions": [
                                    {
                                        "type": (
                                            "approve" if allowed else "reject"
                                        )
                                    }
                                    for _ in payload["action_requests"]
                                ]
                            }
                        else:
                            resume_values[item.id] = {"allowed": allowed}
                    graph_input = Command(resume=resume_values)
                    break
                if kind == "final_state":
                    final_state, think_by_id = data
            if not interrupted:
                break
    except GraphRecursionError:
        yield error_event(
            "recursion_limit",
            "任务步骤过多，已停止。请拆分成更小的请求，或减少重复工具调用。",
            message_key="tool.recursionLimit",
        )
        return

    if final_state is None:
        yield error_event(
            "agent_error",
            "Agent 未返回结果",
            message_key="tool.agentError",
        )
        return

    messages = final_state.get("messages") or []
    _sync_todos_from_state(session_id, final_state)
    assistant_message_id = await asyncio.to_thread(
        _persist_new_messages, session_id, input_messages, messages, think_by_id
    )
    final_content = _extract_final_content(messages)
    # Record this turn's token consumption (real API usage when available).
    usage = _extract_token_usage(messages, input_messages, final_content)
    if assistant_message_id and usage:
        try:
            await asyncio.to_thread(
                db.save_token_usage,
                session_id,
                assistant_message_id,
                usage["input"],
                usage["output"],
                usage["total"],
                usage["source"],
            )
        except Exception:  # noqa: BLE001 - usage tracking must never fail a turn
            logger.exception("save token usage failed session=%s", session_id)
    if needs_title_summary:
        title = await generate_session_title(
            llm,
            question_text,
            final_content,
            ctx.locale,
        )
        if title:
            await asyncio.to_thread(db.update_session, session_id, title=title)
            logger.info("session title summarized session=%s", session_id)
    yield sse_event(
        "done",
        {
            "message": "回答完成",
            "messageKey": "tool.answerDone",
            "messageParams": {},
            "content": final_content,
        },
    )
    logger.info(
        "agent done session=%s content_len=%d",
        session_id,
        len(final_content),
    )
    # Compact the session when enough new messages accumulated. Best-effort:
    # never fail the turn on compaction errors, and keep it off the critical
    # path by emitting a dedicated SSE event after "done".
    try:
        from .compact import compact_session

        saved = await compact_session(session_id, context_limit)
        if saved and saved.get("summary"):
            yield sse_event(
                "compacted",
                {
                    "savedTokens": int(saved.get("saved_tokens") or 0),
                    "summary": saved["summary"],
                },
            )
            logger.info(
                "session compaction emitted id=%s saved_tokens=%s",
                session_id,
                saved.get("saved_tokens", 0),
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("session compaction failed id=%s: %s", session_id, exc)
