from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncIterator

from . import db
from .api.terminal import terminal_command_policy, wait_for_terminal_decision
from .config import settings_store
from .llm import ChatDeepSeekProvider, DeepSeekLLM, MockLLM
from .rag_store import (
    index_workspace as rag_index_workspace,
    search_workspace as rag_search_workspace,
)
from .sse import error_event, sse_event
from .tools.base import ToolExecutionError
from .tools.registry import get_tool, registry

logger = logging.getLogger("divine.agent")


def _summarize_arguments(arguments: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in arguments.items():
        if isinstance(value, str) and len(value) > 80:
            parts.append(f"{key}={len(value)}chars")
        else:
            parts.append(f"{key}={value!r}")
    return ", ".join(parts)[:500]


_PLAN_STATUS_LABELS = {
    "pending": "待办",
    "running": "执行中",
    "done": "完成",
    "error": "失败",
    "skipped": "跳过",
}

_RAG_KEYWORDS = (
    "笔记",
    "文件",
    "文档",
    "目录",
    "资料",
    "章节",
    "大纲",
    "小说",
    "续写",
    "内容",
    "方案",
    "工作区",
    "里面",
    "之前",
)


def _auto_rag_context(
    history: list[dict[str, Any]], workspace: Any
) -> str | None:
    question = next(
        (
            message.get("content", "")
            for message in reversed(history)
            if message.get("role") == "user"
        ),
        "",
    )
    question = (question or "").strip()
    if not question:
        return None
    try:
        results = rag_search_workspace(workspace, question, 3)
        if not results and any(
            keyword in question for keyword in _RAG_KEYWORDS
        ):
            rag_index_workspace(workspace)
            results = rag_search_workspace(workspace, question, 3)
    except Exception:
        return None
    if not results:
        return None
    blocks = [
        f"[{result['file_path']}]\n{result['snippet']}"
        for result in results
    ]
    return (
        "以下是工作区本地资料检索结果：\n\n"
        + "\n\n".join(blocks)
        + "\n\n请优先结合这些资料回答用户问题。"
    )


def _plan_progress(todos: list[dict[str, Any]]) -> str:
    if not todos:
        return ""
    total = len(todos)
    done = sum(1 for todo in todos if todo["status"] == "done")
    lines = [f"当前计划进度：{done}/{total}"]
    for index, todo in enumerate(todos, start=1):
        label = _PLAN_STATUS_LABELS.get(todo["status"], todo["status"])
        lines.append(f"{index}. [{label}] {todo['title']}")
    return "\n".join(lines)


def _claim_next_todo(
    session_id: str, todos: list[dict[str, Any]]
) -> dict[str, Any] | None:
    for todo in todos:
        if todo["status"] == "pending":
            todo["status"] = "running"
            db.update_todo_status(todo["id"], "running")
            return todo
    return None


def _finish_todo(
    todo: dict[str, Any] | None, success: bool, message: str = ""
) -> None:
    if todo is None:
        return
    status = "done" if success else "error"
    todo["status"] = status
    db.update_todo_status(todo["id"], status, (message or "")[:500])


def _todo_update_event(todo: dict[str, Any]) -> str:
    return sse_event(
        "todo_update",
        {"id": todo["id"], "status": todo["status"]},
    )


SYSTEM_PROMPT = """你是 AI Divine，一个本地优先的桌面 AI 助手。
你可以回答问题，也可以使用本地工具生成文件。生成文件前先向用户简要说明计划，
再选择最合适的工具。工具结果要结合到最终回答中，并告诉用户下载链接。
面对需要多步执行的复杂任务，先调用 create_plan 列出待办事项，再按待办顺序逐项执行；
不要跳过未完成事项，也不要重复执行已完成事项。
执行需要修改文件、生成文件或运行命令的任务前，先询问用户是否要出一份方案；
用户选择先出方案后，先调用 create_plan，不要直接执行其他工具。
不要输出 XML 或伪代码形式的工具调用；需要生成笔记时直接调用 notes 工具。
调用 notes 时必须提供明确、具体的标题，不要使用“未命名笔记”作为标题。
生成笔记时若用户指定目录，使用 notes 的 path 参数传入 workspace 内相对目录，默认保存在 notes。
用户要求保存时，如果未明确指定格式，默认只生成 Markdown 笔记，不要同时生成多个格式的文件；
只有用户明确要求两种或更多格式时才生成多个。
当用户附加图片时，只能调用 read_image 分析当前消息中列出的图片附件，并使用该附件
给出的图片本地路径；不要使用历史消息中的图片路径，也不要对非图片文件调用 read_image。
read_image 返回的 content 就是图片识别结果，请基于它回答用户。
回答使用简洁的 Markdown，不输出与任务无关的内容。
重要规则：不要在正文中输出 download_url、/api/files/ 或 http://localhost 等文件链接；
生成文件后只需说明文件名和内容概要，文件下载/打开由前端工具卡片展示。
只能调用本次请求提供的工具，不要杜撰未提供的工具名。
查找或列出工作区文件使用 search_files；搜索完文件后，读取具体内容再使用 read_file。
查看目录结构使用 directory_tree；缩放图片使用 image_resize；拆分合并 PDF 使用 pdf_split_merge；
只读查询数据库使用 sqlite_query；数学计算使用 calculator；剪贴板操作使用 clipboard。
安排提醒或定时任务时调用 schedule_task；创建提醒后不要直接写日程，系统会询问用户是否写入日程，
用户确认后再调用 write_calendar，并把 task_id 传给 write_calendar。
用户要求记录日程/日历事件时调用 write_calendar，可单独使用，从用户输入中识别标题和起止时间。
本地资料检索使用 rag_index 建立索引、rag_search 检索相关内容。
读取文件内容必须使用 read_file、word_document 等专用工具；
读取 Excel 必须使用 read_file（不要使用 spreadsheet，spreadsheet 只能生成 Excel）；
默认禁止用 terminal 执行 cat、python、openpyxl、find 等命令来读取或分析文件；
如果用户明确要求，可提交终端确认后执行。
读取工作区外的本地文件或图片需要用户确认。
terminal 只能用于系统操作，例如安装依赖、运行命令、管理进程或用户明确要求的终端命令。"""

TOOL_ALIASES = {
    "generate_note": "notes",
    "generate_notes": "notes",
}

_READ_ONLY_TOOLS = {
    "read_file",
    "read_image",
    "search_files",
    "directory_tree",
    "rag_search",
    "sqlite_query",
    "calculator",
    "web_fetch",
}

_NO_PLAN_TOOLS = {
    "schedule_task",
    "write_calendar",
}

MAX_TOOL_TURNS = 32


def _build_llm() -> ChatDeepSeekProvider | MockLLM:
    settings = settings_store.load()
    provider = settings.get("provider") or "auto"
    if provider == "mock":
        return MockLLM()
    if provider == "langchain":
        return ChatDeepSeekProvider()
    if provider == "auto" and not settings.get("api_key"):
        return MockLLM()
    return DeepSeekLLM()


async def run_agent(
    session_id: str,
    history: list[dict[str, Any]],
    think: bool,
    workspace: Any,
    approval_mode: str = "ask",
) -> AsyncIterator[str]:
    settings = settings_store.load()
    context_limit = int(settings.get("context_limit") or 20)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "system",
            "content": f"当前会话所属项目工作目录：{workspace}\n"
            "请以该目录作为方案设计和文件操作的工作区。",
        },
    ]
    messages.extend(history[-context_limit:])
    todos = db.list_todos(session_id)
    plan_message: dict[str, Any] | None = None
    system_count = 2
    if todos:
        plan_message = {"role": "system", "content": _plan_progress(todos)}
        messages.insert(system_count, plan_message)
    rag_context = _auto_rag_context(history, workspace)
    if rag_context:
        insert_at = system_count + (1 if plan_message is not None else 0)
        messages.insert(insert_at, {"role": "system", "content": rag_context})
        logger.info(
            "auto rag context session=%s chars=%d",
            session_id,
            len(rag_context),
        )
    llm = _build_llm()
    tool_schemas = registry.openai_schema()
    unknown_tool_counts: dict[str, int] = {}
    repeated_calls: dict[str, int] = {}
    plan_choice_resolved = False
    logger.info(
        "agent start session=%s history=%d",
        session_id,
        len(history),
    )

    for turn in range(MAX_TOOL_TURNS):
        calendar_pending: dict[str, Any] | None = None
        if plan_message is not None:
            plan_message["content"] = _plan_progress(todos)
        logger.info(
            "agent turn session=%s turn=%d messages=%d",
            session_id,
            turn,
            len(messages),
        )
        tool_calls: dict[int, dict[str, str]] = {}
        assistant_content = ""
        think_content = ""
        async for event in llm.stream(
            messages, tool_schemas, think
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
                if event.get("name"):
                    logger.info(
                        "tool call delta session=%s name=%s call_id=%s",
                        session_id,
                        event.get("name"),
                        event.get("id") or "",
                    )

        if not tool_calls:
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
            logger.info(
                "agent done session=%s content_len=%d",
                session_id,
                len(assistant_content),
            )
            return

        assistant_tool_calls = []
        tool_results: list[tuple[str, str]] = []
        call_todos: dict[str, dict[str, Any]] = {}
        call_names = [
            TOOL_ALIASES.get(call["name"], call["name"])
            for call in tool_calls.values()
        ]
        if "create_plan" in call_names:
            plan_choice_resolved = True
        elif (
            not plan_choice_resolved
            and any(
                name not in _READ_ONLY_TOOLS and name not in _NO_PLAN_TOOLS
                for name in call_names
            )
        ):
            yield sse_event(
                "tool",
                {
                    "tool": "plan_choice",
                    "status": "confirm",
                    "message": "执行任务前是否先出一份方案？",
                    "confirm_type": "plan_choice",
                    "session_id": session_id,
                },
            )
            plan_first = await wait_for_terminal_decision(
                session_id, "是否先出一份方案"
            )
            plan_choice_resolved = True
            if plan_first:
                if assistant_content:
                    messages.append(
                        {"role": "assistant", "content": assistant_content}
                    )
                messages.append(
                    {
                        "role": "user",
                        "content": "用户选择先出一份方案。"
                        "请先调用 create_plan 制定计划，不要直接执行其他工具。",
                    }
                )
                yield sse_event(
                    "tool",
                    {
                        "tool": "plan_choice",
                        "status": "done",
                        "message": "已选择先出方案",
                        "confirm_type": "plan_choice",
                        "session_id": session_id,
                    },
                )
                logger.info(
                    "plan choice session=%s decision=plan_first",
                    session_id,
                )
                continue
            yield sse_event(
                "tool",
                {
                    "tool": "plan_choice",
                    "status": "done",
                    "message": "已选择直接执行",
                    "confirm_type": "plan_choice",
                    "session_id": session_id,
                },
            )
            logger.info(
                "plan choice session=%s decision=direct",
                session_id,
            )
        for index, call in sorted(tool_calls.items()):
            name = call["name"]
            call_id = call["id"] or f"call_{index}"
            try:
                arguments = json.loads(call["arguments"] or "{}")
            except json.JSONDecodeError:
                arguments = {"_raw": call["arguments"]}
            logger.info(
                "tool call session=%s name=%s call_id=%s args=[%s]",
                session_id,
                call["name"],
                call_id,
                _summarize_arguments(arguments),
            )
            assistant_tool_calls.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": call["name"],
                        "arguments": call["arguments"] or "{}",
                    },
                }
            )
            adapter = get_tool(name)
            if adapter is None:
                adapter = (
                    get_tool(TOOL_ALIASES.get(name, ""))
                    if name in TOOL_ALIASES
                    else None
                )
            if adapter is None:
                unknown_tool_counts[name] = unknown_tool_counts.get(name, 0) + 1
                available = ", ".join(
                    sorted(tool["name"] for tool in registry.list())
                )
                detail = f"未知工具: {name}，可用工具：{available}"
                tool_message = json.dumps({"error": detail}, ensure_ascii=False)
                yield sse_event(
                    "tool",
                    {
                        "tool": name,
                        "status": "error",
                        "message": detail,
                    },
                )
                tool_results.append((call_id, tool_message))
                if unknown_tool_counts[name] >= 2:
                    logger.warning(
                        "unknown tool loop session=%s tool=%s count=%d",
                        session_id,
                        name,
                        unknown_tool_counts[name],
                    )
                    yield error_event(
                        "tool_loop",
                        f"模型连续调用不存在的工具 {name}，已停止",
                    )
                    return
            else:
                if name == "create_plan":
                    raw_items = (
                        arguments.get("items") or arguments.get("todos") or []
                    )
                    titles = [
                        str(item).strip()
                        for item in raw_items
                        if str(item).strip()
                    ]
                    if not titles:
                        tool_message = json.dumps(
                            {"error": "计划项不能为空"},
                            ensure_ascii=False,
                        )
                        yield sse_event(
                            "tool",
                            {
                                "tool": name,
                                "status": "error",
                                "message": "计划项不能为空",
                            },
                        )
                        tool_results.append((call_id, tool_message))
                    else:
                        todos = db.replace_todos(session_id, titles)
                        if plan_message is not None:
                            plan_message["content"] = _plan_progress(todos)
                        else:
                            plan_message = {
                                "role": "system",
                                "content": _plan_progress(todos),
                            }
                            messages.insert(1, plan_message)
                        yield sse_event("plan", {"items": todos})
                        yield sse_event(
                            "tool",
                            {
                                "tool": name,
                                "status": "confirm",
                                "message": "计划已创建，是否开始执行？",
                                "confirm_type": "plan",
                                "session_id": session_id,
                            },
                        )
                        allowed = await wait_for_terminal_decision(
                            session_id, "执行计划"
                        )
                        if not allowed:
                            db.replace_todos(session_id, [])
                            todos = []
                            if plan_message is not None:
                                messages.remove(plan_message)
                                plan_message = None
                            yield sse_event("plan", {"items": []})
                            tool_message = json.dumps(
                                {"error": "用户拒绝执行计划"},
                                ensure_ascii=False,
                            )
                            yield sse_event(
                                "tool",
                                {
                                    "tool": name,
                                    "status": "error",
                                    "message": "用户拒绝执行计划",
                                    "session_id": session_id,
                                },
                            )
                            tool_results.append((call_id, tool_message))
                            yield error_event(
                                "plan_denied", "用户拒绝执行计划"
                            )
                            return
                        tool_message = json.dumps(
                            {
                                "success": True,
                                "message": f"计划已确认，共 {len(todos)} 项",
                            },
                            ensure_ascii=False,
                        )
                        yield sse_event(
                            "tool",
                            {
                                "tool": name,
                                "status": "done",
                                "message": f"计划已确认，共 {len(todos)} 项",
                            },
                        )
                        tool_results.append((call_id, tool_message))
                    continue
                call_key = (
                    f"{name}|"
                    + json.dumps(arguments, sort_keys=True, ensure_ascii=False)
                )
                repeated_calls[call_key] = (
                    repeated_calls.get(call_key, 0) + 1
                )
                if repeated_calls[call_key] >= 3:
                    logger.warning(
                        "repeated tool call session=%s tool=%s",
                        session_id,
                        name,
                    )
                    yield error_event(
                        "tool_loop",
                        f"模型重复调用同一工具 {name}，已停止",
                    )
                    return
                todo = None
                if todos:
                    todo = _claim_next_todo(session_id, todos)
                    if todo is not None:
                        call_todos[call_id] = todo
                        yield _todo_update_event(todo)
                external_paths = adapter.external_paths(workspace, arguments)
                if external_paths and approval_mode == "ask":
                    logger.info(
                        "external confirm session=%s tool=%s paths=%s",
                        session_id,
                        name,
                        external_paths,
                    )
                    yield sse_event(
                        "tool",
                        {
                            "tool": name,
                            "status": "confirm",
                            "message": "外部路径需要确认",
                            "confirm_type": "external_file",
                            "paths": external_paths,
                            "session_id": session_id,
                        },
                    )
                    allowed = await wait_for_terminal_decision(
                        session_id, external_paths[0]
                    )
                    if not allowed:
                        logger.warning(
                            "external path denied session=%s tool=%s path=%s",
                            session_id,
                            name,
                            external_paths[0],
                        )
                        tool_message = json.dumps(
                            {
                                "error": "用户拒绝访问外部路径",
                                "paths": external_paths,
                            },
                            ensure_ascii=False,
                        )
                        yield sse_event(
                            "tool",
                            {
                                "tool": name,
                                "status": "error",
                                "message": "用户拒绝访问外部路径",
                                "paths": external_paths,
                                "session_id": session_id,
                            },
                        )
                        tool_results.append((call_id, tool_message))
                        todo = call_todos.get(call_id)
                        if todo is not None:
                            _finish_todo(todo, False, "用户拒绝访问外部路径")
                            yield _todo_update_event(todo)
                        continue
                is_terminal = name == "terminal"
                command = str(arguments.get("command") or "")
                policy = (
                    terminal_command_policy(command) if is_terminal else "safe"
                )
                if is_terminal and approval_mode == "full":
                    policy = "safe"
                elif (
                    is_terminal
                    and approval_mode == "assist"
                    and policy != "block"
                ):
                    policy = "safe"
                logger.info(
                    "tool policy session=%s tool=%s policy=%s command=%s",
                    session_id,
                    name,
                    policy,
                    command[:300],
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
                    todo = call_todos.get(call_id)
                    if todo is not None:
                        _finish_todo(todo, False, "已阻止危险命令")
                        yield _todo_update_event(todo)
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
                        todo = call_todos.get(call_id)
                        if todo is not None:
                            _finish_todo(todo, False, "用户拒绝执行")
                            yield _todo_update_event(todo)
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
                            session_id, adapter, name, arguments, workspace
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
                        todo = call_todos.get(call_id)
                        if todo is not None:
                            _finish_todo(
                                todo,
                                bool(output.get("success")),
                                str(output.get("message") or ""),
                            )
                            yield _todo_update_event(todo)
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
                        session_id, adapter, name, arguments, workspace
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
                    if (
                        name == "schedule_task"
                        and str(arguments.get("action") or "") == "create"
                        and output.get("success")
                    ):
                        calendar_pending = (
                            (output.get("data") or {}).get("task") or output
                        )
                        yield sse_event(
                            "scheduled_tasks_changed",
                            {"tasks": db.list_scheduled_tasks()},
                        )
                    if (
                        name == "write_calendar"
                        and output.get("success")
                    ):
                        yield sse_event(
                            "calendar_events_changed",
                            {"events": db.list_calendar_events()},
                        )
                    tool_results.append((call_id, tool_message))
                    todo = call_todos.get(call_id)
                    if todo is not None:
                        _finish_todo(
                            todo,
                            bool(output.get("success")),
                            str(output.get("message") or ""),
                        )
                        yield _todo_update_event(todo)
        db.save_tool_turn(
            session_id,
            assistant_tool_calls,
            think_content,
            tool_results,
        )
        logger.info(
            "tool turn saved session=%s calls=%d results=%d",
            session_id,
            len(assistant_tool_calls),
            len(tool_results),
        )
        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "content": assistant_content,
            "tool_calls": assistant_tool_calls,
            "reasoning_content": think_content,
        }
        messages.append(assistant_message)
        for call_id, tool_message in tool_results:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": tool_message,
                }
            )
        if calendar_pending and "write_calendar" not in call_names:
            task_id = str(calendar_pending.get("id") or "")
            title = str(
                calendar_pending.get("title")
                or calendar_pending.get("message")
                or "定时任务"
            )
            yield sse_event(
                "tool",
                {
                    "tool": "schedule_task",
                    "status": "confirm",
                    "confirm_type": "write_calendar",
                    "message": "是否同时写入日程？",
                    "session_id": session_id,
                    "result": calendar_pending,
                },
            )
            allowed = await wait_for_terminal_decision(
                session_id, "是否写入日程"
            )
            if allowed and task_id:
                yield sse_event(
                    "tool",
                    {
                        "tool": "schedule_task",
                        "status": "done",
                        "message": "已确认写入日程",
                        "session_id": session_id,
                        "result": calendar_pending,
                    },
                )
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"用户同意把提醒“{title}”写入日程。"
                            f"请调用 write_calendar 工具创建日程事件，"
                            f"task_id 传 {task_id}，"
                            "标题和起止时间按该提醒的信息填写。"
                        ),
                    }
                )
                continue
            yield sse_event(
                "tool",
                {
                    "tool": "schedule_task",
                    "status": "done",
                    "message": "不写入日程",
                    "session_id": session_id,
                    "result": calendar_pending,
                },
            )

    logger.warning("tool turn limit session=%s", session_id)
    raise RuntimeError(
        f"工具调用轮次超过限制（{MAX_TOOL_TURNS} 轮），任务太复杂，请分步进行"
    )


async def _execute_tool(
    session_id: str,
    adapter: Any,
    name: str,
    arguments: dict[str, Any],
    workspace: Any,
) -> dict[str, Any]:
    from . import db

    run = db.add_tool_run(session_id, name, "start", arguments)
    started = time.monotonic()
    logger.info("tool start session=%s name=%s", session_id, name)
    logger.info(
        "tool args session=%s name=%s args=[%s]",
        session_id,
        name,
        _summarize_arguments(arguments),
    )
    try:
        result = await adapter.run(workspace, arguments)
        output = result.as_dict()
        db.update_tool_run(run["id"], "done", output)
        logger.info(
            "tool done session=%s name=%s duration=%.2fs success=%s",
            session_id,
            name,
            time.monotonic() - started,
            output.get("success"),
        )
        return output
    except ToolExecutionError as exc:
        output = {"success": False, "message": str(exc)}
        db.update_tool_run(run["id"], "error", output)
        logger.warning(
            "tool error session=%s name=%s duration=%.2fs error=%s",
            session_id,
            name,
            time.monotonic() - started,
            exc,
        )
        return output
