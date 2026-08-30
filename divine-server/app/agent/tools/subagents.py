"""Parallel sub-agent execution for the main agent.

The main agent delegates a batch of independent sub-tasks to this module via
the ``run_subagents`` meta tool. Each sub-agent runs its own LangGraph agent
with an isolated thread (fresh checkpointer + unique thread id), a restricted
tool set, and its own system prompt. Results are aggregated back into a JSON
payload the main agent summarizes into its final answer.

Write capability (v2): a task with ``write: true`` and ``write_paths`` may
create/modify files, but only inside its declared paths. Claims are validated
up front (must be inside the workspace, must not overlap between tasks), the
user approves the whole write batch BEFORE dispatch (in execution.py), and
every write is captured as a before/after diff returned to the main agent.

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
import difflib
import json
import logging
import time
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolErrorMiddleware,
)
from langchain_core.messages import HumanMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError

from ... import db
from ...localization import language_instruction
from ...skills import skill_registry
from ...tools.registry import registry
from ..core import AgentRunContext, canonical_path
from ..core import _build_llm
from ..state import _extract_final_content
from ..core import _make_args_model

logger = logging.getLogger("divine.agent.subagents")

MAX_SUBAGENTS = 8
MAX_SUBAGENT_PARALLEL = 4
# 调研/分析类子任务（如多来源网页调研）需要较多模型回合；
# 16 次对“国内AI服务定价调研”这类多厂商任务不够，24 次仍远低于主 Agent 的 96 次。
SUBAGENT_MAX_TOOL_TURNS = 24
# LangGraph 的 recursion_limit 统计的是图里的 super-step：模型调用和每次工具执行
# 各算一步。研究类子任务一个回合常连续调用多个工具（多次搜索/抓取），
# 2 倍余量会在模型调用上限触发前就抛 GraphRecursionError。
# 6 倍余量（144 步）给足“每回合多次工具调用”的空间，
# 让 ModelCallLimitMiddleware 的 24 次上限成为真正的工作量闸门。
SUBAGENT_RECURSION_LIMIT = SUBAGENT_MAX_TOOL_TURNS * 6
SUBAGENT_TIMEOUT = 180
SUBAGENT_SUMMARY_CAP = 800
SUBAGENT_OUTPUT_CAP = 12000

# Write tools available to write-capable sub-agents (opt-in via write=true).
_SUBAGENT_WRITE_TOOLS = frozenset({"write_file", "edit_files"})
# Verification tools available to terminal-enabled sub-agents (opt-in via
# terminal=true). These route through the terminal command policy already.
_SUBAGENT_COMMAND_TOOLS = frozenset(
    {"lint_check", "run_tests", "format_code"}
)
_SUBAGENT_CHANGE_CAP = 50
_SUBAGENT_DIFF_CAP = 4000

# Registry tools allowed for sub-agents by default (read-only analysis).
_SUBAGENT_READ_ONLY_TOOLS = frozenset(
    {
        "read_file",
        "read_image",
        "search_files",
        "grep_files",
        "glob_files",
        "directory_tree",
        "rag_search",
        "sqlite_query",
        "calculator",
        "web_fetch",
        "web_fetch_batch",
        "web_search",
        "generate_chart",
        "describe_svg",
        "git_status",
        "git_diff",
        "git_log",
        # Knowledge-skill loading is read-only; appended by name below.
        "load_skill",
    }
)

# Tools that are NEVER available to sub-agents, even when listed in the
# per-task `tools` allowlist. "terminal" is special: it stays forbidden by
# default but can be enabled per task via terminal=true, in which case only
# safe-policy commands (terminal_command_policy == "safe") actually run.
_SUBAGENT_FORBIDDEN_TOOLS = frozenset(
    {
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
        "undo_last_turn",
    }
)

SUBAGENT_SYSTEM_PROMPT = """你是 Divine 的并行子 Agent，负责独立完成分配给你的一个子任务。
规则：
- 只能使用下方提供的工具；没有工具可完成时直接输出已有结论，不要编造工具。
- 不要请求用户确认，不要询问问题，不要输出方案。
- 直接输出任务要求的结论。
- 输出保持简洁：要点列表优先，不要长篇大论。
- 网页调研先用 web_search 搜索获取线索（标题/链接/摘要），
  再对搜索结果中的具体页面用 web_fetch_batch 一次抓取多个 URL，不要逐个 web_fetch；
  同一 URL 抓取失败不要反复重试，换一个来源或直接基于已有信息输出结论。
- 资料足够支撑结论时立即结束，不要为了“全面”继续抓取更多页面。
如果本子任务启用了写工具（write_file / edit_files）：
- 只能创建或修改任务声明范围内（write_paths）的文件，禁止写入范围外路径；越界写入会被系统拒绝。
- 保持改动最小：只改任务要求的部分，不要重写无关代码；创建新文件用 write_file（search 传空）。
- 完成后在输出末尾列出修改过的文件与每个文件的改动摘要（新增/修改，各改了什么）。
如果本子任务启用了终端（terminal / lint_check / run_tests / format_code）：
- 优先用 run_tests 跑测试、lint_check 做静态检查、format_code 格式化，不要直接用 terminal。
- terminal 只能执行安全只读命令（python3 -m pytest、npx tsc --noEmit 等）；
  需要确认或高危的命令会被系统直接拒绝，不要重试，在结果中说明即可。"""


def _resolve_write_claims(
    workspace: Path, raw_paths: Any
) -> tuple[list[Path] | None, str | None]:
    """Resolve task write_paths to absolute paths inside the workspace."""
    if raw_paths is None:
        return None, None
    if not isinstance(raw_paths, list) or not raw_paths:
        return None, "write=true 的子任务必须提供非空 write_paths"
    resolved: list[Path] = []
    ws = workspace.resolve()
    for raw in raw_paths:
        raw = str(raw or "").strip()
        if not raw:
            continue
        p = Path(raw)
        if not p.is_absolute():
            p = workspace / p
        try:
            p = p.resolve()
            p.relative_to(ws)
        except (ValueError, OSError):
            return None, f"write_paths 超出工作区范围: {raw}"
        resolved.append(p)
    if not resolved:
        return None, "write=true 的子任务必须提供非空 write_paths"
    return resolved, None


def _claims_overlap(a: Path, b: Path) -> bool:
    """Two claims overlap when one contains the other (shared files possible)."""
    return a == b or a in b.parents or b in a.parents


def _validate_tasks(
    arguments: dict[str, Any], workspace: Path | None = None
) -> tuple[list[dict[str, Any]], str | None]:
    """Validate the run_subagents arguments; return (tasks, error).

    With a workspace, write tasks are validated (claims inside workspace,
    no overlap between tasks' claims).
    """
    raw_tasks = arguments.get("tasks") or []
    if not isinstance(raw_tasks, list) or not raw_tasks:
        return [], "run_subagents 的 tasks 参数必须是非空数组"
    if len(raw_tasks) < 2:
        return [], "run_subagents 至少需要 2 个子任务；单个子任务请直接在主对话中完成"
    if len(raw_tasks) > MAX_SUBAGENTS:
        return [], f"一次最多委托 {MAX_SUBAGENTS} 个子任务"
    tasks: list[dict[str, Any]] = []
    all_claims: list[tuple[str, list[Path]]] = []
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
        write = bool(item.get("write"))
        terminal_enabled = bool(item.get("terminal"))
        claims: list[Path] | None = None
        if write:
            if workspace is None:
                return [], f"子任务 {task_id} 声明 write=true，但未提供工作区校验"
            if not item.get("write_paths"):
                return [], f"子任务 {task_id}: write=true 必须提供非空 write_paths"
            claims, claim_error = _resolve_write_claims(
                workspace, item.get("write_paths")
            )
            if claim_error:
                return [], f"子任务 {task_id}: {claim_error}"
            all_claims.append((task_id, claims))
        tasks.append(
            {
                "id": task_id,
                "name": name,
                "prompt": prompt,
                "tools": tools if isinstance(tools, list) else None,
                "write": write,
                "terminal": terminal_enabled,
                "write_paths": [
                    str(p) for p in (claims or [])
                ] if claims else None,
                "claims": claims,
            }
        )
    if workspace is not None:
        for i in range(len(all_claims)):
            for j in range(i + 1, len(all_claims)):
                id_a, claims_a = all_claims[i]
                id_b, claims_b = all_claims[j]
                for ca in claims_a:
                    for cb in claims_b:
                        if _claims_overlap(ca, cb):
                            return [], (
                                f"子任务 {id_a} 与 {id_b} 的 write_paths 冲突："
                                f"{ca} 与 {cb} 重叠；并行写任务必须修改互不重叠的文件"
                            )
    return tasks, None


def has_write_tasks(tasks: list[dict[str, Any]]) -> bool:
    """True when any validated task is write-capable."""
    return any(bool(task.get("write")) for task in tasks)


def has_terminal_tasks(tasks: list[dict[str, Any]]) -> bool:
    """True when any validated task requested terminal/command execution."""
    return any(bool(task.get("terminal")) for task in tasks)


async def _run_subagent_tool(
    ctx: AgentRunContext,
    adapter: Any,
    name: str,
    arguments: dict[str, Any],
) -> str:
    """Execute one tool for a sub-agent, without approvals or SSE.

    External paths outside ``approved_paths`` are rejected automatically.
    Raw terminal runs are restricted to safe-policy commands: sub-agents
    cannot ask the user for confirmation, so anything requiring it is
    rejected up front. Returns the main agent's string content contract.
    """
    if name == "terminal":
        command = str(arguments.get("command") or "")
        from ...tools.terminal_policy import terminal_command_policy

        policy = terminal_command_policy(command)
        if policy != "safe":
            return json.dumps(
                {
                    "success": False,
                    "message": (
                        f"子 Agent 只能执行安全只读命令（策略={policy}），"
                        "需要确认的命令请在任务结果中说明，由主 Agent 处理"
                    ),
                    "command": command[:300],
                    "rejected": True,
                },
                ensure_ascii=False,
            )
        arguments = {**arguments, "background": False}
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
    effective_timeout = adapter.timeout
    if hasattr(adapter, "effective_timeout"):
        try:
            effective_timeout = adapter.effective_timeout(arguments)
        except Exception:  # noqa: BLE001 — fall back to base timeout
            pass
    try:
        output = await asyncio.wait_for(
            adapter.run(
                ctx.workspace,
                arguments,
                locale=ctx.locale,
            ),
            timeout=effective_timeout,
        )
        result = output.as_dict()
    except asyncio.TimeoutError:
        result = {
            "success": False,
            "message": f"工具执行超时（{effective_timeout}s）",
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


def _tool_target_paths(
    workspace: Path, name: str, arguments: dict[str, Any]
) -> list[Path]:
    """Resolve the file paths a write tool will touch (workspace-relative)."""
    paths: list[Path] = []
    if name == "write_file":
        raw = str(arguments.get("path") or "").strip()
        if raw:
            paths.append(raw)
    elif name == "edit_files":
        for item in arguments.get("files") or []:
            if isinstance(item, dict):
                raw = str(item.get("path") or "").strip()
                if raw:
                    paths.append(raw)
    resolved: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if not p.is_absolute():
            p = workspace / p
        resolved.append(p.resolve())
    return resolved


def _within_claims(path: Path, claims: list[Path] | None) -> bool:
    if not claims:
        return False
    return any(path == claim or claim in path.parents for claim in claims)


def _snapshot_text(path: Path, limit: int = 1_000_000) -> str | None:
    """Best-effort text snapshot; None for missing/binary/oversized files."""
    try:
        if not path.is_file() or path.stat().st_size > limit:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _record_change(
    changes: list[dict[str, Any]],
    workspace: Path,
    path: Path,
    before: str | None,
    after: str | None,
) -> None:
    if len(changes) >= _SUBAGENT_CHANGE_CAP:
        return
    try:
        rel = path.relative_to(workspace.resolve()).as_posix()
    except ValueError:
        rel = str(path)
    if before is None and after is not None:
        action = "created"
    elif before is not None and after is None:
        action = "deleted"
    elif before != after:
        action = "modified"
    else:
        return
    diff = ""
    if before is not None and after is not None:
        diff = "\n".join(
            difflib.unified_diff(
                (before or "").splitlines(),
                (after or "").splitlines(),
                fromfile=rel,
                tofile=rel,
                lineterm="",
            )
        )
    elif after is not None:
        diff = "\n".join(
            difflib.unified_diff(
                [], (after or "").splitlines(), fromfile="/dev/null", tofile=rel
            )
        )
    changes.append(
        {
            "path": rel,
            "action": action,
            "diff": diff[:_SUBAGENT_DIFF_CAP],
        }
    )


async def _run_subagent_tool_with_claims(
    ctx: AgentRunContext,
    adapter: Any,
    name: str,
    arguments: dict[str, Any],
    claims: list[Path] | None,
    changes: list[dict[str, Any]],
) -> str:
    """Write-tool variant: enforce declared write_paths and record diffs."""
    workspace = ctx.workspace.resolve()
    targets = _tool_target_paths(workspace, name, arguments)
    denied = [p for p in targets if not _within_claims(p, claims)]
    if denied:
        return json.dumps(
            {
                "success": False,
                "message": (
                    "写入路径超出本子任务声明范围（write_paths）："
                    + ", ".join(str(p) for p in denied[:3])
                ),
                "paths": [str(p) for p in denied[:5]],
                "rejected": True,
            },
            ensure_ascii=False,
        )
    before = {str(p): _snapshot_text(p) for p in targets}
    result_text = await _run_subagent_tool(ctx, adapter, name, arguments)
    after = {str(p): _snapshot_text(p) for p in targets}
    for p in targets:
        _record_change(changes, workspace, p, before.get(str(p)), after.get(str(p)))
    return result_text


def _build_subagent_tools(
    ctx: AgentRunContext,
    allowlist: list[str] | None,
    lock: asyncio.Lock,
    write_claims: list[Path] | None = None,
    changes: list[dict[str, Any]] | None = None,
    terminal_enabled: bool = False,
) -> list[StructuredTool]:
    """Build the restricted toolset for one sub-agent.

    Default is read-only. When ``write_claims`` is provided the task may also
    use ``write_file`` / ``edit_files``, but only within the declared paths;
    every write is recorded as a before/after diff into ``changes``.
    When ``terminal_enabled`` the task additionally gets the raw terminal
    (safe-policy commands only) plus the structured verification tools
    (lint_check / run_tests / format_code).
    ``allowlist`` narrows the default set; forbidden tools are always removed
    (unless explicitly enabled via write_claims / terminal_enabled).
    """
    tools: list[StructuredTool] = []
    write_enabled = write_claims is not None and changes is not None
    for meta in registry.list():
        name = meta["name"]
        if name in _SUBAGENT_FORBIDDEN_TOOLS:
            allowed_exception = write_enabled and name in _SUBAGENT_WRITE_TOOLS
            allowed_exception = allowed_exception or (
                terminal_enabled
                and (name == "terminal" or name in _SUBAGENT_COMMAND_TOOLS)
            )
            if not allowed_exception:
                continue
        elif (
            name not in _SUBAGENT_READ_ONLY_TOOLS
            and name not in _SUBAGENT_WRITE_TOOLS
        ):
            if not (
                terminal_enabled
                and (name == "terminal" or name in _SUBAGENT_COMMAND_TOOLS)
            ):
                continue
        if allowlist and name not in allowlist:
            continue
        adapter = registry.get(name)
        if adapter is None:
            continue
        args_model = _make_args_model(name, meta["parameters"])

        async def call(
            runtime: Any,
            _adapter: Any = adapter,
            _name: str = name,
            **kwargs: Any,
        ) -> Any:
            async with lock:
                if _name in _SUBAGENT_WRITE_TOOLS and write_enabled:
                    return await _run_subagent_tool_with_claims(
                        ctx, _adapter, _name, kwargs, write_claims, changes
                    )
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
    changes: list[dict[str, Any]] = []
    write_claims = task.get("claims")
    terminal_enabled = bool(task.get("terminal"))
    try:
        llm = _build_llm(think=ctx.think, effort=ctx.effort, model_id=ctx.model_id)
        tools = _build_subagent_tools(
            sub_ctx,
            task.get("tools"),
            lock,
            write_claims=write_claims,
            changes=changes if write_claims else None,
            terminal_enabled=terminal_enabled,
        )
        language = language_instruction(ctx.locale)
        write_hint = ""
        if write_claims:
            write_hint = (
                "\n本子任务已启用写文件权限，write_paths 声明范围：\n"
                + "\n".join(f"- {p}" for p in (task.get("write_paths") or []))
                + "\n只能修改以上路径内的文件。"
            )
        if terminal_enabled:
            write_hint += (
                "\n本子任务已启用终端验证：可用 run_tests / lint_check / format_code，"
                "terminal 仅限安全只读命令。"
            )
        system_prompt = (
            f"{SUBAGENT_SYSTEM_PROMPT}\n\n{language}\n\n"
            f"当前会话所属项目工作目录：{ctx.workspace}\n"
            "请以该目录作为资料检索和文件读取的工作区。"
            + write_hint
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
            "recursion_limit": SUBAGENT_RECURSION_LIMIT,
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
        payload: dict[str, Any] = {
            "id": task_id,
            "name": task["name"],
            "status": "done",
            "summary": summary,
            "output": output_text[:SUBAGENT_OUTPUT_CAP],
            "duration": round(time.monotonic() - start, 1),
        }
        if changes:
            payload["changed_files"] = changes
            payload["changed_count"] = len(changes)
        return payload
    except asyncio.TimeoutError:
        logger.warning("subagent timeout id=%s duration=%.1fs", task_id, time.monotonic() - start)
        return {
            "id": task_id,
            "name": task["name"],
            "status": "error",
            "error": f"子 Agent 执行超时（{SUBAGENT_TIMEOUT}s）",
            "duration": round(time.monotonic() - start, 1),
        }
    except GraphRecursionError:
        logger.warning(
            "subagent recursion limit id=%s steps=%s",
            task_id,
            SUBAGENT_RECURSION_LIMIT,
        )
        return {
            "id": task_id,
            "name": task["name"],
            "status": "error",
            "error": "子任务步骤过多，已停止。请拆分成更小的子任务，或减少重复工具调用。",
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
    tasks, error = _validate_tasks(arguments, workspace=ctx.workspace)
    writer = getattr(runtime, "stream_writer", None)
    call_id = getattr(runtime, "tool_call_id", None) or f"call_{time.monotonic_ns()}"
    session_id = ctx.session_id
    write_batch = has_write_tasks(tasks)

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
    output_payload: dict[str, Any] = {
        "success": bool(done_count),
        "message": summary_message,
        "results": results,
    }
    if write_batch:
        changed_total = sum(
            int(item.get("changed_count") or 0) for item in results
        )
        output_payload["write"] = True
        output_payload["changed_total"] = changed_total
        summary_message = (
            f"{len(tasks)} 个子任务完成，共修改 {changed_total} 个文件"
            + (f"，{failed_count} 个失败" if failed_count else "")
        )
        output_payload["message"] = summary_message
        emit(
            "tool",
            {
                "tool": "run_subagents",
                "status": "done" if done_count else "error",
                "message": summary_message,
                "messageKey": "tool.subagentsWriteDone" if done_count else None,
                "messageParams": (
                    {"changed": changed_total, "failed": failed_count}
                    if done_count
                    else {}
                ),
                "result": {"subagents": results, "write": True},
                "call_id": call_id,
                "session_id": session_id,
            },
        )
    try:
        db.update_tool_run(
            run["id"],
            "done" if done_count else "error",
            output_payload,
        )
    except Exception:  # noqa: BLE001 — persistence must never fail a turn
        logger.exception("persist subagent batch failed session=%s", session_id)
    return json.dumps(output_payload, ensure_ascii=False)


__all__ = [
    "_run_subagents",
    "_validate_tasks",
    "has_write_tasks",
    "has_terminal_tasks",
    "SUBAGENT_SYSTEM_PROMPT",
]
