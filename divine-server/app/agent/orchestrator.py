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
from ..config import DEFAULT_LOCAL_LLM_THRESHOLD, settings_store
from ..localization import default_session_title, normalize_locale
from ..sse import error_event, sse_event
from .core import (
    AGENT_RECURSION_LIMIT,
    approval_timeout_seconds,
    AgentRunContext,
    _build_llm,
    _content_text,
    _interrupt_sse,
    _resolve_tool_mode,
    _skill_tool_name,
    _stream_agent_run,
    canonical_path,
    estimate_tokens,
    generate_session_title,
    normalize_ui_theme,
)
from .intent import classify_intents, is_question_like
from .state import (
    _extract_final_content,
    _extract_token_usage,
    _persist_new_messages,
    _sync_todos_from_state,
)
from .tools import _build_agent, _build_tools, reset_agent_thread

logger = logging.getLogger("divine.agent.orchestrator")

# 本地可直接处理的意图（不需要调云端 LLM）
_LOCAL_INTENTS = {"open_app", "screenshot", "lock_screen", "search_file"}


def _can_handle_locally(
    intents: set[str],
    local_result: dict | None,
    threshold: float = DEFAULT_LOCAL_LLM_THRESHOLD,
) -> bool:
    """判断是否可以本地直接处理（不调云端 LLM）。"""
    if not intents:
        return False
    # 只要有一个意图属于本地可处理的，且本地模型置信度高
    if local_result and local_result.get("confidence", 0) >= threshold:
        return bool(intents & _LOCAL_INTENTS)
    return False

def _pending_tool_call_ids(messages: list[Any]) -> list[tuple[str, str]]:
    """Unanswered tool calls as (call_id, tool_name), in thread order.

    Occurs after a crash/cancel between an AIMessage with tool_calls and its
    ToolMessages; providers reject such threads, so callers repair them.
    """
    from langchain_core.messages import AIMessage, ToolMessage

    pending: dict[str, str] = {}
    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls or []:
                call_id = (
                    call.get("id")
                    if isinstance(call, dict)
                    else getattr(call, "id", "")
                )
                name = (
                    call.get("name")
                    if isinstance(call, dict)
                    else getattr(call, "name", "")
                )
                if call_id:
                    pending[call_id] = str(name or "")
        elif isinstance(message, ToolMessage):
            call_id = getattr(message, "tool_call_id", "") or ""
            if call_id in pending:
                del pending[call_id]
    return list(pending.items())


def _has_incomplete_tool_calls(messages: list[Any]) -> bool:
    return bool(_pending_tool_call_ids(messages))


def _repair_tool_groups(
    messages: list[Any],
) -> tuple[list[Any], list[Any]]:
    """Compute thread repairs for orphan tool-call groups (protocol semantics).

    返回 ``(removes, appends)``，一次 ``aupdate_state`` 提交：

    - removes：**中段**孤儿组整组删除（RemoveMessage）。append 无法给中段
      孤儿原位补齐——LangGraph messages 通道只能追加，若把占位 ToolMessage
      补到尾部，重放时该 assistant(tool_calls) 之后仍缺紧跟的 tool 响应，
      OpenAI 兼容 API 依旧 400。删除整组，让模型在下一轮重新规划。
    - appends：**尾部**孤儿组缺失的 tool 响应用占位 ToolMessage 补齐
      （原位即尾部，追加即修复），尽量保留线程上下文。

    孤儿判定遵循协议语义而非全局 id 配对：assistant(tool_calls) 之后
    连续出现的 tool 消息必须覆盖全部 call id，到下一条非 tool 消息仍未
    覆盖即为残缺组（与 db.history._sanitize_tool_groups 同规则）。这与
    ``_pending_tool_call_ids`` 的"全局按 id 配对"不同——后者会把
    [A(c1), A(c2), tool(c1), tool(c2)] 判为完整，但 API 校验要求 tool 紧跟
    assistant，交错序列同样会被 400 拒绝。
    """
    from langchain_core.messages import AIMessage, RemoveMessage, ToolMessage

    removes: list[Any] = []
    appends: list[Any] = []
    count = len(messages)
    index = 0
    while index < count:
        message = messages[index]
        calls = getattr(message, "tool_calls", None) or []
        if not isinstance(message, AIMessage) or not calls:
            index += 1
            continue
        pending: dict[str, str] = {}
        for call in calls:
            cid = (
                call.get("id")
                if isinstance(call, dict)
                else getattr(call, "id", "")
            )
            name = (
                call.get("name")
                if isinstance(call, dict)
                else getattr(call, "name", "")
            )
            if cid:
                pending[str(cid)] = str(name or "")
        if not pending:
            index += 1
            continue
        group_tools: list[Any] = []
        cursor = index + 1
        while cursor < count and isinstance(messages[cursor], ToolMessage):
            cid = getattr(messages[cursor], "tool_call_id", "") or ""
            if cid in pending:
                del pending[cid]
            group_tools.append(messages[cursor])
            cursor += 1
        if pending:
            if cursor >= count:
                # 尾部残缺：占位补齐缺失的 tool 响应（保留线程上下文）
                for call in calls:
                    cid = (
                        call.get("id")
                        if isinstance(call, dict)
                        else getattr(call, "id", "")
                    )
                    if cid in pending:
                        name = (
                            call.get("name")
                            if isinstance(call, dict)
                            else getattr(call, "name", "")
                        )
                        appends.append(
                            ToolMessage(
                                content=(
                                    "上一轮工具调用被中断，没有返回结果。"
                                    "如需该信息请重新调用工具。"
                                ),
                                tool_call_id=cid,
                                name=name or "tool",
                            )
                        )
            else:
                # 中段残缺：无原位补齐手段，整组删除（assistant + 已落结果）
                for tool_message in group_tools:
                    if getattr(tool_message, "id", None):
                        removes.append(RemoveMessage(id=tool_message.id))
                if getattr(message, "id", None):
                    removes.append(RemoveMessage(id=message.id))
        index = cursor
    return removes, appends


_TOOL_STUB_MIN_CHARS = 600
_TOOL_STUB_KEEP_RECENT = 12
_TOOL_STUB_TEXT = (
    "[早期工具结果已清理：{name}，原 {chars} 字符。如需该信息请重新调用工具]"
)


def _thread_token_budget() -> int:
    """Message-token budget for the thread: ~70% of the model context window.

    system prompt + tool schemas + 当前轮回复落在剩余 30% 里。按 token 而不是
    按消息条数裁剪，长编码任务早期读过的文件/计划不会在几十条消息后被丢掉。
    """
    try:
        from .state import context_window

        window = context_window()
    except Exception:  # noqa: BLE001 — 预算计算失败时保守取小窗口
        window = 128_000
    return max(int(window * 0.7), 12_000)


def _message_tokens(message: Any) -> int:
    content = _content_text(getattr(message, "content", ""))
    tokens = estimate_tokens(content)
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        tokens += estimate_tokens(
            json.dumps(tool_calls, ensure_ascii=False, default=str)
        )
    return tokens


def _thread_context_actions(
    messages: list[Any],
    limit: int,
    token_budget: int | None = None,
) -> tuple[list[Any], list[Any]]:
    """Token-budget trim + old tool-result stubbing for the agent thread.

    返回 ``(removals, stubs)``，一次 ``aupdate_state`` 同时提交：

    - removals：超出保留窗口的旧消息整体删除（RemoveMessage）。删除边界
      仍是 HumanMessage 起点，不会拆散 AIMessage→ToolMessage 配对。
    - stubs：保留窗口内、但已滑出最近尾部（limit 条之外）的长 ToolMessage
      用同 id 的占位消息置换，结构保留、字节缩小——旧文件内容不再长期
      占用上下文，需要时可重新读取。

    ``limit`` 语义变为"最近 N 条完整保留"（默认 30）；硬删除由 token 预算
    （窗口 70%）和条数上限（limit*4，防结构性膨胀）触发。
    """
    from langchain_core.messages import (
        HumanMessage,
        RemoveMessage,
        ToolMessage,
    )

    if not messages:
        return [], []
    budget = token_budget or _thread_token_budget()
    max_count = max(limit * 4, 80)

    # 1. token 预算：从最新往旧累计，超出预算处为删除边界
    total = 0
    cut_by_tokens = 0
    for index in range(len(messages) - 1, -1, -1):
        total += _message_tokens(messages[index])
        if total > budget:
            cut_by_tokens = index + 1
            break

    # 2. 条数硬上限：防纯结构膨胀（stub 保留条数，条数本身不缩）
    cut = cut_by_tokens
    if len(messages) > max_count:
        cut = max(cut, len(messages) - max_count)

    # 删除边界推进到 HumanMessage 起点，保证不拆散 tool-call 配对
    while cut < len(messages) and not isinstance(
        messages[cut], HumanMessage
    ):
        cut += 1
    if cut >= len(messages):
        # 兜底：全删会丢掉当前任务，至少保留最后两条（AI+工具结果 或 问答对）
        cut = max(0, len(messages) - 2)

    removals = [
        RemoveMessage(id=message.id)
        for message in messages[:cut]
        if getattr(message, "id", None)
    ]

    # 3. 旧工具结果置换：保留窗口内、最近 _TOOL_STUB_KEEP_RECENT 条之外
    stub_zone_end = len(messages) - _TOOL_STUB_KEEP_RECENT
    stubs: list[Any] = []
    for index in range(cut, stub_zone_end):
        message = messages[index]
        if not isinstance(message, ToolMessage):
            continue
        text = _content_text(message.content) if message.content else ""
        if len(text) <= _TOOL_STUB_MIN_CHARS:
            continue
        stubs.append(
            ToolMessage(
                content=_TOOL_STUB_TEXT.format(
                    name=getattr(message, "name", None) or "tool",
                    chars=len(text),
                ),
                tool_call_id=getattr(message, "tool_call_id", "") or "",
                name=getattr(message, "name", None) or "tool",
                id=message.id,
            )
        )
    return removals, stubs

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


def _unused_mention_skills(
    messages: list[Any], mentioned: frozenset[str]
) -> list[str]:
    """校验本轮 `/技能` 引用是否真的生效（方案 025 §3.3）。

    技能引用是用户与 agent 之间的契约：本轮至少应产生一次
    `load_skill(技能名)` 或该能力技能对应的工具调用；否则把技能名回传给
    前端提示“技能未被使用”——不然“选错了”用户无从察觉。
    """
    if not mentioned:
        return []
    called: set[str] = set()
    loaded: set[str] = set()
    for message in messages:
        for call in getattr(message, "tool_calls", None) or ():
            if isinstance(call, dict):
                name = str(call.get("name") or "")
                args = call.get("args") or {}
            else:
                name = str(getattr(call, "name", "") or "")
                args = getattr(call, "args", None) or {}
            if not name:
                continue
            called.add(name)
            if name == "load_skill" and isinstance(args, dict):
                loaded.add(str(args.get("name") or ""))
        # 部分 provider 只在 ToolMessage 上回写工具名，兜底再收一遍
        if getattr(message, "type", "") == "tool":
            tool_name = str(getattr(message, "name", "") or "")
            if tool_name:
                called.add(tool_name)
    unused: list[str] = []
    for skill_name in mentioned:
        if skill_name in loaded or _skill_tool_name(skill_name) in called:
            continue
        unused.append(skill_name)
    return unused


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
    output_hint: str | None = None,
    ui_theme: str | None = None,
    mention_skills: list[str] | None = None,
) -> AsyncIterator[str]:
    """Stream one agent turn as SSE strings, handling interrupts and persistence."""
    import time as _time

    turn_started = _time.monotonic()
    workspace_path = workspace if isinstance(workspace, Path) else Path(workspace)
    session = await asyncio.to_thread(db.get_session, session_id)
    resolved_tool_mode = _resolve_tool_mode(tool_mode, model_id)
    ctx = AgentRunContext(
        session_id=session_id,
        workspace=workspace_path,
        approval_mode=approval_mode,
        locale=normalize_locale(
            locale or (session or {}).get("locale") or "zh-CN"
        ),
        ui_theme=normalize_ui_theme(ui_theme),
        approved_paths=frozenset(
            canonical_path(path, workspace_path) for path in (approved_paths or [])
        ),
        think=think,
        effort=effort,
        model_id=model_id,
        cancel_event=cancel_event,
        tool_mode=resolved_tool_mode,
        mention_skills=frozenset(mention_skills or []),
    )
    plan_mode = (session or {}).get("plan_mode") or "ask"
    if plan_mode == "direct":
        ctx.plan_choice_resolved = True
        ctx.plan_approved = True
    elif plan_mode == "plan_first":
        ctx.plan_choice_resolved = True
        ctx.plan_first_pending = True

    # 回合开始前快照工作区（P3-3b）：供 undo_last_turn 撤销本轮改动。
    # 快照失败绝不阻断对话；大仓库/超限场景在 create_checkpoint 内部跳过。
    try:
        from ..tools.checkpoint import create_checkpoint

        checkpoint_info = await asyncio.to_thread(
            create_checkpoint, workspace_path, session_id
        )
        if checkpoint_info.get("skipped"):
            logger.info(
                "turn checkpoint skipped session=%s reason=%s",
                session_id,
                checkpoint_info["skipped"],
            )
    except Exception as exc:  # noqa: BLE001 — 快照失败绝不阻断对话
        logger.warning("turn checkpoint failed session=%s: %s", session_id, exc)

    # 意图识别（提前到工具构建前——工具按意图裁减需要，见 tools._CONTENT_TOOLS）。
    # 从 history 取当前用户消息做分类，与后文线程化 question_text 等价。
    settings = await asyncio.to_thread(settings_store.load)
    local_llm_enabled = settings.get("local_llm_enabled", False)
    local_llm_mode = settings.get("local_llm_mode", "keyword")
    local_llm_threshold = settings.get(
        "local_llm_threshold", DEFAULT_LOCAL_LLM_THRESHOLD
    )
    _hist_user = next(
        (m for m in reversed(history) if m.get("role") == "user"), None
    )
    history_context = ""
    if len(history) >= 2:
        last_ai = (
            history[-2].get("content", "")
            if history[-2].get("role") == "assistant"
            else ""
        )
        history_context = str(last_ai)[:500]
    intents, local_result = await asyncio.to_thread(
        classify_intents,
        str((_hist_user or {}).get("content") or ""),
        history_context=history_context,
        local_llm_enabled=local_llm_enabled,
        local_llm_mode=local_llm_mode,
        local_llm_threshold=local_llm_threshold,
    )
    ctx.intents = intents
    ctx.local_intent_result = local_result

    llm = _build_llm(think=think, effort=effort, model_id=model_id)
    # MCP 工具索引刷新（带 TTL 缓存，失败容忍）：在 _build_tools 同步读取前更新
    try:
        from ..mcp.manager import mcp_manager

        await mcp_manager.refresh_tool_index()
    except Exception as exc:  # noqa: BLE001 — MCP 不可用不影响本地工具
        logger.warning("MCP tool index refresh failed: %s", exc)
    tools = _build_tools(ctx)
    from .core.checkpointer import get_checkpointer

    checkpointer = await get_checkpointer()
    agent = _build_agent(llm, tools, ctx, checkpointer)
    config = {
        "configurable": {"thread_id": session_id},
        "recursion_limit": AGENT_RECURSION_LIMIT,
    }

    snapshot = await agent.aget_state(config)
    thread_messages = (snapshot.values or {}).get("messages") or []
    has_thread = bool(thread_messages)
    if has_thread:
        # 上次运行在工具调用中途被中断（崩溃/取消/超时），或历史里残留了
        # 中段孤儿组（tool 消息未紧跟其 assistant）。按协议语义修复：
        # 尾部残缺合成 ToolMessage 补齐让线程恢复一致；中段孤儿组整组删除
        # （append 无法原位补齐中段，重放时 API 仍会 400）。修复失败才清零。
        removes, appends = _repair_tool_groups(thread_messages)
        if removes or appends:
            try:
                await agent.aupdate_state(
                    config, {"messages": removes + appends}
                )
                logger.warning(
                    "repaired interrupted tool calls session=%s "
                    "appended=%d removed=%d",
                    session_id,
                    len(appends),
                    len(removes),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "agent thread repair failed, resetting session=%s: %s",
                    session_id,
                    exc,
                )
                await reset_agent_thread(session_id)
                has_thread = False
    if has_thread:
        # 上下文整理（本轮开始前）：token 预算硬裁剪 + 旧工具结果占位置换。
        # limit 语义为"最近 N 条完整保留"；硬删除由 token 预算与条数上限触发。
        limit = int(context_limit or 20)
        removals, stubs = _thread_context_actions(thread_messages, limit)
        if removals or stubs:
            try:
                await agent.aupdate_state(
                    config, {"messages": removals + stubs}
                )
                logger.info(
                    "agent thread compacted session=%s removed=%d stubbed=%d "
                    "recent_keep=%d",
                    session_id,
                    len(removals),
                    len(stubs),
                    limit,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "agent thread compact failed session=%s: %s",
                    session_id,
                    exc,
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
        summary = await asyncio.to_thread(db.get_summary, session_id)
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
    existing_messages = await asyncio.to_thread(db.list_messages, session_id)
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

    # 本地意图识别 + 路由判断已提前到工具构建前（见上方），此处直接使用
    # 已计算好的 intents / local_result，执行本地动作或回退云端。
    if _can_handle_locally(intents, local_result, local_llm_threshold):
        logger.info(
            "local intent handled session=%s intents=%s confidence=%.2f",
            session_id,
            intents,
            local_result.get("confidence", 0) if local_result else 0,
        )
        reply = None
        # 提问/信息查询类消息（如"上海天气"被误判成 search_file）不执行
        # 本地动作，直接交给云端回答
        if not is_question_like(question_text):
            try:
                from .intent import execute_local_action

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
        else:
            logger.info(
                "消息疑似提问，跳过本地动作交给云端 session=%s question=%r",
                session_id,
                question_text[:50],
            )

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

    # options 卡片遵循提示：拼在本次模型输入末尾（意图分类之后，不落库）
    if output_hint and input_messages and input_messages[-1].type == "human":
        from langchain_core.messages import HumanMessage as _HintHuman

        last = input_messages[-1]
        input_messages[-1] = _HintHuman(
            content=_content_text(last.content) + "\n" + output_hint,
            id=last.id,
        )

    graph_input: Any = {"messages": input_messages}
    final_state: dict[str, Any] | None = None
    think_by_id: dict[str, str] = {}
    partial_think: list[str] = []
    partial_content: list[str] = []
    partial_saved = False

    async def _persist_partial_once() -> None:
        """持久化本次已生成的部分输出（幂等：只落库一次）。

        手动停止时前端会先 abort SSE 连接、再调 cancel 接口——连接断开
        会让本生成器在 yield 点被 CancelledError/GeneratorExit 拆掉，
        走不到下方 cancel_event 检查。这里同时覆盖优雅取消与异常退出
        两条路径，保证部分内容不丢。
        """
        nonlocal partial_saved
        content = "".join(partial_content)
        think = "".join(partial_think)
        if partial_saved or (not content and not think):
            return
        await asyncio.to_thread(db.abort_todos, session_id)
        await _persist_partial_generation(session_id, content, think)
        partial_saved = True

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
                    await _persist_partial_once()
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
                                pending["event"].wait(),
                                approval_timeout_seconds(settings),
                            )
                            allowed = bool(pending["allowed"])
                        except asyncio.TimeoutError:
                            allowed = False
                        finally:
                            remove_terminal_decision(session_id)
                        if payload.get("type") == "ask_user":
                            # ask_user：resume 值即用户答案（180s 超时 answer 为空，
                            # 由 execution 侧降级为"按最佳判断继续"）；不参与
                            # approve/reject 与 action_requests 的组装。
                            resume_values[item.id] = {
                                "allowed": True,
                                "answer": pending.get("answer"),
                            }
                            continue
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
        # 撞上限时已流出的部分内容必须落库——此前只 abort_todos，
        # 用户做了大半的工作在刷新后丢失（与手动停止断连同款漏洞）。
        await _persist_partial_once()
        yield error_event(
            "recursion_limit",
            "任务步骤过多，已停止。已生成的内容已保留，回复「继续」可接着当前进度做；也可以把任务拆分成更小的请求。",
            message_key="tool.recursionLimit",
        )
        return
    except (asyncio.CancelledError, GeneratorExit):
        # 客户端断开（手动停止先 abort 连接）时生成器在 yield 点被拆掉，
        # 走不到循环内的 cancel_event 检查——这里兜底持久化部分输出。
        # 注意：GeneratorExit 语境下不允许再 yield，持久化后必须原样抛出。
        try:
            await _persist_partial_once()
        except Exception:  # noqa: BLE001 — 清理路径尽力而为，不掩盖原异常
            logger.exception(
                "persist partial generation failed session=%s", session_id
            )
        raise
    except Exception:
        # 模型/工具异常（如 429 限流）：已流出的内容同样必须落库——与
        # GraphRecursionError、断连同款兜底，否则前端已渲染的内容刷新即丢。
        # 工具轮次从 checkpointer 线程快照捞（异常时 astream 拿不到终态，
        # 快照保留最后一个完成的 super-step）；快照中已持久化的完整文本是
        # 流式累积内容的词法前缀（同序、完整消息），只补尾部避免文本双写。
        # 异常原样上抛，由 chat 层发 server_error 事件，此处只负责不丢数据。
        persisted_prefix = ""
        try:
            from langchain_core.messages import AIMessage

            state = await agent.aget_state(config)
            state_messages = (state.values or {}).get("messages") or []
            await asyncio.to_thread(
                _persist_new_messages, session_id, input_messages, state_messages, {}
            )
            persisted_prefix = "".join(
                _content_text(message.content)
                for message in state_messages
                if isinstance(message, AIMessage) and not message.tool_calls
            )
        except Exception:  # noqa: BLE001 — 快照失败退回纯流式部分持久化
            logger.exception(
                "persist checkpointed tool turns failed session=%s", session_id
            )
        content = "".join(partial_content)
        tail = (
            content[len(persisted_prefix):]
            if persisted_prefix and content.startswith(persisted_prefix)
            else content
        )
        if tail or partial_think:
            try:
                await asyncio.to_thread(db.abort_todos, session_id)
                await _persist_partial_generation(
                    session_id, tail, "".join(partial_think)
                )
            except Exception:  # noqa: BLE001 — 清理路径尽力而为
                logger.exception(
                    "persist partial generation failed session=%s", session_id
                )
        raise

    if final_state is None:
        await asyncio.to_thread(db.abort_todos, session_id)
        yield error_event(
            "agent_error",
            "Agent 未返回结果",
            message_key="tool.agentError",
        )
        return

    messages = final_state.get("messages") or []
    _sync_todos_from_state(session_id, final_state)
    # run 正常结束：终态收敛（running→done、pending→skipped）并推全量计划。
    # 修复 D1 的前端半边——DB 收敛后前端实时同步，刷新不再归零。
    items, settled = await asyncio.to_thread(db.settle_todos, session_id)
    if items:
        yield sse_event(
            "plan_sync",
            {
                "items": [
                    {
                        "id": item["id"],
                        "index": item["index"],
                        "title": item["title"],
                        "status": item["status"],
                        "result": item["result"],
                    }
                    for item in items
                ],
                "settled": settled,
            },
        )

    # 演示模式（未配置 API Key，走 Mock 模型）：在回答后追加引导提示，
    # 提示用户安装免费本地模型或配置 API Key（追加进消息内容，持久化与
    # SSE 一致）
    try:
        from ..llm import MockChatModel
        from langchain_core.messages import AIMessage

        if isinstance(llm, MockChatModel):
            for message in reversed(messages):
                if isinstance(message, AIMessage) and (message.content or ""):
                    notice = (
                        "\n\n---\n> ⚠️ 当前为演示模式回答（未配置 API Key）。"
                        "可安装免费本地模型离线使用，或在设置中配置 API Key。"
                    )
                    message.content = f"{message.content}{notice}"
                    break
    except Exception:  # noqa: BLE001
        pass

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
                int((_time.monotonic() - turn_started) * 1000),
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
            "unused_mentions": _unused_mention_skills(
                messages, ctx.mention_skills
            ),
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
        from .state import compact_session

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
