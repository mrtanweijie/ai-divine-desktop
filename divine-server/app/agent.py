from __future__ import annotations

import json
from typing import Any, AsyncIterator

from .api.terminal import terminal_command_policy, wait_for_terminal_decision
from .config import settings_store, workspace_dir
from .llm import ChatDeepSeekProvider, MockLLM
from .sse import sse_event
from .tools.base import ToolExecutionError
from .tools.registry import get_tool, registry


SYSTEM_PROMPT = """你是 AI Divine，一个本地优先的桌面 AI 助手。
你可以回答问题，也可以使用本地工具生成文件。生成文件前先向用户简要说明计划，
再选择最合适的工具。工具结果要结合到最终回答中，并告诉用户下载链接。
不要输出 XML 或伪代码形式的工具调用；需要生成笔记时直接调用 notes 工具。
用户要求保存时，如果未明确指定格式，默认只生成 Markdown 笔记，不要同时生成多个格式的文件；
只有用户明确要求两种或更多格式时才生成多个。
当用户附加图片时，只能调用 read_image 分析当前消息中列出的图片附件，并使用该附件
给出的图片本地路径；不要使用历史消息中的图片路径，也不要对非图片文件调用 read_image。
read_image 返回的 content 就是图片识别结果，请基于它回答用户。
回答使用简洁的 Markdown，不输出与任务无关的内容。
重要规则：不要在正文中输出 download_url、/api/files/ 或 http://localhost 等文件链接；
生成文件后只需说明文件名和内容概要，文件下载/打开由前端工具卡片展示。
读取文件内容必须使用 read_file、word_document 等专用工具；
读取 Excel 必须使用 read_file（不要使用 spreadsheet，spreadsheet 只能生成 Excel）；
禁止用 terminal 执行 cat、python、openpyxl、find 等命令来读取或分析文件。
terminal 只能用于系统操作，例如安装依赖、运行命令、管理进程或用户明确要求的终端命令。"""

TOOL_ALIASES = {
    "generate_note": "notes",
    "generate_notes": "notes",
}


def _build_llm() -> ChatDeepSeekProvider | MockLLM:
    settings = settings_store.load()
    provider = settings.get("provider") or "auto"
    if provider == "mock":
        return MockLLM()
    if provider == "langchain":
        return ChatDeepSeekProvider()
    if provider == "auto" and not settings.get("api_key"):
        return MockLLM()
    return ChatDeepSeekProvider()


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

    for turn in range(8):
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
                adapter = (
                    get_tool(TOOL_ALIASES.get(name, ""))
                    if name in TOOL_ALIASES
                    else None
                )
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
                is_terminal = name == "terminal"
                command = str(arguments.get("command") or "")
                policy = (
                    terminal_command_policy(command) if is_terminal else "safe"
                )
                if is_terminal and policy == "block":
                    tool_message = json.dumps(
                        {"error": "已阻止危险命令", "command": command},
                        ensure_ascii=False,
                    )
                    yield sse_event(
                        "tool",
                        {
                            "tool": name,
                            "status": "error",
                            "message": "已阻止危险命令",
                            "command": command,
                            "result": {"command": command},
                            "session_id": session_id,
                        },
                    )
                    tool_results.append((call_id, tool_message))
                elif is_terminal and policy == "confirm":
                    yield sse_event(
                        "tool",
                        {
                            "tool": name,
                            "status": "confirm",
                            "message": "等待用户确认",
                            "command": command,
                            "session_id": session_id,
                        },
                    )
                    allowed = await wait_for_terminal_decision(
                        session_id, command
                    )
                    if not allowed:
                        tool_message = json.dumps(
                            {"error": "用户拒绝执行", "command": command},
                            ensure_ascii=False,
                        )
                        yield sse_event(
                            "tool",
                            {
                                "tool": name,
                                "status": "error",
                                "message": "用户拒绝执行",
                                "command": command,
                                "result": {"command": command},
                                "session_id": session_id,
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
                                "command": command,
                                "session_id": session_id,
                            },
                        )
                        output = await _execute_tool(
                            session_id, adapter, name, arguments
                        )
                        tool_message = output.get("content") or json.dumps(
                            output, ensure_ascii=False
                        )
                        yield sse_event(
                            "tool",
                            {
                                "tool": name,
                                "status": "done" if output.get("success") else "error",
                                "message": output.get("message", "执行完成"),
                                "command": command,
                                "result": output,
                                "session_id": session_id,
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
                    output = await _execute_tool(
                        session_id, adapter, name, arguments
                    )
                    tool_message = output.get("content") or json.dumps(
                        output, ensure_ascii=False
                    )
                    payload: dict[str, Any] = {
                        "tool": name,
                        "status": "done" if output.get("success") else "error",
                        "message": output.get("message", "执行完成"),
                        "result": output,
                    }
                    if is_terminal:
                        payload["command"] = command
                    yield sse_event("tool", payload)
                    tool_results.append((call_id, tool_message))
            assistant_tool_calls.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": call["arguments"] or "{}"},
                }
            )

        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "content": assistant_content,
            "tool_calls": assistant_tool_calls,
        }
        if think_content:
            assistant_message["reasoning_content"] = think_content
        messages.append(assistant_message)
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
) -> dict[str, Any]:
    from . import db

    run = db.add_tool_run(session_id, name, "start", arguments)
    try:
        result = await adapter.run(workspace_dir(), arguments)
        output = result.as_dict()
        db.update_tool_run(run["id"], "done", output)
        return output
    except ToolExecutionError as exc:
        output = {"success": False, "message": str(exc)}
        db.update_tool_run(run["id"], "error", output)
        return output
