"""Parallel sub-agent execution for the main agent.

The main agent delegates a batch of independent sub-tasks to this module via
the ``run_subagents`` meta tool. Each sub-agent runs its own LangGraph agent
with an isolated thread (fresh checkpointer + unique thread id), a read-only
tool allowlist, and its own system prompt. Results are aggregated back into a
JSON payload the main agent summarizes into its final answer.

Lifecycle / SSE contract (see docs/subagent-feature-design.md):
- ``subagent`` events carry ``sub_id`` / ``name`` / ``status`` and either
  ``summary`` (done) or ``error`` (error); the frontend upserts them into a
  collapsible progress panel on the assistant message.
- Sub-agent internal tool calls do NOT emit ``tool`` events and are NOT
  persisted to ``tool_runs``; only the ``run_subagents`` batch itself is a
  persisted tool run.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolErrorMiddleware,
)
from langchain_core.messages import HumanMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver

from .. import db
from ..localization import language_instruction
from ..skills import skill_registry
from ..tools.registry import registry
from .context import AgentRunContext, canonical_path
from .llm import _build_llm
from .persistence import _extract_final_content
from .schema import _make_args_model

logger = logging.getLogger("divine.agent.subagents")

MAX_SUBAGENTS = 8
MAX_SUBAGENT_PARALLEL = 4
SUBAGENT_MAX_TOOL_TURNS = 16
SUBAGENT_TIMEOUT = 180
SUBAGENT_SUMMARY_CAP = 800
SUBAGENT_OUTPUT_CAP = 12000

# Registry tools allowed for sub-agents by default (read-only analysis).
_SUBAGENT_READ_ONLY_TOOLS = frozenset(
    {
        "read_file",
        "read_image",
        "search_files",
        "directory_tree",
        "rag_search",
        "sqlite_query",
        "calculator",
        "web_fetch",
        "web_fetch_batch",
        "generate_chart",
        "describe_svg",
    }
)

# Tools that are NEVER available to sub-agents, even when listed in the
# per-task `tools` allowlist (v1 hard constraint: sub-agents stay read-only).
_SUBAGENT_FORBIDDEN_TOOLS = frozenset(
    {
        "terminal",
        "edit_files",
        "write_file",
        "notes",
        "word_document",
        "spreadsheet",
        "presentation",
        "pdf_generate",
        "pdf_render",
        "pdf_split_merge",
        "schedule_task",
        "write_calendar",
        "remember",
        "forget_memory",
        "migrate_skill",
        "migrate_skills",
        "install_skill",
        "preview_skill_repo",
        "discover_importable_skills",
        "create_plan",
        "write_todos",
        "run_subagents",
    }
)

SUBAGENT_SYSTEM_PROMPT = """你是 Divine 的并行子 Agent，负责独立完成分配给你的一个子任务。
规则：
- 只能使用下方提供的工具；没有工具可完成时直接输出已有结论，不要编造工具。
- 不要请求用户确认，不要询问问题，不要输出方案。
- 直接输出任务要求的结论。
- 输出保持简洁：要点列表优先，不要长篇大论。"""


def _validate_tasks(arguments: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    """Validate the run_subagents arguments; return (tasks, error)."""
    raw_tasks = arguments.get("tasks") or []
    if not isinstance(raw_tasks, list) or not raw_tasks:
        return [], "run_subagents 的 tasks 参数必须是非空数组"
    if len(raw_tasks) < 2:
        return [], "run_subagents 至少需要 2 个子任务；单个子任务请直接在主对话中完成"
    if len(raw_tasks) > MAX_SUBAGENTS:
        return [], f"一次最多委托 {MAX_SUBAGENTS} 个子任务"
    tasks: list[dict[str, Any]] = []
    for index, item in enumerate(raw_tasks):
        if not isinstance(item, dict):
            return [], f"第 {index + 1} 个子任务必须是对象"
        task_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        prompt = str(item.get("prompt") or "").strip()
        if not task_id or not name or not prompt:
            return [], f"第 {index + 1} 个子任务缺少 id / name / prompt"
        tools = item.get("tools")
        if tools is not None and not isinstance(tools, list):
            return [], f"子任务 {task_id} 的 tools 必须是数组"
        tasks.append(
            {
                "id": task_id,
                "name": name,
                "prompt": prompt,
                "tools": tools if isinstance(tools, list) else None,
            }
        )
    return tasks, None


async def _run_subagent_tool(
    ctx: AgentRunContext,
    adapter: Any,
    name: str,
    arguments: dict[str, Any],
) -> str:
    """Execute one read-only tool for a sub-agent, without approvals or SSE.

    External paths outside ``approved_paths`` are rejected automatically.
    Returns the same string content contract as the main agent's tool calls.
    """
    external_paths = adapter.external_paths(ctx.workspace, arguments)
    denied = [
        path
        for path in external_paths
        if canonical_path(path, ctx.workspace) not in ctx.approved_paths
    ]
    if denied:
        return json.dumps(
            {
                "success": False,
                "message": "子 Agent 无权访问外部路径",
                "paths": denied[:5],
                "rejected": True,
            },
            ensure_ascii=False,
        )
    try:
        output = await asyncio.wait_for(
            adapter.run(
                ctx.workspace,
                arguments,
                locale=ctx.locale,
            ),
            timeout=adapter.timeout,
        )
        result = output.as_dict()
    except asyncio.TimeoutError:
        result = {
            "success": False,
            "message": f"工具执行超时（{adapter.timeout}s）",
        }
    except Exception as exc:  # noqa: BLE001 — surface tool errors to the model
        logger.warning(
            "subagent tool error name=%s: %s", name, exc, exc_info=True
        )
        result = {"success": False, "message": f"工具执行失败: {type(exc).__name__}"}
    content = result.get("content")
    if content is None:
        content = json.dumps(result, ensure_ascii=False)
    return str(content)


def _build_subagent_tools(
    ctx: AgentRunContext,
    allowlist: list[str] | None,
    lock: asyncio.Lock,
) -> list[StructuredTool]:
    """Build the restricted read-only toolset for one sub-agent.

    ``allowlist`` narrows the default set; forbidden tools are always removed.
    Each sub-agent gets its own lock so parallel sub-agents do not serialize
    on the main session lock.
    """
    tools: list[StructuredTool] = []
    for meta in registry.list():
        name = meta["name"]
        if name in _SUBAGENT_FORBIDDEN_TOOLS:
            continue
        if name not in _SUBAGENT_READ_ONLY_TOOLS:
            continue
        if allowlist and name not in allowlist:
            continue
        adapter = registry.get(name)
        if adapter is None:
            continue
        args_model = _make_args_model(name, meta["parameters"])

        async def call(
            runtime: Any, _adapter: Any = adapter, _name: str = name, **kwargs: Any
        ) -> Any:
            async with lock:
                return await _run_subagent_tool(ctx, _adapter, _name, kwargs)

        tools.append(
            StructuredTool.from_function(
                coroutine=call,
                name=name,
                description=meta["description"],
                args_schema=args_model,
            )
        )
    # load_skill: knowledge skills only (read-only).
    skill_registry.refresh(ctx.workspace)
    for skill in skill_registry.knowledge_skills():
        if allowlist and "load_skill" not in allowlist:
            continue

        async def call_load(name: str = skill.name) -> str:
            return skill_registry.load(name)

        tools.append(
            StructuredTool.from_function(
                coroutine=call_load,
                name="load_skill",
                description=(
                    "按需加载已安装技能的完整指令和参考资料。"
                    "技能名必须是可用技能列表里的名称。"
                ),
            )
        )
        break
    return tools


async def _run_subagent(
    ctx: AgentRunContext, task: dict[str, Any]
) -> dict[str, Any]:
    """Run one sub-task as an isolated agent; return its result payload."""
    task_id = str(task["id"])
    start = time.monotonic()
    sub_ctx = AgentRunContext(
        session_id=ctx.session_id,
        workspace=ctx.workspace,
        approval_mode="assist",
        locale=ctx.locale,
        approved_paths=ctx.approved_paths,
        think=ctx.think,
        effort=ctx.effort,
        model_id=ctx.model_id,
        cancel_event=ctx.cancel_event,
    )
    lock = asyncio.Lock()
    try:
        llm = _build_llm(think=ctx.think, effort=ctx.effort, model_id=ctx.model_id)
        tools = _build_subagent_tools(sub_ctx, task.get("tools"), lock)
        language = language_instruction(ctx.locale)
        system_prompt = (
            f"{SUBAGENT_SYSTEM_PROMPT}\n\n{language}\n\n"
            f"当前会话所属项目工作目录：{ctx.workspace}\n"
            "请以该目录作为资料检索和文件读取的工作区。"
        )
        agent = create_agent(
            model=llm,
            tools=tools,
            system_prompt=system_prompt,
            middleware=[
                ModelCallLimitMiddleware(
                    run_limit=SUBAGENT_MAX_TOOL_TURNS,
                    exit_behavior="end",
                ),
                ToolErrorMiddleware(
                    on_error=lambda exc, request: (
                        f"工具执行异常: {type(exc).__name__}: {str(exc)[:300]}"
                    )
                ),
            ],
            checkpointer=InMemorySaver(),
            name=f"subagent-{task_id}",
        )
        config = {
            "configurable": {"thread_id": f"{ctx.session_id}:sub:{task_id}"},
            "recursion_limit": SUBAGENT_MAX_TOOL_TURNS * 2,
        }
        result = await asyncio.wait_for(
            agent.ainvoke(
                {"messages": [HumanMessage(content=task["prompt"])]},
                config,
            ),
            timeout=SUBAGENT_TIMEOUT,
        )
        messages = result.get("messages") or []
        output_text = _extract_final_content(messages) or ""
        summary = output_text[:SUBAGENT_SUMMARY_CAP]
        return {
            "id": task_id,
            "name": task["name"],
            "status": "done",
            "summary": summary,
            "output": output_text[:SUBAGENT_OUTPUT_CAP],
            "duration": round(time.monotonic() - start, 1),
        }
    except asyncio.TimeoutError:
        logger.warning("subagent timeout id=%s duration=%.1fs", task_id, time.monotonic() - start)
        return {
            "id": task_id,
            "name": task["name"],
            "status": "error",
            "error": f"子 Agent 执行超时（{SUBAGENT_TIMEOUT}s）",
            "duration": round(time.monotonic() - start, 1),
        }
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 — a failing sub-task must not kill the batch
        logger.warning("subagent error id=%s: %s", task_id, exc, exc_info=True)
        return {
            "id": task_id,
            "name": task["name"],
            "status": "error",
            "error": f"子 Agent 执行失败: {type(exc).__name__}: {str(exc)[:200]}",
            "duration": round(time.monotonic() - start, 1),
        }


async def _run_subagents(
    ctx: AgentRunContext,
    runtime: Any,
    arguments: dict[str, Any],
) -> str:
    """Execute a run_subagents batch and return the aggregated JSON payload."""
    tasks, error = _validate_tasks(arguments)
    writer = getattr(runtime, "stream_writer", None)
    call_id = getattr(runtime, "tool_call_id", None) or f"call_{time.monotonic_ns()}"
    session_id = ctx.session_id

    def emit(kind: str, payload: dict[str, Any]) -> None:
        if writer is None:
            return
        writer({"event": kind, "session_id": session_id, **payload})

    if error:
        payload = json.dumps(
            {"success": False, "message": error}, ensure_ascii=False
        )
        emit(
            "tool",
            {
                "tool": "run_subagents",
                "status": "error",
                "message": error,
                "call_id": call_id,
                "session_id": session_id,
            },
        )
        return payload

    # Persist the batch itself as a tool run so the frontend can restore the
    # panel from history; sub-agent internal tool calls are not persisted.
    run = db.add_tool_run(session_id, "run_subagents", "start", arguments)

    max_parallel = max(
        1,
        min(
            int(arguments.get("max_parallel") or MAX_SUBAGENT_PARALLEL),
            MAX_SUBAGENT_PARALLEL,
        ),
    )
    emit(
        "tool",
        {
            "tool": "run_subagents",
            "status": "running",
            "message": f"正在并行执行 {len(tasks)} 个子任务",
            "messageKey": "tool.subagentsRunning",
            "messageParams": {"count": len(tasks)},
            "call_id": call_id,
            "session_id": session_id,
        },
    )
    for task in tasks:
        emit(
            "subagent",
            {
                "sub_id": task["id"],
                "name": task["name"],
                "status": "running",
            },
        )

    semaphore = asyncio.Semaphore(max_parallel)

    async def run_one(task: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            if ctx.cancel_event is not None and ctx.cancel_event.is_set():
                return {
                    "id": task["id"],
                    "name": task["name"],
                    "status": "error",
                    "error": "已取消",
                }
            return await _run_subagent(ctx, task)

    async def _run_batch() -> list[dict[str, Any]]:
        return await asyncio.gather(*(run_one(task) for task in tasks))

    batch = asyncio.create_task(_run_batch())
    if ctx.cancel_event is not None:
        cancel_waiter = asyncio.create_task(ctx.cancel_event.wait())
        done, _ = await asyncio.wait(
            {batch, cancel_waiter}, return_when=asyncio.FIRST_COMPLETED
        )
        if batch not in done:
            batch.cancel()
            logger.info("subagent batch cancelled session=%s", session_id)
            results = [
                {
                    "id": task["id"],
                    "name": task["name"],
                    "status": "error",
                    "error": "已取消",
                }
                for task in tasks
            ]
            try:
                await batch
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        else:
            results = batch.result()
        cancel_waiter.cancel()
    else:
        results = await batch

    done_count = sum(1 for item in results if item.get("status") == "done")
    failed_count = len(results) - done_count
    for item in results:
        if item.get("status") == "done":
            emit(
                "subagent",
                {
                    "sub_id": item["id"],
                    "name": item["name"],
                    "status": "done",
                    "summary": item.get("summary") or "",
                },
            )
        else:
            emit(
                "subagent",
                {
                    "sub_id": item["id"],
                    "name": item["name"],
                    "status": "error",
                    "error": item.get("error") or "子 Agent 执行失败",
                },
            )

    summary_message = (
        f"{len(tasks)} 个子任务完成，{failed_count} 个失败"
        if failed_count
        else f"{len(tasks)} 个子任务全部完成"
    )
    emit(
        "tool",
        {
            "tool": "run_subagents",
            "status": "done" if done_count else "error",
            "message": summary_message,
            "messageKey": "tool.subagentsDone" if done_count else None,
            "messageParams": (
                {"done": done_count, "failed": failed_count} if done_count else {}
            ),
            "result": {"subagents": results},
            "call_id": call_id,
            "session_id": session_id,
        },
    )
    output_payload = {
        "success": bool(done_count),
        "message": summary_message,
        "results": results,
    }
    try:
        db.update_tool_run(
            run["id"],
            "done" if done_count else "error",
            output_payload,
        )
    except Exception:  # noqa: BLE001 — persistence must never fail a turn
        logger.exception("persist subagent batch failed session=%s", session_id)
    return json.dumps(output_payload, ensure_ascii=False)


__all__ = ["_run_subagents", "_validate_tasks", "SUBAGENT_SYSTEM_PROMPT"]
