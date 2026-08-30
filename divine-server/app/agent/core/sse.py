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
                        await queue.put(
                            (
                                "sse",
                                sse_event("think", {"content": event["content"]}),
                            )
                        )
                    else:
                        text_parts.append(event["content"])
                        await queue.put(
                            (
                                "sse",
                                sse_event("message", {"content": event["content"]}),
                            )
                        )
            for event in think_processor.flush():
                if event["type"] == "think":
                    reasoning_parts.append(event["content"])
                    await queue.put(
                        ("sse", sse_event("think", {"content": event["content"]}))
                    )
                else:
                    text_parts.append(event["content"])
                    await queue.put(
                        ("sse", sse_event("message", {"content": event["content"]}))
                    )
            return
        async for delta in message.text:
            for event in react_processor.push(delta):
                if event["type"] == "think":
                    reasoning_parts.append(event["content"])
                    await queue.put(
                        ("sse", sse_event("think", {"content": event["content"]}))
                    )
                else:
                    text_parts.append(event["content"])
                    await queue.put(
                        ("sse", sse_event("message", {"content": event["content"]}))
                    )
        for event in react_processor.flush():
            if event["type"] == "think":
                reasoning_parts.append(event["content"])
                await queue.put(
                    ("sse", sse_event("think", {"content": event["content"]}))
                )
            else:
                text_parts.append(event["content"])
                await queue.put(
                    ("sse", sse_event("message", {"content": event["content"]}))
                )

    async def drain_reasoning() -> None:
        async for delta in message.reasoning:
            reasoning_parts.append(delta)
            await queue.put(
                ("sse", sse_event("think", {"content": delta}))
            )

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
