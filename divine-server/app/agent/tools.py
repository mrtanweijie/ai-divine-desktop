"""LangChain tool and agent construction."""

from __future__ import annotations

import asyncio
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
    TodoListMiddleware,
    ToolErrorMiddleware,
)
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import ToolRuntime

from ..skills import skill_registry
from ..tools.registry import registry
from .constants import MAX_TOOL_TURNS
from .context import AgentRunContext
from .execution import _handle_adapter_call
from .middleware import TodoSyncMiddleware
from .prompts import _build_dynamic_prompt, _should_ask_plan
from .schema import _make_args_model, _run_skill_script, _skill_args_model, _skill_tool_name

_CHECKPOINTER = InMemorySaver()

_TOOL_LOCKS: dict[str, asyncio.Lock] = {}

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
    """Build the full tool set for a session, including installed skills."""
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

async def reset_agent_thread(thread_id: str) -> None:
    await _CHECKPOINTER.adelete_thread(thread_id)

def _build_agent(
    llm: Any, tools: list[StructuredTool], ctx: AgentRunContext
) -> Any:
    """Build the LangGraph agent with prompts, limits, and approval middleware."""
    middleware = [
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
    ]
    if ctx.tool_mode == "react":
        # Outermost wrapper: strips tools from the model binding and turns
        # the text ReAct trace into standard tool_calls. Everything below
        # (limits, approval, todo sync, error handling) runs unchanged.
        from .react import ReActParseMiddleware

        middleware.insert(0, ReActParseMiddleware())
    return create_agent(
        model=llm,
        tools=tools,
        middleware=middleware,
        checkpointer=_CHECKPOINTER,
    )
