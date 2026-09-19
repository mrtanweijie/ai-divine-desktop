"""Task execution history (design 027).

每跑一次定时任务生成一行；reminder / agent / monitor 不写（保持现状不变，
它们的执行历史已经从 `scheduled_tasks.last_run_at` 推断）。
webhook / digest / interactive 在 stage 2+ 会创建此表的行。
"""

from __future__ import annotations

import json
from typing import Any

from .connection import _new_id, _now, get_conn


def create_run(task_id: str) -> dict[str, Any]:
    run_id = _new_id()
    now = _now()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO task_runs "
            "(id, task_id, started_at, status, output, error, delivery_status_json) "
            "VALUES (?, ?, ?, 'pending', '', '', '{}')",
            (run_id, task_id, now),
        )
        conn.commit()
    return get_run(run_id)  # type: ignore[return-value]


def update_run(run_id: str, **fields: Any) -> dict[str, Any]:
    """Update mutable run fields. `finished_at` 由调用方决定是否设置。"""
    columns = ("status", "output", "error", "delivery_status_json", "finished_at")
    assignments: list[str] = []
    values: list[Any] = []
    for column in columns:
        if column not in fields:
            continue
        value = fields[column]
        if column == "delivery_status_json" and isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        assignments.append(f"{column} = ?")
        values.append(value)
    if not assignments:
        return get_run(run_id)  # type: ignore[return-value]
    with get_conn() as conn:
        conn.execute(
            f"UPDATE task_runs SET {', '.join(assignments)} WHERE id = ?",
            (*values, run_id),
        )
        conn.commit()
    return get_run(run_id)  # type: ignore[return-value]


def get_run(run_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM task_runs WHERE id = ?", (run_id,)
        ).fetchone()
    if not row:
        return None
    return _normalize(dict(row))


def list_runs_for_task(task_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with get_conn() as conn:
        # 同秒内的多次插入用 rowid 兜底——_now() 精度到秒，并发触发可能同值。
        rows = conn.execute(
            "SELECT * FROM task_runs WHERE task_id = ? "
            "ORDER BY started_at DESC, rowid DESC LIMIT ?",
            (task_id, limit),
        ).fetchall()
    return [_normalize(dict(row)) for row in rows]


def _normalize(row: dict[str, Any]) -> dict[str, Any]:
    """把 SQLite 里的 JSON 字符串字段解码出来，方便前端直接用。"""
    raw = row.get("delivery_status_json") or "{}"
    try:
        row["delivery_status"] = json.loads(raw)
    except json.JSONDecodeError:
        row["delivery_status"] = {}
    return row