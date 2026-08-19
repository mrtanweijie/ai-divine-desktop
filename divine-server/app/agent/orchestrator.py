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
from ..localization import default_session_title, normalize_locale
from ..sse import error_event, sse_event
from .context import AgentRunContext
from .llm import _build_llm, generate_session_title
from .persistence import (
    _extract_final_content,
    _persist_new_messages,
    _sync_todos_from_state,
)
from .schema import _content_text
from .sse import _interrupt_sse, _stream_agent_run
from .tools import _build_agent, _build_tools, reset_agent_thread

logger = logging.getLogger("divine.agent.orchestrator")

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

def _persist_partial_generation(
    session_id: str, content: str, think: str
) -> None:
    if not content and not think:
        return
    saved = db.add_message(session_id, "assistant", content)
    if think:
        db.add_message_part(saved["id"], "think", think, order=0)

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
) -> AsyncIterator[str]:
    """Stream one agent turn as SSE strings, handling interrupts and persistence."""
    workspace_path = workspace if isinstance(workspace, Path) else Path(workspace)
    session = db.get_session(session_id)
    ctx = AgentRunContext(
        session_id=session_id,
        workspace=workspace_path,
        approval_mode=approval_mode,
        locale=normalize_locale(
            locale or (session or {}).get("locale") or "zh-CN"
        ),
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
    logger.info(
        "agent start session=%s history=%d thread=%s",
        session_id,
        len(history),
        has_thread,
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
                agent, graph_input, config
            ):
                if cancel_event is not None and cancel_event.is_set():
                    _persist_partial_generation(
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
    _persist_new_messages(session_id, input_messages, messages, think_by_id)
    final_content = _extract_final_content(messages)
    if needs_title_summary:
        title = await generate_session_title(
            llm,
            question_text,
            final_content,
            ctx.locale,
        )
        if title:
            db.update_session(session_id, title=title)
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
