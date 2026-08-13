from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Literal, Optional, Union

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
    ModelRequest,
    TodoListMiddleware,
    ToolCallLimitMiddleware,
    ToolErrorMiddleware,
    dynamic_prompt,
)
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
    convert_to_messages,
)
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.prebuilt import ToolRuntime
from langgraph.stream.transformers import CustomTransformer
from langgraph.types import Command, interrupt
from pydantic import ConfigDict, create_model

from . import db
from .agent import (
    MAX_TOOL_TURNS,
    SYSTEM_PROMPT,
    _NO_PLAN_TOOLS,
    _READ_ONLY_TOOLS,
    _auto_rag_context,
    _claim_next_todo,
    _execute_tool,
    _finish_todo,
    _plan_progress,
)
from .api.terminal import (
    create_terminal_decision,
    remove_terminal_decision,
    terminal_command_policy,
)
from .config import settings_store
from .github_skills import preview_skill_repo
from .llm import ChatDeepSeekProvider, MockChatModel
from .sse import error_event, sse_event
from .skills import (
    discover_importable_skills,
    find_importable_skill,
    skill_registry,
)
from .tools.registry import registry

logger = logging.getLogger("divine.agent_langchain")

_CHECKPOINTER = InMemorySaver()
_TOOL_LOCKS: dict[str, asyncio.Lock] = {}
_ACTIVE_INTERRUPTS: set[tuple[str, str]] = set()
_PLAN_CONTINUATION_KEYWORDS = (
    "继续",
    "下一步",
    "执行计划",
    "按计划",
    "开始执行",
    "接着",
    "往下",
    "continue",
    "next step",
)


class TodoSyncMiddleware(AgentMiddleware):
    """Persist LangGraph todo state back to SQLite and emit plan SSE events."""

    def __init__(self, ctx: AgentRunContext) -> None:
        super().__init__()
        self.ctx = ctx

    async def awrap_tool_call(
        self, request: Any, handler: Any
    ) -> Any:
        result = await handler(request)
        if request.tool_call.get("name") != "write_todos":
            return result
        self.ctx.plan_first_pending = False
        db.update_session(self.ctx.session_id, plan_mode="direct")
        raw_todos = (request.tool_call.get("args") or {}).get("todos") or []
        titles = [
            str(todo.get("content") or "").strip()
            for todo in raw_todos
            if str(todo.get("content") or "").strip()
        ]
        items = db.replace_todos(self.ctx.session_id, titles)
        request.runtime.stream_writer({"event": "plan", "items": items})
        return result


@dataclass
class AgentRunContext:
    session_id: str
    workspace: Path
    approval_mode: str
    plan_choice_resolved: bool = False
    plan_first_pending: bool = False
    plan_approved: bool = False


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                value = part.get("text") or part.get("content")
                if value:
                    parts.append(str(value))
        return "".join(parts)
    return str(content) if content else ""


def _schema_annotation(schema: dict[str, Any]) -> Any:
    enum_values = schema.get("enum")
    if enum_values:
        values = [
            value
            for value in enum_values
            if isinstance(value, (str, int, float, bool))
        ]
        literals = tuple(Literal[value] for value in values)
        return literals[0] if len(literals) == 1 else Union[literals]

    schema_type = schema.get("type")
    if schema_type == "string":
        return str
    if schema_type == "integer":
        return int
    if schema_type == "number":
        return float
    if schema_type == "boolean":
        return bool
    if schema_type == "array":
        return list[_schema_annotation(schema.get("items") or {})]
    if schema_type == "object":
        return dict[str, Any]
    for key in ("anyOf", "oneOf"):
        sub_schemas = schema.get(key)
        if sub_schemas:
            annotations = [_schema_annotation(item) for item in sub_schemas]
            return annotations[0] if len(annotations) == 1 else Union[tuple(annotations)]
    return Any


def _make_args_model(
    name: str, parameters: dict[str, Any] | None
) -> Any:
    parameters = parameters or {}
    properties = parameters.get("properties") or {}
    if not properties:
        return None
    required = set(parameters.get("required") or [])
    fields: dict[str, tuple[Any, Any]] = {}
    for prop_name, prop_schema in properties.items():
        annotation = _schema_annotation(prop_schema or {})
        if prop_name in required:
            fields[prop_name] = (annotation, ...)
        else:
            fields[prop_name] = (Optional[annotation], None)
    return create_model(
        f"{name}_args",
        __config__=ConfigDict(extra="allow"),
        **fields,
    )


def _skill_tool_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()).strip("_-")
    return f"skill_{cleaned or 'script'}"


def _skill_script_timeout() -> int:
    try:
        return max(1, int(os.getenv("DIVINE_SKILL_SCRIPT_TIMEOUT", "120")))
    except ValueError:
        return 120


def _run_skill_script(
    script: Path,
    skill_dir: Path,
    mode: str,
    params: dict[str, Any] | None,
    args: list[str] | None,
    timeout: int | None,
) -> Any:
    timeout = timeout or _skill_script_timeout()
    command = [sys.executable, str(script)]
    stdin_text: str | None = None
    if mode == "json":
        stdin_text = json.dumps({"params": params or {}}, ensure_ascii=False)
    else:
        command.extend(str(item) for item in (args or []))

    try:
        completed = subprocess.run(
            command,
            input=stdin_text,
            capture_output=True,
            text=True,
            cwd=str(skill_dir),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"技能脚本执行超时（{timeout}s）") from exc
    except OSError as exc:
        raise RuntimeError(f"无法启动技能脚本: {exc}") from exc

    stdout_text = completed.stdout or ""
    stderr_text = completed.stderr or ""
    if completed.returncode != 0:
        detail = stderr_text.strip() or stdout_text.strip()
        raise RuntimeError(
            "技能脚本退出码 %d：%s"
            % (completed.returncode, detail[-500:] if detail else "无输出")
        )

    if mode == "json":
        try:
            return json.loads(stdout_text)
        except json.JSONDecodeError as exc:
            tail = stderr_text.strip()[-200:] if stderr_text.strip() else ""
            raise RuntimeError(
                "技能脚本未返回合法 JSON: "
                + stdout_text[-300:]
                + (f"；stderr: {tail}" if tail else "")
            ) from exc

    output = stdout_text.strip()
    if stderr_text.strip():
        output = output + ("\n" if output else "") + "[stderr]\n" + stderr_text.strip()[-2000:]
    if not output:
        output = "（技能脚本无输出）"
    if len(output) > 30000:
        output = output[:30000] + "\n...[输出已截断]"
    return output


def _skill_args_model(name: str, mode: str) -> Any:
    model_name = f"{_skill_tool_name(name)}_args".replace("-", "_")
    if mode == "json":
        return create_model(
            model_name,
            params=(dict[str, Any], ...),
            timeout=(Optional[int], None),
        )
    return create_model(
        model_name,
        args=(Optional[list[str]], None),
        timeout=(Optional[int], None),
    )


def _auto_rag_context_lc(
    messages: list[Any], workspace: Path
) -> str | None:
    history: list[dict[str, Any]] = []
    for message in messages:
        role = getattr(message, "type", "")
        if role == "human":
            role = "user"
        elif role == "ai":
            role = "assistant"
        elif role == "tool":
            role = "tool"
        else:
            continue
        content = _content_text(getattr(message, "content", ""))
        if not content:
            continue
        history.append({"role": role, "content": content})
    return _auto_rag_context(history, workspace)


def _skill_catalog_prompt() -> str:
    knowledge_skills = skill_registry.knowledge_skills()
    executable_skills = skill_registry.executable_skills()
    if not knowledge_skills and not executable_skills:
        return ""
    lines: list[str] = []
    if knowledge_skills:
        lines.append("可用知识技能（需要时调用 load_skill 加载正文和参考资料）：")
        for skill in knowledge_skills:
            lines.append(f"- {skill.name}: {skill.description}")
    if executable_skills:
        lines.append("可用能力技能（可直接调用脚本工具执行）：")
        for skill in executable_skills:
            tool_name = _skill_tool_name(skill.name)
            if skill.script_mode == "json":
                usage = "从 stdin 读取 JSON 参数"
            else:
                usage = "接收命令行参数 args"
            lines.append(
                f"- {skill.name}: {skill.description}"
                f"（调用 {tool_name}，{usage}）"
            )
    return "\n".join(lines)


def _active_plan_progress(
    messages: list[Any], todos: list[dict[str, Any]]
) -> str | None:
    if not todos:
        return None
    last_user_index = -1
    for index, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            last_user_index = index
    if last_user_index < 0:
        return _plan_progress(todos)

    question = _content_text(messages[last_user_index].content).lower()
    if any(
        keyword in question for keyword in _PLAN_CONTINUATION_KEYWORDS
    ):
        return _plan_progress(todos)

    for message in messages[last_user_index + 1 :]:
        if isinstance(message, ToolMessage) and getattr(
            message, "name", None
        ) == "write_todos":
            return _plan_progress(todos)
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls or []:
            name = call.get("name") if isinstance(call, dict) else getattr(
                call, "name", ""
            )
            if name == "write_todos":
                return _plan_progress(todos)
    return None


_PLAN_EXPLICIT_KEYWORDS = (
    "先出方案",
    "出方案",
    "做方案",
    "写方案",
    "给个方案",
    "制定计划",
    "做个计划",
    "做计划",
    "规划",
    "方案",
)
_NO_PLAN_EXPLICIT_KEYWORDS = (
    "不要方案",
    "不用方案",
    "不需要方案",
    "别问",
    "直接执行",
    "直接做",
    "直接完成",
    "不用计划",
    "不要计划",
)
_COMPLEX_PLAN_KEYWORDS = (
    "重构",
    "迁移",
    "搭建",
    "开发",
    "创建项目",
    "生成项目",
    "整个项目",
    "项目结构",
    "全栈",
    "多文件",
    "多个文件",
    "多页面",
    "多个页面",
    "多步",
    "多步骤",
    "批量",
    "所有文件",
    "全部文件",
    "完整",
    "复杂",
    "系统",
    "模块",
    "功能",
    "页面",
    "前端",
    "后端",
    "数据库",
    "接口",
    "组件",
    "网站",
    "应用",
    "脚手架",
    "框架",
    "教程",
    "目录结构",
)


def _should_ask_plan(messages: list[Any]) -> bool:
    user_messages = [
        message
        for message in messages
        if isinstance(message, HumanMessage)
    ]
    if not user_messages:
        return True
    text = _content_text(user_messages[-1].content).strip()
    if not text:
        return True
    lowered = text.lower()
    if any(keyword in lowered for keyword in _NO_PLAN_EXPLICIT_KEYWORDS):
        return False
    if any(keyword in lowered for keyword in _PLAN_EXPLICIT_KEYWORDS):
        return True

    score = 0
    if len(text) >= 100:
        score += 1
    score += sum(
        1 for keyword in _COMPLEX_PLAN_KEYWORDS if keyword in lowered
    )
    separators = sum(
        1
        for separator in ("、", "，", "和", "以及", "还要", "同时", "\n")
        if separator in text
    )
    if separators >= 2:
        score += 1
    if text.count("文件") >= 2 or text.count("页面") >= 2:
        score += 1
    return score >= 2


def _build_dynamic_prompt(ctx: AgentRunContext) -> Any:
    @dynamic_prompt
    def prompt(request: ModelRequest) -> str:
        current_settings = settings_store.load()
        provider = current_settings.get("provider") or "auto"
        model_name = current_settings.get("model") or "deepseek-v4-flash"
        if provider == "mock" or (
            provider == "auto" and not current_settings.get("api_key")
        ):
            model_line = "当前模型：本地演示模式（Mock）"
        else:
            model_line = f"当前模型：{model_name}"
        parts = [
            SYSTEM_PROMPT.replace("create_plan", "write_todos"),
            (
                f"当前会话所属项目工作目录：{ctx.workspace}\n"
                "请以该目录作为方案设计和文件操作的工作区。"
            ),
            model_line,
        ]
        todos = db.list_todos(ctx.session_id)
        plan_progress = _active_plan_progress(
            request.state.get("messages") or [], todos
        )
        if plan_progress:
            parts.append(plan_progress)
        rag_context = _auto_rag_context_lc(
            request.state.get("messages") or [], ctx.workspace
        )
        if rag_context:
            parts.append(rag_context)
        skill_catalog = _skill_catalog_prompt()
        if skill_catalog:
            parts.append(skill_catalog)
        return "\n\n".join(parts)

    return prompt


def _build_llm() -> Any:
    settings = settings_store.load()
    provider = settings.get("provider") or "auto"
    if provider == "mock":
        return MockChatModel()
    if provider == "langchain":
        return ChatDeepSeekProvider().llm
    if provider == "auto" and not settings.get("api_key"):
        return MockChatModel()
    return ChatDeepSeekProvider().llm


def _serialize_tool_calls(tool_calls: list[Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for call in tool_calls:
        name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
        call_id = call.get("id") if isinstance(call, dict) else getattr(call, "id", "")
        args = call.get("args") if isinstance(call, dict) else getattr(call, "args", {})
        calls.append(
            {
                "id": call_id or "",
                "type": "function",
                "function": {
                    "name": name or "",
                    "arguments": json.dumps(args or {}, ensure_ascii=False),
                },
            }
        )
    return calls


def _persist_new_messages(
    session_id: str,
    input_messages: list[Any],
    messages: list[Any],
    think_by_id: dict[str, str],
) -> None:
    last_input_index = -1
    if input_messages:
        last_input = input_messages[-1]
        for index, message in enumerate(messages):
            if type(message) is type(last_input) and _content_text(
                message.content
            ) == _content_text(last_input.content):
                last_input_index = index
    if last_input_index < 0:
        last_input_index = 0

    index = last_input_index + 1
    while index < len(messages):
        message = messages[index]
        if not isinstance(message, AIMessage):
            index += 1
            continue
        if message.tool_calls:
            calls = _serialize_tool_calls(message.tool_calls)
            results: list[tuple[str, str]] = []
            next_index = index + 1
            while next_index < len(messages) and isinstance(
                messages[next_index], ToolMessage
            ):
                results.append(
                    (
                        messages[next_index].tool_call_id,
                        _content_text(messages[next_index].content),
                    )
                )
                next_index += 1
            if results:
                db.save_tool_turn(
                    session_id,
                    calls,
                    think_by_id.get(message.id, ""),
                    results,
                )
            index = next_index
            continue

        content = _content_text(message.content)
        if content:
            saved = db.add_message(session_id, "assistant", content)
            think = think_by_id.get(message.id, "")
            if think:
                db.add_message_part(saved["id"], "think", think, order=0)
        index += 1


def _extract_final_content(messages: list[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not message.tool_calls:
            return _content_text(message.content)
    return ""


def _sync_todos_from_state(
    session_id: str, final_state: dict[str, Any]
) -> None:
    todos = final_state.get("todos")
    if todos is None:
        return
    titles = [
        str(todo.get("content") or "").strip()
        for todo in todos
        if str(todo.get("content") or "").strip()
    ]
    db.replace_todos(session_id, titles)


def _custom_sse(payload: Any) -> str:
    if not isinstance(payload, dict):
        return sse_event("tool", {"message": str(payload)})
    event_name = payload.get("event", "tool")
    data = {key: value for key, value in payload.items() if key != "event"}
    return sse_event(event_name, data)


def _frontend_tool_result(output: dict[str, Any]) -> dict[str, Any]:
    result = dict(output)
    for key in ("content", "stdout", "stderr"):
        value = result.get(key)
        if isinstance(value, str) and len(value) > 4000:
            result[key] = value[:4000] + f"\n...[截断，共 {len(value)} 字符]"
    data = result.get("data")
    if isinstance(data, dict):
        data_copy = dict(data)
        for key in ("content", "stdout", "stderr", "text"):
            value = data_copy.get(key)
            if isinstance(value, str) and len(value) > 4000:
                data_copy[key] = (
                    value[:4000] + f"\n...[截断，共 {len(value)} 字符]"
                )
        results = data_copy.get("results")
        if isinstance(results, list) and len(results) > 12:
            data_copy["results"] = results[:12] + [
                {"truncated": True, "count": len(results) - 12}
            ]
        result["data"] = data_copy
    return result


def _ask_interrupt(
    session_id: str,
    marker: str,
    payload: dict[str, Any],
) -> Any:
    key = (session_id, marker)
    if key not in _ACTIVE_INTERRUPTS:
        _ACTIVE_INTERRUPTS.add(key)
    decision = interrupt(payload)
    _ACTIVE_INTERRUPTS.discard(key)
    return decision


async def _handle_adapter_call(
    ctx: AgentRunContext,
    runtime: ToolRuntime,
    adapter: Any,
    name: str,
    arguments: dict[str, Any],
) -> Any:
    call_id = runtime.tool_call_id or f"call_{time.monotonic_ns()}"
    writer = runtime.stream_writer

    if (
        not ctx.plan_choice_resolved
        and name not in _READ_ONLY_TOOLS
        and name not in _NO_PLAN_TOOLS
        and _should_ask_plan(runtime.state.get("messages") or [])
    ):
        decision = _ask_interrupt(
            ctx.session_id,
            f"plan_choice:{call_id}",
            {
                "type": "plan_choice",
                "session_id": ctx.session_id,
                "tool": name,
                "message": "执行任务前是否先出一份方案？",
                "call_id": call_id,
            },
        )
        plan_first = (
            bool(decision.get("allowed"))
            if isinstance(decision, dict)
            else bool(decision)
        )
        ctx.plan_choice_resolved = True
        db.update_session(
            ctx.session_id,
            plan_mode="plan_first" if plan_first else "direct",
        )
        if plan_first:
            ctx.plan_first_pending = True
        else:
            ctx.plan_approved = True
        writer(
            {
                "event": "tool",
                "tool": "plan_choice",
                "status": "done",
                "message": "已选择先出方案" if plan_first else "已选择直接执行",
                "confirm_type": "plan_choice",
                "session_id": ctx.session_id,
            }
        )
        if plan_first:
            return (
                "用户选择先出一份方案。"
                "请先调用 create_plan 制定计划，不要直接执行其他工具。"
            )

    if name != "create_plan" and ctx.plan_first_pending:
        return (
            "用户选择先出一份方案。"
            "请先调用 create_plan 制定计划，不要直接执行其他工具。"
        )

    todo = None
    todos = db.list_todos(ctx.session_id)
    if todos:
        todo = _claim_next_todo(ctx.session_id, todos)
        if todo is not None:
            writer(
                {
                    "event": "todo_update",
                    "id": todo["id"],
                    "status": todo["status"],
                }
            )

    try:
        if name == "migrate_skill":
            candidate = find_importable_skill(
                ctx.workspace,
                str(arguments.get("name") or ""),
                str(arguments.get("source_tool") or "") or None,
            )
            if candidate is not None:
                target = str(arguments.get("target") or "project")
                decision = _ask_interrupt(
                    ctx.session_id,
                    f"skill_migrate:{call_id}",
                    {
                        "type": "skill_migrate",
                        "session_id": ctx.session_id,
                        "tool": name,
                        "message": (
                            f"确认将技能 {candidate['name']} "
                            f"迁移到 {target} 级目录？"
                        ),
                        "skill": candidate,
                        "target": target,
                        "call_id": call_id,
                    },
                )
                allowed = (
                    bool(decision.get("allowed"))
                    if isinstance(decision, dict)
                    else bool(decision)
                )
                if not allowed:
                    if todo is not None:
                        _finish_todo(todo, False, "用户取消技能迁移")
                        writer(
                            {
                                "event": "todo_update",
                                "id": todo["id"],
                                "status": todo["status"],
                            }
                        )
                    writer(
                        {
                            "event": "tool",
                            "tool": name,
                            "status": "error",
                            "message": "用户取消技能迁移",
                            "session_id": ctx.session_id,
                            "call_id": call_id,
                        }
                    )
                    return json.dumps(
                        {
                            "error": "用户取消技能迁移",
                            "skill": candidate["name"],
                        },
                        ensure_ascii=False,
                    )

        if name == "migrate_skills":
            names = [
                str(item or "").strip()
                for item in (arguments.get("names") or [])
                if str(item or "").strip()
            ]
            source_tool = (
                str(arguments.get("source_tool") or "").strip() or None
            )
            target = str(arguments.get("target") or "project")
            candidates = [
                candidate
                for candidate in discover_importable_skills(ctx.workspace)
                if candidate["name"] in names
                and (
                    not source_tool
                    or candidate["source_tool"] == source_tool
                )
            ]
            unique: dict[str, dict[str, Any]] = {}
            for candidate in candidates:
                unique.setdefault(str(candidate["name"]), candidate)
            selected = list(unique.values())
            if selected:
                decision = _ask_interrupt(
                    ctx.session_id,
                    f"skill_migrate_batch:{call_id}",
                    {
                        "type": "skill_migrate_batch",
                        "session_id": ctx.session_id,
                        "tool": name,
                        "message": (
                            f"确认批量迁移 {len(selected)} 个技能？"
                        ),
                        "skills": selected,
                        "target": target,
                        "call_id": call_id,
                    },
                )
                allowed = (
                    bool(decision.get("allowed"))
                    if isinstance(decision, dict)
                    else bool(decision)
                )
                if not allowed:
                    if todo is not None:
                        _finish_todo(todo, False, "用户取消批量技能迁移")
                        writer(
                            {
                                "event": "todo_update",
                                "id": todo["id"],
                                "status": todo["status"],
                            }
                        )
                    writer(
                        {
                            "event": "tool",
                            "tool": name,
                            "status": "error",
                            "message": "用户取消批量技能迁移",
                            "session_id": ctx.session_id,
                            "call_id": call_id,
                        }
                    )
                    return json.dumps(
                        {
                            "error": "用户取消批量技能迁移",
                            "skills": [item["name"] for item in selected],
                        },
                        ensure_ascii=False,
                    )

        if name == "install_skill":
            repo_url = str(arguments.get("repo_url") or "")
            ref = str(arguments.get("ref") or "") or None
            target = str(arguments.get("target") or "project")
            try:
                repo_preview = await preview_skill_repo(repo_url, ref)
            except Exception:
                repo_preview = None
            if repo_preview is not None:
                decision = _ask_interrupt(
                    ctx.session_id,
                    f"skill_install:{call_id}",
                    {
                        "type": "skill_install",
                        "session_id": ctx.session_id,
                        "tool": name,
                        "message": (
                            f"确认安装 GitHub 仓库 "
                            f"{repo_preview.get('repo', '')} 中的技能？"
                        ),
                        "repo_preview": repo_preview,
                        "target": target,
                        "call_id": call_id,
                    },
                )
                allowed = (
                    bool(decision.get("allowed"))
                    if isinstance(decision, dict)
                    else bool(decision)
                )
                if not allowed:
                    if todo is not None:
                        _finish_todo(todo, False, "用户取消技能安装")
                        writer(
                            {
                                "event": "todo_update",
                                "id": todo["id"],
                                "status": todo["status"],
                            }
                        )
                    writer(
                        {
                            "event": "tool",
                            "tool": name,
                            "status": "error",
                            "message": "用户取消技能安装",
                            "session_id": ctx.session_id,
                            "call_id": call_id,
                        }
                    )
                    return json.dumps(
                        {
                            "error": "用户取消技能安装",
                            "repo": repo_preview.get("repo", ""),
                        },
                        ensure_ascii=False,
                    )

        external_paths = adapter.external_paths(ctx.workspace, arguments)
        if external_paths and ctx.approval_mode == "ask":
            logger.info(
                "external confirm session=%s tool=%s paths=%s",
                ctx.session_id,
                name,
                external_paths,
            )
            decision = _ask_interrupt(
                ctx.session_id,
                f"external_file:{call_id}",
                {
                    "type": "external_file",
                    "session_id": ctx.session_id,
                    "tool": name,
                    "message": "外部路径需要确认",
                    "paths": external_paths,
                    "call_id": call_id,
                },
            )
            allowed = (
                bool(decision.get("allowed"))
                if isinstance(decision, dict)
                else bool(decision)
            )
            if not allowed:
                if todo is not None:
                    _finish_todo(todo, False, "用户拒绝访问外部路径")
                    writer(
                        {
                            "event": "todo_update",
                            "id": todo["id"],
                            "status": todo["status"],
                        }
                    )
                writer(
                        {
                            "event": "tool",
                            "tool": name,
                            "status": "error",
                            "message": "已拒绝访问外部路径",
                            "paths": external_paths,
                            "session_id": ctx.session_id,
                            "call_id": call_id,
                        }
                    )
                return json.dumps(
                    {
                        "success": False,
                        "message": "用户拒绝了外部路径访问",
                        "paths": external_paths,
                        "rejected": True,
                    },
                    ensure_ascii=False,
                )

        is_terminal = name == "terminal"
        command = str(arguments.get("command") or "")
        policy = terminal_command_policy(command) if is_terminal else "safe"
        if is_terminal and ctx.approval_mode == "full":
            policy = "safe"
        elif (
            is_terminal
            and ctx.approval_mode == "assist"
            and policy != "block"
        ):
            policy = "safe"
        elif is_terminal and policy == "confirm" and ctx.plan_approved:
            policy = "safe"

        logger.info(
            "tool policy session=%s tool=%s policy=%s command=%s",
            ctx.session_id,
            name,
            policy,
            command[:300],
        )

        if is_terminal and policy == "block":
            if todo is not None:
                _finish_todo(todo, False, "已阻止危险命令")
                writer(
                    {
                        "event": "todo_update",
                        "id": todo["id"],
                        "status": todo["status"],
                    }
                )
            writer(
                {
                    "event": "tool",
                    "tool": name,
                    "status": "error",
                    "message": "已阻止危险命令",
                    "command": command,
                    "result": {"command": command},
                    "session_id": ctx.session_id,
                    "call_id": call_id,
                }
            )
            return json.dumps(
                {"error": "已阻止危险命令", "command": command},
                ensure_ascii=False,
            )

        if is_terminal and policy == "confirm":
            decision = _ask_interrupt(
                ctx.session_id,
                f"terminal:{call_id}",
                {
                    "type": "terminal",
                    "session_id": ctx.session_id,
                    "tool": name,
                    "message": "等待用户确认",
                    "command": command,
                    "call_id": call_id,
                },
            )
            allowed = (
                bool(decision.get("allowed"))
                if isinstance(decision, dict)
                else bool(decision)
            )
            if not allowed:
                if todo is not None:
                    _finish_todo(todo, False, "用户拒绝执行")
                    writer(
                        {
                            "event": "todo_update",
                            "id": todo["id"],
                            "status": todo["status"],
                        }
                    )
                writer(
                    {
                        "event": "tool",
                        "tool": name,
                        "status": "error",
                        "message": "已拒绝执行",
                        "command": command,
                        "result": {"command": command},
                        "session_id": ctx.session_id,
                        "call_id": call_id,
                    }
                )
                return json.dumps(
                    {
                        "success": False,
                        "message": "用户拒绝了终端命令执行",
                        "command": command,
                        "rejected": True,
                    },
                    ensure_ascii=False,
                )

        write_calendar_allowed = False
        if (
            name == "schedule_task"
            and str(arguments.get("action") or "") == "create"
        ):
            decision = _ask_interrupt(
                ctx.session_id,
                f"write_calendar:{call_id}",
                {
                    "type": "write_calendar",
                    "session_id": ctx.session_id,
                    "tool": "schedule_task",
                    "message": "创建提醒后是否同时写入日程？",
                    "action": "create",
                    "call_id": call_id,
                },
            )
            write_calendar_allowed = (
                bool(decision.get("allowed"))
                if isinstance(decision, dict)
                else bool(decision)
            )

        writer(
            {
                "event": "tool",
                "tool": name,
                "status": "running",
                "message": f"正在调用 {name}",
                "command": command if is_terminal else None,
                "call_id": call_id,
            }
        )
        output = await _execute_tool(
            ctx.session_id, adapter, name, arguments, ctx.workspace
        )
        tool_content = output.get("content") or json.dumps(
            output, ensure_ascii=False
        )
        payload: dict[str, Any] = {
            "event": "tool",
            "tool": name,
            "status": "done" if output.get("success") else "error",
            "message": output.get("message", "执行完成"),
            "result": _frontend_tool_result(output),
            "call_id": call_id,
        }
        if is_terminal:
            payload["command"] = command
        writer(payload)

        if (
            name == "schedule_task"
            and str(arguments.get("action") or "") == "create"
            and output.get("success")
        ):
            writer(
                {
                    "event": "scheduled_tasks_changed",
                    "tasks": db.list_scheduled_tasks(),
                }
            )
            calendar_pending = (
                (output.get("data") or {}).get("task") or output
            )
            if write_calendar_allowed:
                writer(
                    {
                        "event": "tool",
                        "tool": "schedule_task",
                        "status": "done",
                        "message": "已确认写入日程",
                        "session_id": ctx.session_id,
                        "result": calendar_pending,
                    }
                )
                task_id = str(calendar_pending.get("id") or "")
                title = str(
                    calendar_pending.get("title")
                    or calendar_pending.get("message")
                    or "定时任务"
                )
                tool_content = json.dumps(
                    {
                        "success": True,
                        "message": (
                            f"提醒“{title}”已创建，用户同意写入日程。"
                            "请立即调用 write_calendar 创建日程，"
                            f"task_id 传 {task_id}，"
                            "标题和起止时间按该提醒的信息填写。"
                        ),
                        "data": calendar_pending,
                    },
                    ensure_ascii=False,
                )
            else:
                writer(
                    {
                        "event": "tool",
                        "tool": "schedule_task",
                        "status": "done",
                        "message": "不写入日程",
                        "session_id": ctx.session_id,
                        "result": calendar_pending,
                    }
                )

        if name == "write_calendar" and output.get("success"):
            writer(
                {
                    "event": "calendar_events_changed",
                    "events": db.list_calendar_events(),
                }
            )

        if todo is not None:
            _finish_todo(
                todo,
                bool(output.get("success")),
                str(output.get("message") or ""),
            )
            writer(
                {
                    "event": "todo_update",
                    "id": todo["id"],
                    "status": todo["status"],
                }
            )

        return tool_content
    except Exception:
        if todo is not None:
            _finish_todo(todo, False, "工具执行异常")
            writer(
                {
                    "event": "todo_update",
                    "id": todo["id"],
                    "status": todo["status"],
                }
            )
        raise


def _make_tool_call(
    ctx: AgentRunContext,
    adapter: Any,
    name: str,
    lock: asyncio.Lock,
):
    async def call(runtime: ToolRuntime, **kwargs: Any) -> Any:
        async with lock:
            return await _handle_adapter_call(
                ctx, runtime, adapter, name, kwargs
            )

    return call


def _build_tools(ctx: AgentRunContext) -> list[StructuredTool]:
    tools: list[StructuredTool] = []
    skill_registry.refresh(ctx.workspace)
    lock = _TOOL_LOCKS.setdefault(ctx.session_id, asyncio.Lock())
    for meta in registry.list():
        if meta["name"] == "create_plan":
            continue
        adapter = registry.get(meta["name"])
        if adapter is None:
            continue
        args_model = _make_args_model(meta["name"], meta["parameters"])
        tools.append(
            StructuredTool.from_function(
                coroutine=_make_tool_call(
                    ctx, adapter, meta["name"], lock
                ),
                name=meta["name"],
                description=meta["description"],
                args_schema=args_model,
            )
        )

    for skill in skill_registry.executable_skills():
        if skill.script_path is None:
            continue
        tool_name = _skill_tool_name(skill.name)
        if skill.script_mode == "json":
            description = (
                f"执行能力型技能 {skill.name} 的 script.py。"
                f"{skill.description} 参数 params 通过 stdin JSON 传给脚本。"
            )
        else:
            description = (
                f"执行能力型技能 {skill.name} 的脚本。"
                f"{skill.description} args 为传给脚本的命令行参数列表。"
            )

        async def _call_skill(
            params: dict[str, Any] | None = None,
            args: list[str] | None = None,
            timeout: int | None = None,
            _meta: Any = skill,
            _mode: str = skill.script_mode,
        ) -> Any:
            return await asyncio.to_thread(
                _run_skill_script,
                _meta.script_path,
                _meta.dir,
                _mode,
                params,
                args,
                timeout,
            )

        tools.append(
            StructuredTool.from_function(
                coroutine=_call_skill,
                name=tool_name,
                description=description,
                args_schema=_skill_args_model(skill.name, skill.script_mode),
            )
        )

    async def _load_skill(name: str) -> str:
        return skill_registry.load(name)

    tools.append(
        StructuredTool.from_function(
            coroutine=_load_skill,
            name="load_skill",
            description=(
                "按需加载已安装技能的完整指令和参考资料。"
                "技能名必须是 system prompt 中可用技能列表里的名称。"
            ),
        )
    )
    return tools


def _build_agent(
    llm: Any, tools: list[StructuredTool], ctx: AgentRunContext
) -> Any:
    return create_agent(
        model=llm,
        tools=tools,
        middleware=[
            _build_dynamic_prompt(ctx),
            ModelCallLimitMiddleware(
                run_limit=MAX_TOOL_TURNS,
                exit_behavior="end",
            ),
            ToolCallLimitMiddleware(
                run_limit=MAX_TOOL_TURNS,
                exit_behavior="end",
            ),
            HumanInTheLoopMiddleware(
                interrupt_on={
                    "write_todos": {
                        "allowed_decisions": ["approve", "reject"],
                        "when": lambda request: not ctx.plan_approved
                        and (
                            ctx.plan_first_pending
                            or _should_ask_plan(
                                request.state.get("messages") or []
                            )
                        ),
                    }
                }
            ),
            TodoSyncMiddleware(ctx),
            TodoListMiddleware(),
            ToolErrorMiddleware(
                on_error=lambda exc, request: (
                    f"工具执行异常: {type(exc).__name__}: {str(exc)[:300]}"
                )
            ),
        ],
        checkpointer=_CHECKPOINTER,
    )


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
                "skill_install": payload.get("repo_preview") or {},
                "target": payload.get("target") or "project",
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
    message: Any, queue: asyncio.Queue[tuple[str, Any]]
) -> tuple[Any, str]:
    text_parts: list[str] = []
    reasoning_parts: list[str] = []

    async def drain_text() -> None:
        async for delta in message.text:
            text_parts.append(delta)
            await queue.put(
                ("sse", sse_event("message", {"content": delta}))
            )

    async def drain_reasoning() -> None:
        async for delta in message.reasoning:
            reasoning_parts.append(delta)
            await queue.put(
                ("sse", sse_event("think", {"content": delta}))
            )

    output_future = asyncio.ensure_future(message.output)
    await asyncio.gather(drain_text(), drain_reasoning())
    output = await output_future
    return output, "".join(reasoning_parts)


async def _stream_agent_run(
    agent: Any,
    graph_input: Any,
    config: dict[str, Any],
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
                output, reasoning = await _consume_message(message, queue)
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


async def run_agent(
    session_id: str,
    history: list[dict[str, Any]],
    think: bool,
    workspace: Any,
    approval_mode: str = "ask",
) -> AsyncIterator[str]:
    workspace_path = workspace if isinstance(workspace, Path) else Path(workspace)
    ctx = AgentRunContext(
        session_id=session_id,
        workspace=workspace_path,
        approval_mode=approval_mode,
    )
    session = db.get_session(session_id)
    plan_mode = (session or {}).get("plan_mode") or "ask"
    if plan_mode == "direct":
        ctx.plan_choice_resolved = True
        ctx.plan_approved = True
    elif plan_mode == "plan_first":
        ctx.plan_choice_resolved = True
        ctx.plan_first_pending = True
    llm = _build_llm()
    tools = _build_tools(ctx)
    agent = _build_agent(llm, tools, ctx)
    config = {
        "configurable": {"thread_id": session_id},
        "recursion_limit": 256,
    }

    snapshot = await agent.aget_state(config)
    has_thread = bool((snapshot.values or {}).get("messages"))
    if has_thread:
        user_messages = [
            message
            for message in history
            if message.get("role") == "user"
        ]
        last_user = user_messages[-1] if user_messages else history[-1]
        input_messages = convert_to_messages([last_user])
    else:
        input_messages = convert_to_messages(history)
    logger.info(
        "agent start session=%s history=%d thread=%s",
        session_id,
        len(history),
        has_thread,
    )

    graph_input: Any = {"messages": input_messages}
    final_state: dict[str, Any] | None = None
    think_by_id: dict[str, str] = {}
    try:
        while True:
            interrupted = False
            async for kind, data in _stream_agent_run(
                agent, graph_input, config
            ):
                if kind == "sse":
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
        )
        return

    if final_state is None:
        yield error_event("agent_error", "Agent 未返回结果")
        return

    messages = final_state.get("messages") or []
    _sync_todos_from_state(session_id, final_state)
    _persist_new_messages(session_id, input_messages, messages, think_by_id)
    final_content = _extract_final_content(messages)
    yield sse_event(
        "done",
        {
            "message": "回答完成",
            "content": final_content,
        },
    )
    logger.info(
        "agent done session=%s content_len=%d",
        session_id,
        len(final_content),
    )
