"""Dynamic prompts, RAG context, skill catalog, and plan-asking heuristics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain.agents.middleware import ModelRequest, dynamic_prompt
from langchain_core.messages import HumanMessage, ToolMessage

from .. import db
from ..config import settings_store
from ..localization import language_instruction
from ..skills import skill_registry
from .constants import SYSTEM_PROMPT
from .context import AgentRunContext
from .plans import _plan_progress
from .rag import _auto_rag_context
from .schema import _content_text, _skill_tool_name

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
            language_instruction(ctx.locale),
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
