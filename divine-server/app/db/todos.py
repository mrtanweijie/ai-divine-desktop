"""Agent plan/todo repository."""

from __future__ import annotations

from typing import Any

from .connection import get_conn, _new_id, _now

def replace_todos(
    session_id: str, titles: list[str]
) -> list[dict[str, Any]]:
    now = _now()
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM agent_todos WHERE session_id = ?", (session_id,)
        )
        for index, title in enumerate(titles):
            conn.execute(
                "INSERT INTO agent_todos "
                "(id, session_id, \"index\", title, status, result, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'pending', NULL, ?, ?)",
                (_new_id(), session_id, index, title, now, now),
            )
        conn.commit()
    return list_todos(session_id)

def list_todos(session_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_todos WHERE session_id = ? "
            "ORDER BY \"index\" ASC, rowid ASC",
            (session_id,),
        ).fetchall()
    return [dict(row) for row in rows]

def update_todo_status(
    todo_id: str, status: str, result: str | None = None
) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE agent_todos SET status = ?, result = ?, updated_at = ? "
            "WHERE id = ?",
            (status, result, _now(), todo_id),
        )
        conn.commit()

def add_todo(session_id: str, title: str) -> dict[str, Any]:
    """Append a single todo to the end of a session's plan."""
    now = _now()
    index = len(list_todos(session_id))
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO agent_todos "
            "(id, session_id, \"index\", title, status, result, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'pending', NULL, ?, ?)",
            (_new_id(), session_id, index, title, now, now),
        )
        conn.commit()
    return list_todos(session_id)[-1]

# 本地独有但保留的待办前缀：失败回流项（[复盘]）需跨 run 存活——
# prompts 侧每轮从 DB 读取计划进度注入，回流项被清掉等于回流机制失效。
_RECOVERY_TITLE_PREFIX = "[复盘]"

def _rewrite_todos(session_id: str, rows: list[dict[str, Any]]) -> None:
    now = _now()
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM agent_todos WHERE session_id = ?", (session_id,)
        )
        for row in rows:
            conn.execute(
                "INSERT INTO agent_todos "
                "(id, session_id, \"index\", title, status, result, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row["id"],
                    session_id,
                    row["index"],
                    row["title"],
                    row["status"],
                    row["result"],
                    now,
                    now,
                ),
            )
        conn.commit()

def sync_todos(
    session_id: str, items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """以 agent state 的计划为准合并本地待办，且保留已判定状态。

    修复（D1）：旧路径 replace_todos 会把所有状态重置为 pending，导致
    run 结束后进度归零、前端与 DB 分叉。合并规则：
    - 按标题匹配本地行（位置一致者优先）：本地 done/error 是工具执行
      实证，优先保留；其余采用传入状态（pending→pending、in_progress→
      running、completed→done 由调用方映射）。
    - state 新增的行按传入状态插入。
    - 本地独有行：保留未完成的 [复盘] 回流项，其余删除。
    """
    existing = list_todos(session_id)
    by_title: dict[str, list[dict[str, Any]]] = {}
    for todo in existing:
        by_title.setdefault(todo["title"], []).append(todo)
    used: set[str] = set()
    rows: list[dict[str, Any]] = []
    for item in items:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        mapped = str(item.get("status") or "pending")
        candidates = by_title.get(title, [])
        match = next(
            (c for c in candidates if c["id"] not in used and c["index"] == len(rows)),
            None,
        )
        if match is None:
            match = next((c for c in candidates if c["id"] not in used), None)
        if match is None:
            row_id, status, result = _new_id(), mapped, None
        else:
            used.add(match["id"])
            local = match["status"]
            if local in ("done", "error"):
                status = local
            elif mapped == "done":
                status = "done"
            elif mapped == "running":
                status = "running"
            else:
                status = local
            row_id, result = match["id"], match["result"]
        rows.append(
            {
                "id": row_id,
                "index": len(rows),
                "title": title,
                "status": status,
                "result": result,
            }
        )
    for todo in existing:
        if todo["id"] in used:
            continue
        if todo["title"].startswith(_RECOVERY_TITLE_PREFIX) and todo[
            "status"
        ] in ("pending", "running"):
            rows.append(
                {
                    "id": todo["id"],
                    "index": len(rows),
                    "title": todo["title"],
                    "status": todo["status"],
                    "result": todo["result"],
                }
            )
    _rewrite_todos(session_id, rows)
    return list_todos(session_id)

def settle_todos(session_id: str) -> tuple[list[dict[str, Any]], int]:
    """run 正常结束后的终态收敛（D5：skipped 首次获得真实语义）。

    - running → done：agent 已给出最终回答，视为该步已收尾；
    - pending → skipped：未被认领，agent 判断无需执行；
    - done / error / skipped 保持不变。
    返回 (收敛后的全量 todos, 被收敛的条数)。
    """
    todos = list_todos(session_id)
    settled = 0
    for todo in todos:
        if todo["status"] == "running":
            update_todo_status(todo["id"], "done", todo["result"])
            settled += 1
        elif todo["status"] == "pending":
            update_todo_status(todo["id"], "skipped", todo["result"])
            settled += 1
    return list_todos(session_id), settled

def abort_todos(session_id: str) -> None:
    """用户取消 / 异常中断路径的收敛：running → skipped（不谎报完成）。

    pending 保持 pending——后续 run 可能继续执行同一计划。
    """
    for todo in list_todos(session_id):
        if todo["status"] == "running":
            update_todo_status(todo["id"], "skipped", todo["result"])
