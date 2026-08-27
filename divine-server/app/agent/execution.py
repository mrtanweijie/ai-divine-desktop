"""Tool adapter execution with approvals, terminal policy, and todo tracking."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from langgraph.prebuilt import ToolRuntime

from .. import db
from ..api.terminal import terminal_command_policy
from ..github_skills import preview_skill_repo
from ..skills import discover_importable_skills, find_importable_skill
from .constants import _NO_PLAN_TOOLS, _READ_ONLY_TOOLS
from .context import AgentRunContext, canonical_path
from .interrupts import _ask_interrupt
from .persistence import _frontend_tool_result
from .plans import _claim_next_todo, _finish_todo
from .prompts import _should_ask_plan
from .tool_runtime import _execute_tool

logger = logging.getLogger("divine.agent.execution")

# 与 terminal 共用命令安全策略的工具（adapter 需实现 build_command）。
_COMMAND_TOOLS = {"lint_check", "run_tests"}

_CONTEXT_STRING_LIMIT = 12_000
_CONTEXT_STRING_KEEP = 10_000
_CONTEXT_LIST_LIMIT = 50


def _compact_for_context(value: Any) -> Any:
    """Deep-truncate oversized tool output before it enters the LLM context."""
    if isinstance(value, str):
        if len(value) > _CONTEXT_STRING_LIMIT:
            return (
                value[:_CONTEXT_STRING_KEEP]
                + f"\n...(truncated, total {len(value)} chars; "
                "如需更多内容请分段读取或缩小搜索范围)"
            )
        return value
    if isinstance(value, dict):
        return {k: _compact_for_context(v) for k, v in value.items()}
    if isinstance(value, list):
        compacted = [_compact_for_context(item) for item in value]
        if len(compacted) > _CONTEXT_LIST_LIMIT:
            omitted = len(compacted) - _CONTEXT_LIST_LIMIT
            compacted = compacted[:_CONTEXT_LIST_LIMIT]
            compacted.append(f"...({omitted} more items omitted)")
        return compacted
    return value

async def _handle_adapter_call(
    ctx: AgentRunContext,
    runtime: ToolRuntime,
    adapter: Any,
    name: str,
    arguments: dict[str, Any],
) -> Any:
    """Execute a tool inside the LangGraph runtime with approval and SSE events."""
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
        await asyncio.to_thread(
            db.update_session,
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
                "messageKey": (
                    "tool.planChoiceFirst" if plan_first else "tool.planChoiceDirect"
                ),
                "messageParams": {},
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
    todos = await asyncio.to_thread(db.list_todos, ctx.session_id)
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
        if name == "run_subagents":
            from .subagents import (
                _run_subagents,
                _validate_tasks,
                has_terminal_tasks,
            )

            # Write-capable / terminal-enabled batches need user approval
            # BEFORE dispatch; the sub-agents themselves never prompt.
            tasks, sub_error = _validate_tasks(arguments, workspace=ctx.workspace)
            write_tasks = [
                task
                for task in tasks
                if task.get("write") and task.get("write_paths")
            ]
            terminal_batch = has_terminal_tasks(tasks)
            if not sub_error and (write_tasks or terminal_batch):
                decision = _ask_interrupt(
                    ctx.session_id,
                    f"subagents_write:{call_id}",
                    {
                        "type": "subagents_write",
                        "session_id": ctx.session_id,
                        "tool": name,
                        "message": (
                            "确认并行任务（含写文件或终端执行权限）？"
                            if write_tasks
                            else "确认并行任务（子任务可执行安全只读命令）？"
                        ),
                        "subagent_write": {
                            "tasks": [
                                {
                                    "id": task["id"],
                                    "name": task["name"],
                                    "write_paths": task["write_paths"],
                                    "terminal": bool(task.get("terminal")),
                                }
                                for task in write_tasks + [
                                    t
                                    for t in tasks
                                    if t.get("terminal")
                                    and not (t.get("write") and t.get("write_paths"))
                                ]
                            ]
                        },
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
                        _finish_todo(todo, False, "用户拒绝并行写任务")
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
                            "message": "已拒绝并行任务",
                            "messageKey": "tool.subagentsWriteRejected",
                            "messageParams": {},
                            "session_id": ctx.session_id,
                            "call_id": call_id,
                        }
                    )
                    return json.dumps(
                        {
                            "success": False,
                            "message": "用户拒绝了并行写任务",
                            "rejected": True,
                        },
                        ensure_ascii=False,
                    )

            return await _run_subagents(ctx, runtime, arguments)

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
                            "messageKey": "tool.skillMigrateCancelled",
                            "messageParams": {},
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
                            "messageKey": "tool.batchMigrateCancelled",
                            "messageParams": {},
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
                            "messageKey": "tool.skillInstallCancelled",
                            "messageParams": {},
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
        if ctx.approved_paths:
            # Files the user attached themselves (selected/pasted) are already
            # authorized; no confirmation is needed for those exact paths.
            external_paths = [
                path
                for path in external_paths
                if canonical_path(path, ctx.workspace) not in ctx.approved_paths
            ]
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
                            "messageKey": "tool.externalFileRejected",
                            "messageParams": {},
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

        # terminal 与命令型工具（lint_check/run_tests）共用同一安全策略：
        # 命令由 adapter.build_command 构造，经 terminal_command_policy 分级。
        is_terminal = name == "terminal" or (
            name in _COMMAND_TOOLS
            and getattr(adapter, "build_command", None) is not None
        )
        if name == "terminal":
            command = str(arguments.get("command") or "")
        elif is_terminal:
            built: Any = adapter.build_command(arguments)
            command = str(built) if built else "(自动构建的检查/测试命令)"
        else:
            command = ""

        if name in {"git_commit", "git_revert"} and ctx.approval_mode == "ask":
            git_desc = (
                f"git_commit：{str(arguments.get('message') or '')[:200]}"
                if name == "git_commit"
                else f"git_revert：{str(arguments.get('path') or '(全部未提交改动)')}"
            )
            decision = _ask_interrupt(
                ctx.session_id,
                f"git:{call_id}",
                {
                    "type": "git",
                    "session_id": ctx.session_id,
                    "tool": name,
                    "message": "确认执行 git 写操作？",
                    "command": git_desc,
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
                    _finish_todo(todo, False, "用户拒绝 git 写操作")
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
                        "message": "已拒绝 git 写操作",
                        "messageKey": "tool.gitRejected",
                        "messageParams": {},
                        "command": git_desc,
                        "result": {"command": git_desc},
                        "session_id": ctx.session_id,
                        "call_id": call_id,
                    }
                )
                return json.dumps(
                    {
                        "success": False,
                        "message": "用户拒绝了 git 写操作",
                        "command": git_desc,
                        "rejected": True,
                    },
                    ensure_ascii=False,
                )

        if name == "bg_kill" and ctx.approval_mode == "ask":
            bg_desc = f"bg_kill：{str(arguments.get('bg_id') or '')}"
            decision = _ask_interrupt(
                ctx.session_id,
                f"bg_kill:{call_id}",
                {
                    "type": "bg_kill",
                    "session_id": ctx.session_id,
                    "tool": name,
                    "message": "确认停止后台任务？",
                    "command": bg_desc,
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
                    _finish_todo(todo, False, "用户拒绝停止后台任务")
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
                        "message": "已拒绝停止后台任务",
                        "messageKey": "tool.bgKillRejected",
                        "messageParams": {},
                        "command": bg_desc,
                        "result": {"command": bg_desc},
                        "session_id": ctx.session_id,
                        "call_id": call_id,
                    }
                )
                return json.dumps(
                    {
                        "success": False,
                        "message": "用户拒绝了停止后台任务",
                        "command": bg_desc,
                        "rejected": True,
                    },
                    ensure_ascii=False,
                )

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
                    "messageKey": "tool.dangerousCommandBlocked",
                    "messageParams": {},
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
                        "messageKey": "tool.terminalRejected",
                        "messageParams": {},
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
                "messageKey": "tool.runningTool",
                "messageParams": {"tool": name},
                "command": command if is_terminal else None,
                **(
                    {
                        "urls": [
                            str(url).strip()
                            for url in (arguments.get("urls") or [])
                            if str(url).strip()
                        ]
                    }
                    if name == "web_fetch_batch"
                    else {}
                ),
                "call_id": call_id,
            }
        )

        async def _emit_fetch_progress(item: dict[str, Any]) -> None:
            current_url = str(item.get("url") or "")
            writer(
                {
                    "event": "tool",
                    "tool": name,
                    "status": "running",
                    "message": f"正在抓取 {current_url}",
                    "currentUrl": current_url,
                    **(
                        {
                            "urls": [
                                str(url).strip()
                                for url in (arguments.get("urls") or [])
                                if str(url).strip()
                            ]
                        }
                        if name == "web_fetch_batch"
                        else {}
                    ),
                    "call_id": call_id,
                    "session_id": ctx.session_id,
                }
            )

        # Background process tools are scoped by session: inject the session
        # id so bg_manager can isolate processes per conversation.
        if name == "terminal" or name in {"bg_status", "bg_output", "bg_kill"}:
            arguments.setdefault("session_id", ctx.session_id)

        # 图片识别：注入当前会话实际使用的模型，让 read_image 优先用它
        # （而不是 settings 里的 active 默认模型）。
        if name == "read_image" and ctx.model_id:
            arguments.setdefault("model_id", ctx.model_id)

        output = await _execute_tool(
            ctx.session_id,
            adapter,
            name,
            arguments,
            ctx.workspace,
            locale=ctx.locale,
            progress_callback=(
                _emit_fetch_progress
                if name == "web_fetch_batch"
                else None
            ),
        )
        context_view = _compact_for_context(output)
        tool_content = context_view.get("content") or json.dumps(
            context_view, ensure_ascii=False
        )
        tool_content = _compact_for_context(tool_content)
        payload: dict[str, Any] = {
            "event": "tool",
            "tool": name,
            "status": "done" if output.get("success") else "error",
            "message": output.get("message", "执行完成"),
            "messageKey": output.get("messageKey"),
            "messageParams": output.get("messageParams") or {},
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
            tasks = await asyncio.to_thread(db.list_scheduled_tasks)
            writer(
                {
                    "event": "scheduled_tasks_changed",
                    "tasks": tasks,
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
                        "messageKey": "tool.calendarWritten",
                        "messageParams": {},
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
                        "messageKey": "tool.calendarSkipped",
                        "messageParams": {},
                        "session_id": ctx.session_id,
                        "result": calendar_pending,
                    }
                )

        if name == "write_calendar" and output.get("success"):
            events = await asyncio.to_thread(db.list_calendar_events)
            writer(
                {
                    "event": "calendar_events_changed",
                    "events": events,
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
