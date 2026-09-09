"""LangChain tool and agent construction."""

from __future__ import annotations

import asyncio
import logging
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

from ...skills import skill_registry
from ...tools.registry import registry
from ..core import MAX_TOOL_TURNS, _READ_ONLY_TOOLS
from ..core import AgentRunContext
from .execution import _handle_adapter_call
from ..middleware import TodoSyncMiddleware, TurnCounterMiddleware, UserInjectionMiddleware
from ..core.prompts import _build_dynamic_prompt, _should_ask_plan
from ..core import _make_args_model, _run_skill_script, _skill_args_model, _skill_tool_name

_CHECKPOINTER = InMemorySaver()

logger = logging.getLogger("divine.agent.tools")

_TOOL_LOCKS: dict[str, asyncio.Lock] = {}

# 免锁（可并行执行）的工具 = 只读工具 + 明确无副作用的辅助工具。
# lint_check 只读分析；run_tests 会跑项目代码（可能占端口/写缓存），保持加锁。
_LOCK_FREE_TOOLS: frozenset[str] = frozenset(
    _READ_ONLY_TOOLS | {"glob_files", "list_definitions", "lint_check", "load_skill", "review_changes"}
)

# 内容创作/技能类工具：仅当对应意图命中时注入（其余工具常驻）。
# 这类工具 schema 大（pdf_generate 889 token、run_subagents 738 等）且只服务
# 特定意图——按意图裁减可显著降低每次云端调用的 input token
# （60 个全带 ≈ 13.3k，意图=question 时裁到 ≈ 7k）。
# 保守原则：只裁"纯内容创作 + 技能 + 子 agent"，文件/代码/网络/终端等
# 干活主力工具一律常驻，避免意图漏判导致工具缺失。
# 值可为 str（单意图）或 tuple（任一命中即注入）。注意多轮创作常以短追问出现
# （"换个主题色重一份"），该轮意图常只命中 html——pdf_generate 必须随
# html/resume 一并放行，否则模型在追问轮拿不到简历/PDF 管线，被迫手写 HTML。
_CONTENT_TOOLS: dict[str, str | tuple[str, ...]] = {
    "pdf_generate": ("pdf", "resume", "html"),
    "html_resume": ("resume", "html", "pdf"),
    "html_common": ("html", "resume"),
    "pdf_render": "pdf",
    "pdf_split_merge": "pdf",
    "word_document": "document",
    "presentation": "document",
    "spreadsheet": "document",
    "image_generate": "image",
    "image_resize": "image",
    # draw_svg 放宽到 svg + mermaid：架构图首轮走 mermaid 正文输出（不调工具），
    # 追问轮"要 SVG 版"意图仍判 mermaid 时，draw_svg 必须可用，否则模型拿不到工具。
    "draw_svg": ("svg", "mermaid"),
    "edit_svg": "svg",
    "describe_svg": "svg",
    "svg_to_png": "svg",
    "svg_to_png_batch": "svg",
    "generate_chart": "chart",
    "mermaid_export": "mermaid",
    "ux_html": "ux",
    "install_skill": "skill",
    "migrate_skill": "skill",
    "migrate_skills": "skill",
    "discover_importable_skills": "skill",
    "preview_skill_repo": "skill",
    "run_subagents": "subagent",
}


def _make_tool_call(
    ctx: AgentRunContext,
    adapter: Any,
    name: str,
    lock: asyncio.Lock | None,
):
    """Wrap one adapter for the LangGraph tool node.

    ``lock`` 为 None 时（只读工具）不加锁：LangGraph 对同一条 AI 消息里的
    多个 tool_calls 并发执行，只读工具并行可以显著降低探索阶段的延迟；
    可变工具（写文件/终端/git 写等）仍串行，避免并发改动互相踩踏。
    """

    async def call(runtime: ToolRuntime, **kwargs: Any) -> Any:
        if lock is None:
            return await _handle_adapter_call(
                ctx, runtime, adapter, name, kwargs
            )
        async with lock:
            return await _handle_adapter_call(
                ctx, runtime, adapter, name, kwargs
            )

    return call

def _content_tool_allowed(name: str, intents: set[str] | frozenset[str]) -> bool:
    """意图裁剪判定：无门槛工具恒注入；有门槛时任一意图命中即注入。

    intents 为空视为无信号，全量放行（首轮兜底）。
    """
    required = _CONTENT_TOOLS.get(name)
    if not required:
        return True
    if not intents:
        return True
    needed = {required} if isinstance(required, str) else set(required)
    return bool(needed & intents)


def _build_tools(ctx: AgentRunContext) -> list[StructuredTool]:
    """Build the full tool set for a session, including installed skills."""
    tools: list[StructuredTool] = []
    skill_registry.refresh(ctx.workspace)
    lock = _TOOL_LOCKS.setdefault(ctx.session_id, asyncio.Lock())
    intents = ctx.intents
    for meta in registry.list():
        name = meta["name"]
        if name == "create_plan":
            continue
        # 意图工具裁减：内容创作/技能类工具仅当对应意图命中时注入。
        if not _content_tool_allowed(name, intents):
            continue
        adapter = registry.get(meta["name"])
        if adapter is None:
            continue
        args_model = _make_args_model(meta["name"], meta["parameters"])
        tools.append(
            StructuredTool.from_function(
                coroutine=_make_tool_call(
                    ctx,
                    adapter,
                    meta["name"],
                    None if name in _LOCK_FREE_TOOLS else lock,
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

    # MCP 外部工具（动态注入）：执行/审批/持久化复用同一条 adapter 管线，
    # 会话级锁不加（网络 IO，且单 server 内部由 keeper 任务天然串行）。
    try:
        from ...mcp.adapter import McpToolAdapter
        from ...mcp.manager import mcp_manager

        for info in mcp_manager.snapshot_tools():
            adapter = McpToolAdapter(info)
            description = (
                f"[MCP:{info.server_name}] {info.description or info.tool_name}。"
                "来自外部 MCP 服务器，调用前确认参数与该服务器的能力描述一致。"
            )
            tools.append(
                StructuredTool.from_function(
                    coroutine=_make_tool_call(ctx, adapter, info.key, None),
                    name=info.key,
                    description=description[:1000],
                    args_schema=_make_args_model(info.key, info.input_schema),
                )
            )
    except Exception:  # noqa: BLE001 — MCP 不可用绝不影响本地工具
        logger.exception("MCP 工具注入失败")
    return tools

async def reset_agent_thread(thread_id: str) -> None:
    from ..core.checkpointer import get_checkpointer

    saver = await get_checkpointer()
    await saver.adelete_thread(thread_id)

def _build_agent(
    llm: Any,
    tools: list[StructuredTool],
    ctx: AgentRunContext,
    checkpointer: Any = None,
) -> Any:
    """Build the LangGraph agent with prompts, limits, and approval middleware.

    checkpointer 缺省用 InMemorySaver（测试/子代理场景）；主对话线程由
    orchestrator 传入 get_checkpointer() 的 SqliteSaver，线程态跨重启保留。
    """
    middleware = [
        TurnCounterMiddleware(ctx),
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
        UserInjectionMiddleware(ctx),
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
        checkpointer=checkpointer or _CHECKPOINTER,
    )
