from __future__ import annotations

import json
from typing import Any, AsyncIterator

from .config import settings_store, workspace_dir
from .llm import DeepSeekLLM, MockLLM
from .sse import sse_event
from .tools.base import ToolExecutionError
from .tools.registry import get_tool, registry


SYSTEM_PROMPT = """你是 AI Workspace，一个本地优先的桌面 AI 助手。
你可以回答问题，也可以使用本地工具生成文件。生成文件前先向用户简要说明计划，
再选择最合适的工具。工具结果要结合到最终回答中，并告诉用户下载链接。
回答使用简洁的 Markdown，不输出与任务无关的内容。"""


def _build_llm() -> DeepSeekLLM | MockLLM:
    settings = settings_store.load()
    provider = settings.get("provider") or "auto"
    if provider == "mock":
        return MockLLM()
    if provider == "auto" and not settings.get("api_key"):
        return MockLLM()
    return DeepSeekLLM()


async def run_agent(
    session_id: str,
    history: list[dict[str, Any]],
    think: bool,
) -> AsyncIterator[str]:
    settings = settings_store.load()
    context_limit = int(settings.get("context_limit") or 20)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]
    messages.extend(history[-context_limit:])
    llm = _build_llm()
    tool_schemas = registry.openai_schema()

    for turn in range(4):
        tool_calls: dict[int, dict[str, str]] = {}
        assistant_content = ""
        think_content = ""
        async for event in llm.stream(
            messages, tool_schemas if turn == 0 else None, think
        ):
            event_type = event.get("type")
            if event_type == "think":
                think_content += event.get("content", "")
                yield sse_event("think", {"content": event.get("content", "")})
            elif event_type == "message":
                assistant_content += event.get("content", "")
                yield sse_event("message", {"content": event.get("content", "")})
            elif event_type == "tool_call":
                index = int(event.get("index") or 0)
                call = tool_calls.setdefault(
                    index,
                    {"id": "", "name": "", "arguments": ""},
                )
                if event.get("id"):
                    call["id"] = event["id"]
                if event.get("name"):
                    call["name"] = event["name"]
                call["arguments"] += event.get("arguments") or ""

        if not tool_calls:
            from . import db

            message = db.add_message(session_id, "assistant", assistant_content)
            order = 0
            if think_content:
                db.add_message_part(
                    message["id"], "think", think_content, order=order
                )
                order += 1
            yield sse_event(
                "done",
                {
                    "message": "回答完成",
                    "content": assistant_content,
                },
            )
            return

        assistant_tool_calls = []
        tool_results: list[tuple[str, str]] = []
        for index, call in sorted(tool_calls.items()):
            name = call["name"]
            call_id = call["id"] or f"call_{index}"
            try:
                arguments = json.loads(call["arguments"] or "{}")
            except json.JSONDecodeError:
                arguments = {"_raw": call["arguments"]}
            adapter = get_tool(name)
            if adapter is None:
                tool_message = json.dumps({"error": f"未知工具: {name}"})
                yield sse_event(
                    "tool",
                    {
                        "tool": name,
                        "status": "error",
                        "message": f"未知工具: {name}",
                    },
                )
                tool_results.append((call_id, tool_message))
            else:
                yield sse_event(
                    "tool",
                    {
                        "tool": name,
                        "status": "running",
                        "message": f"正在调用 {name}",
                    },
                )
                tool_message = await _execute_tool(
                    session_id, adapter, name, arguments
                )
                parsed_result = json.loads(tool_message)
                yield sse_event(
                    "tool",
                    {
                        "tool": name,
                        "status": "done" if parsed_result.get("success") else "error",
                        "message": parsed_result.get("message", "执行完成"),
                        "result": parsed_result,
                    },
                )
                tool_results.append((call_id, tool_message))
            assistant_tool_calls.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": call["arguments"] or "{}"},
                }
            )

        messages.append(
            {
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": assistant_tool_calls,
            }
        )
        for call_id, tool_message in tool_results:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": tool_message,
                }
            )

    raise RuntimeError("工具调用次数超过限制")


async def _execute_tool(
    session_id: str, adapter: Any, name: str, arguments: dict[str, Any]
) -> str:
    from . import db

    run = db.add_tool_run(session_id, name, "start", arguments)
    try:
        result = await adapter.run(workspace_dir(), arguments)
        output = result.as_dict()
        db.update_tool_run(run["id"], "done", output)
        return json.dumps(output, ensure_ascii=False)
    except ToolExecutionError as exc:
        output = {"success": False, "message": str(exc)}
        db.update_tool_run(run["id"], "error", output)
        return json.dumps(output, ensure_ascii=False)
