"""media_tasks 仓储（035）：视频/图像生成任务的唯一真相。

设计约束（035 §6）：
- 任务表是 P1 的前提——生成任务面板要列进行中任务，没有表就没有真相；
- 重启可恢复：``list_resumable()`` 把 queued/running 的行捞回来重新挂轮询；
- 行不随会话删除而消失（无外键），file_path 指向的文件可能被用户删掉，
  读取方要自己兜「文件已删除」。
"""

from __future__ import annotations

import json
from typing import Any

from .connection import get_conn, _new_id, _now

TERMINAL_STATUSES = ("succeeded", "failed", "expired", "cancelled")


def _row_to_task(row: Any) -> dict[str, Any]:
    task = dict(row)
    task["params"] = json.loads(task.pop("params_json") or "{}")
    task["extras"] = json.loads(task.pop("extras_json") or "{}")
    return task


def create_task(
    *,
    kind: str,
    provider: str,
    prompt: str,
    params: dict[str, Any],
    session_id: str | None = None,
    call_id: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    task_id = _new_id()
    now = _now()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO media_tasks
                (id, session_id, call_id, kind, provider, model, prompt,
                 params_json, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?)
            """,
            (
                task_id,
                session_id,
                call_id,
                kind,
                provider,
                model,
                prompt,
                json.dumps(params, ensure_ascii=False),
                now,
                now,
            ),
        )
        conn.commit()
    return get_task(task_id)  # type: ignore[return-value]


def get_task(task_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM media_tasks WHERE id = ?", (task_id,)
        ).fetchone()
    return _row_to_task(row) if row else None


def update_task(task_id: str, **fields: Any) -> dict[str, Any] | None:
    """部分更新；``params`` / ``extras`` 走 JSON 序列化，其余按标量写。"""
    if not fields:
        return get_task(task_id)
    sets: list[str] = []
    values: list[Any] = []
    for key, value in fields.items():
        column = f"{key}_json" if key in ("params", "extras") else key
        if key in ("params", "extras"):
            value = json.dumps(value, ensure_ascii=False)
        sets.append(f"{column} = ?")
        values.append(value)
    sets.append("updated_at = ?")
    values.append(_now())
    values.append(task_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE media_tasks SET {', '.join(sets)} WHERE id = ?", values)
        conn.commit()
    return get_task(task_id)


def list_tasks(
    *,
    statuses: list[str] | None = None,
    session_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """按创建时间倒序列任务；``statuses=None`` 表示全部。"""
    query = "SELECT * FROM media_tasks"
    conditions: list[str] = []
    values: list[Any] = []
    if statuses:
        marks = ", ".join("?" for _ in statuses)
        conditions.append(f"status IN ({marks})")
        values.extend(statuses)
    if session_id:
        conditions.append("session_id = ?")
        values.append(session_id)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY created_at DESC, id DESC LIMIT ?"
    values.append(limit)
    with get_conn() as conn:
        rows = conn.execute(query, values).fetchall()
    return [_row_to_task(row) for row in rows]


def list_resumable() -> list[dict[str, Any]]:
    """启动恢复：生成中途退出的任务，重新挂轮询（035 §6 护栏 3）。"""
    return list_tasks(statuses=["queued", "running"], limit=200)


def find_recent_duplicate(
    *,
    provider: str,
    prompt: str,
    params: dict[str, Any],
    seconds: int = 60,
) -> dict[str, Any] | None:
    """幂等护栏：seconds 内相同 provider+prompt+params 的任务直接复用（035 §6）。"""
    from datetime import datetime, timedelta, timezone

    threshold = (
        datetime.now(timezone.utc) - timedelta(seconds=seconds)
    ).strftime("%Y-%m-%dT%H:%M:%S")
    rows = list_tasks(statuses=["queued", "running"], limit=50)
    canonical = json.dumps(params, ensure_ascii=False, sort_keys=True)
    for row in rows:
        if row["provider"] != provider or (row["prompt"] or "") != prompt:
            continue
        if str(row["created_at"]) < threshold:
            continue
        row_params = json.dumps(row.get("params") or {}, ensure_ascii=False, sort_keys=True)
        if row_params == canonical:
            return row
    return None


def count_running(provider: str | None = None) -> int:
    query = "SELECT COUNT(*) AS n FROM media_tasks WHERE status IN ('queued', 'running')"
    values: list[Any] = []
    if provider:
        query += " AND provider = ?"
        values.append(provider)
    with get_conn() as conn:
        row = conn.execute(query, values).fetchone()
    return int(row["n"]) if row else 0


def delete_task(task_id: str) -> bool:
    """删除终态任务行（生成中的行由 API 层拒绝）。"""
    with get_conn() as conn:
        cursor = conn.execute("DELETE FROM media_tasks WHERE id = ?", (task_id,))
        conn.commit()
    return cursor.rowcount > 0
