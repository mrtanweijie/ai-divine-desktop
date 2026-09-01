"""Plan/todo helpers shared with the agent tool runtime."""

from __future__ import annotations

from typing import Any

from ... import db

_PLAN_STATUS_LABELS = {
    "pending": "待办",
    "running": "执行中",
    "done": "完成",
    "error": "失败",
    "skipped": "跳过",
}

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

# 同 session 复盘项总量上限：超过即不再回流，收敛为给用户的提示。
# 双闸之一（另一闸是 _is_recovery_title 的同类去重）——封死
# "多种工具连环失败 → 待办无限累积 → token 被逐个试光"的软肋。
_MAX_RECOVERY_TODOS = 5

def _is_recovery_title(title: str, tool_name: str) -> bool:
    return title.startswith("[复盘]") and tool_name in title

def _count_recovery(todos: list[dict[str, Any]]) -> int:
    return sum(1 for t in todos if t["title"].startswith("[复盘]"))

def _spawn_recovery_todo(
    session_id: str,
    todos: list[dict[str, Any]],
    failed: dict[str, Any],
    reason: str = "",
) -> dict[str, Any] | None:
    """失败回流：把一次工具失败转成一条『复盘/修复』todo 挂回当前计划。

    双闸护栏：
    1. 同类去重：同 tool 已有 pending 复盘项则跳过（防死循环 / 防刷屏）。
    2. 全局上限：同 session 复盘项总量封顶 _MAX_RECOVERY_TODOS（防连环失败累积）。

    回流只写待办、不触发执行——重试执行权始终交回 agent 决策，
    受现有 approval 审批约束，token 燃烧路径上始终有人类刹车。
    """
    for t in todos:
        if t["status"] == "pending" and _is_recovery_title(
            t["title"], failed.get("tool_name", "")
        ):
            return None
    if _count_recovery(todos) >= _MAX_RECOVERY_TODOS:
        return None
    tool_name = failed.get("tool_name", "工具")
    reason_text = str(failed.get("reason") or reason or "未知错误")
    title = f"[复盘] {tool_name} 失败：{reason_text[:40]}"
    return db.add_todo(session_id, title)
