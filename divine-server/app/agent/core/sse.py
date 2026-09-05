"""SSE formatting and agent stream consumption."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from langgraph.stream.transformers import CustomTransformer

from ...sse import sse_event

def _custom_sse(payload: Any) -> str:
    if not isinstance(payload, dict):
        return sse_event("tool", {"message": str(payload)})
    event_name = payload.get("event", "tool")
    data = {key: value for key, value in payload.items() if key != "event"}
    return sse_event(event_name, data)

def _interrupt_sse(
    payload: dict[str, Any], default_session_id: str = ""
) -> str:
    kind = payload.get("type")
    session_id = payload.get("session_id") or default_session_id
    if kind == "plan_choice":
        return sse_event(
            "tool",
            {
                "tool": "plan_choice",
                "status": "confirm",
                "message": payload.get("message", "执行任务前是否先出一份方案？"),
                "messageKey": "tool.planChoiceText",
                "messageParams": {},
                "confirm_type": "plan_choice",
                "call_id": payload.get("call_id", ""),
                "session_id": session_id,
            },
        )
    if kind == "ask_user":
        return sse_event(
            "tool",
            {
                "tool": "ask_user",
                "status": "confirm",
                "message": payload.get("question", "需要你补充信息"),
                "confirm_type": "ask_user",
                "question": payload.get("question", ""),
                "options": payload.get("options") or [],
                "input_type": payload.get("input_type") or "text",
                "call_id": payload.get("call_id", ""),
                "session_id": session_id,
            },
        )
    if kind == "plan":
        return (
            sse_event("plan", {"items": payload.get("todos") or []})
            + sse_event(
                "tool",
                {
                    "tool": "create_plan",
                    "status": "confirm",
                    "message": payload.get("message", "计划已创建，是否开始执行？"),
                    "messageKey": "tool.planConfirmText",
                    "messageParams": {},
                    "confirm_type": "plan",
                    "call_id": payload.get("call_id", ""),
                    "session_id": session_id,
                },
            )
        )
    if kind == "external_file":
        return sse_event(
            "tool",
            {
                "tool": payload.get("tool") or "tool",
                "status": "confirm",
                "message": payload.get("message", "外部路径需要确认"),
                "messageKey": "tool.externalFileConfirm",
                "messageParams": {},
                "confirm_type": "external_file",
                "paths": payload.get("paths") or [],
                "call_id": payload.get("call_id", ""),
                "session_id": session_id,
            },
        )
    if kind == "terminal":
        return sse_event(
            "tool",
            {
                "tool": payload.get("tool") or "terminal",
                "status": "confirm",
                "confirm_type": "terminal",
                "message": payload.get("message", "等待用户确认"),
                "messageKey": "tool.terminalWaitText",
                "messageParams": {},
                "command": payload.get("command") or "",
                "call_id": payload.get("call_id", ""),
                "session_id": session_id,
            },
        )
    if kind == "git":
        # git_commit / git_revert 审批：必须携带 confirm_type 与 command，
        # 否则前端确认区匹配不到任何分支、不渲染按钮，用户无从回应，
        # Agent 只能等到超时被拒（git 中断无 UI 卡死的根因）。
        return sse_event(
            "tool",
            {
                "tool": payload.get("tool") or "git_commit",
                "status": "confirm",
                "confirm_type": "git",
                "message": payload.get("message", "确认执行 git 写操作？"),
                "messageKey": "tool.gitConfirmWait",
                "messageParams": {},
                "command": payload.get("command") or "",
                "call_id": payload.get("call_id", ""),
                "session_id": session_id,
            },
        )
    if kind == "write_calendar":
        return sse_event(
            "tool",
            {
                "tool": "schedule_task",
                "status": "confirm",
                "confirm_type": "write_calendar",
                "message": payload.get("message", "创建提醒后是否同时写入日程？"),
                "messageKey": "tool.calendarConfirmText",
                "messageParams": {},
                "call_id": payload.get("call_id", ""),
                "session_id": session_id,
            },
        )
    if kind == "skill_migrate":
        return sse_event(
            "tool",
            {
                "tool": "migrate_skill",
                "status": "confirm",
                "confirm_type": "skill_migrate",
                "message": payload.get("message", "等待用户确认技能迁移"),
                "messageKey": "tool.skillMigrateWait",
                "messageParams": {
                    "name": (payload.get("skill") or {}).get("name", ""),
                    "target": payload.get("target") or "project",
                },
                "skill_migrate": payload.get("skill") or {},
                "target": payload.get("target") or "project",
                "call_id": payload.get("call_id", ""),
                "session_id": session_id,
            },
        )
    if kind == "skill_migrate_batch":
        return sse_event(
            "tool",
            {
                "tool": "migrate_skills",
                "status": "confirm",
                "confirm_type": "skill_migrate_batch",
                "message": payload.get("message", "等待用户确认批量技能迁移"),
                "messageKey": "tool.batchMigrateWait",
                "messageParams": {
                    "count": len(payload.get("skills") or []),
                },
                "skill_migrations": payload.get("skills") or [],
                "target": payload.get("target") or "project",
                "call_id": payload.get("call_id", ""),
                "session_id": session_id,
            },
        )
    if kind == "skill_install":
        return sse_event(
            "tool",
            {
                "tool": "install_skill",
                "status": "confirm",
                "confirm_type": "skill_install",
                "message": payload.get("message", "等待用户确认技能安装"),
                "messageKey": "tool.skillInstallWait",
                "messageParams": {
                    "repo": (payload.get("repo_preview") or {}).get(
                        "repo", ""
                    ),
                },
                "skill_install": payload.get("repo_preview") or {},
                "target": payload.get("target") or "project",
                "call_id": payload.get("call_id", ""),
                "session_id": session_id,
            },
        )
    if kind == "subagents_write":
        return sse_event(
            "tool",
            {
                "tool": "run_subagents",
                "status": "confirm",
                "confirm_type": "subagents_write",
                "message": payload.get("message", "等待用户确认并行写任务"),
                "messageKey": "tool.subagentsWriteWait",
                "messageParams": {
                    "count": len((payload.get("subagent_write") or {}).get("tasks") or []),
                },
                "subagent_write": payload.get("subagent_write") or {},
                "call_id": payload.get("call_id", ""),
                "session_id": session_id,
            },
        )
    if payload.get("action_requests"):
        plan_items: list[dict[str, str]] = []
        for action in payload["action_requests"]:
            if action.get("name") == "write_todos":
                for index, todo in enumerate(
                    (action.get("args") or {}).get("todos") or []
                ):
                    content = str(todo.get("content") or "").strip()
                    if content:
                        plan_items.append(
                            {
                                "id": str(index),
                                "index": str(index),
                                "title": content,
                                "status": "pending",
                            }
                        )
        confirm_event = sse_event(
            "tool",
            {
                "tool": "write_todos",
                "status": "confirm",
                "message": "等待用户确认",
                "messageKey": "tool.planConfirmText",
                "messageParams": {},
                "confirm_type": "plan",
                "call_id": payload.get("call_id", ""),
                "session_id": session_id,
            },
        )
        if plan_items:
            return sse_event("plan", {"items": plan_items}) + confirm_event
        return confirm_event
    return sse_event(
        "tool",
        {
            "tool": payload.get("tool") or "tool",
            "status": "confirm",
            "message": payload.get("message", "等待用户确认"),
            "messageKey": "tool.waitingUserConfirm",
            "messageParams": {},
            "call_id": payload.get("call_id", ""),
            "session_id": session_id,
        },
    )

def _interrupt_prompt(payload: dict[str, Any]) -> str:
    if payload.get("action_requests"):
        return "是否执行计划？"
    if payload.get("type") == "terminal":
        return str(payload.get("command") or "等待用户确认")
    if payload.get("type") == "external_file":
        paths = payload.get("paths") or []
        return str(paths[0] if paths else "外部路径需要确认")
    return str(payload.get("message") or "等待用户确认")

# B6（流式渲染优化）：文本事件攒批窗口。相邻同类型 think/message 帧
# 合并后再入队，减少本地 IPC 帧数；类型切换点立即 flush，保证
# 思考块与正文的边界不被错误合并。
_TEXT_FLUSH_INTERVAL = 0.05
_TEXT_FLUSH_CHARS = 96


def _make_text_emitter(queue: asyncio.Queue[tuple[str, Any]]):
    """返回 (emit, flush)：按类型攒批文本事件。

    只合并相邻同类型帧（flush 后才切换类型），事件相对顺序不变。
    done/tool 等其他事件由各自路径入队；每条 message 的文本先于
    工具事件流完（工具执行需要完整消息），故无跨事件交错。
    """
    batch_type: str | None = None
    batch_parts: list[str] = []
    batch_chars = 0
    loop = asyncio.get_running_loop()
    batch_started = 0.0

    async def flush() -> None:
        nonlocal batch_type, batch_parts, batch_chars
        if batch_type is not None and batch_parts:
            await queue.put(
                ("sse", sse_event(batch_type, {"content": "".join(batch_parts)}))
            )
        batch_type = None
        batch_parts = []
        batch_chars = 0

    async def emit(event_type: str, content: str) -> None:
        nonlocal batch_type, batch_started, batch_chars
        if not content:
            return
        if batch_type != event_type:
            await flush()
            batch_type = event_type
            batch_started = loop.time()
        batch_parts.append(content)
        batch_chars += len(content)
        if (
            loop.time() - batch_started >= _TEXT_FLUSH_INTERVAL
            or batch_chars >= _TEXT_FLUSH_CHARS
        ):
            await flush()

    return emit, flush


async def _consume_message(
    message: Any,
    queue: asyncio.Queue[tuple[str, Any]],
    react: bool = False,
) -> tuple[Any, str]:
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    react_processor = None
    if react:
        from ..tools.react import ReActStreamProcessor

        react_processor = ReActStreamProcessor()

    emit, flush_text_batch = _make_text_emitter(queue)

    async def drain_text() -> None:
        if react_processor is None:
            # 普通文本流：用 <think> 标签分离器把推理模型的思考块
            # （如 MiniMax-M3、GLM-5.x）拆成 think 事件，正文保持 message。
            from ...llm.think_tags import ThinkTagProcessor

            think_processor = ThinkTagProcessor()
            async for delta in message.text:
                for event in think_processor.push(delta):
                    if event["type"] == "think":
                        reasoning_parts.append(event["content"])
                        await emit("think", event["content"])
                    else:
                        text_parts.append(event["content"])
                        await emit("message", event["content"])
            for event in think_processor.flush():
                if event["type"] == "think":
                    reasoning_parts.append(event["content"])
                    await emit("think", event["content"])
                else:
                    text_parts.append(event["content"])
                    await emit("message", event["content"])
            await flush_text_batch()
            return
        async for delta in message.text:
            for event in react_processor.push(delta):
                if event["type"] == "think":
                    reasoning_parts.append(event["content"])
                    await emit("think", event["content"])
                else:
                    text_parts.append(event["content"])
                    await emit("message", event["content"])
        for event in react_processor.flush():
            if event["type"] == "think":
                reasoning_parts.append(event["content"])
                await emit("think", event["content"])
            else:
                text_parts.append(event["content"])
                await emit("message", event["content"])
        await flush_text_batch()

    async def drain_reasoning() -> None:
        async for delta in message.reasoning:
            reasoning_parts.append(delta)
            await emit("think", delta)
        await flush_text_batch()

    output_future = asyncio.ensure_future(message.output)
    await asyncio.gather(drain_text(), drain_reasoning())
    if reasoning_parts:
        await queue.put(("sse", sse_event("think_done", {})))
    output = await output_future
    # 清理消息正文里的 <think> 块（推理模型内联思考），避免正文重复显示。
    try:
        content = getattr(output, "content", None)
        if isinstance(content, str) and "<think>" in content:
            from ...llm.think_tags import strip_think_tags

            output = output.model_copy(update={"content": strip_think_tags(content)})
    except Exception:  # noqa: BLE001 — 清理失败不影响主流程
        pass
    return output, "".join(reasoning_parts)

async def _stream_agent_run(
    agent: Any,
    graph_input: Any,
    config: dict[str, Any],
    react: bool = False,
) -> AsyncIterator[tuple[str, Any]]:
    run = await agent.astream_events(
        graph_input,
        config,
        version="v3",
        transformers=[CustomTransformer],
    )
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
    think_by_id: dict[str, str] = {}

    async def consume_messages() -> None:
        try:
            async for message in run.messages:
                output, reasoning = await _consume_message(
                    message, queue, react=react
                )
                message_id = getattr(output, "id", None)
                if message_id and reasoning:
                    think_by_id[message_id] = (
                        think_by_id.get(message_id, "") + reasoning
                    )
        finally:
            await queue.put(("task_done", "messages"))

    async def consume_custom() -> None:
        try:
            async for payload in run.custom:
                await queue.put(("sse", _custom_sse(payload)))
        finally:
            await queue.put(("task_done", "custom"))

    tasks = [
        asyncio.create_task(consume_messages()),
        asyncio.create_task(consume_custom()),
    ]
    try:
        done_count = 0
        while done_count < 2:
            kind, data = await queue.get()
            if kind == "task_done":
                done_count += 1
            else:
                yield kind, data
        interrupted = await run.interrupted()
        if interrupted:
            interrupts = await run.interrupts()
            yield "interrupts", interrupts
        else:
            final_state = await run.output()
            yield "final_state", (final_state, think_by_id)
    finally:
        for task in tasks:
            task.cancel()
        await run.abort()
