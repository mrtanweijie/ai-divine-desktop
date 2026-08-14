"""Plan/todo helpers shared with the agent tool runtime."""

from __future__ import annotations

from typing import Any

from .. import db

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
