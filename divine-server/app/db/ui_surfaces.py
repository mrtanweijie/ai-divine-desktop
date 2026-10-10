"""A2UI 面板**编辑态**的读写（``ui_surface_states``）。

设计文档：``docs/design/028-a2ui-integration-20261009.md`` §5.5。

这里存的是「用户改了但还没提交」的输入值 —— 与另外三个落点严格分开：

* 面板**最终态**（长什么样）→ ``message_parts.type='ui_surface'``（回合结束写）；
* 动作**提交**（用户做了什么）→ 一条可见的 user 消息 + ``a2ui_action`` part；
* 本表 → **未提交的编辑值**，刷新/切会话后把面板"填回原样"。

三条纪律：
1. 按 ``surface_id`` **覆盖写**（Upsert），不堆行；
2. **绝不进模型上下文** —— 历史回溯只读 ``messages.content``；
3. 写失败不影响交互（调用方吞异常，见前端 ``uiSurfaceStateStore``）。
"""

from __future__ import annotations

import json
from typing import Any

from .connection import _now, get_conn


def save_ui_surface_state(
    surface_id: str,
    data: dict[str, Any],
    *,
    message_id: str = "",
    session_id: str = "",
) -> dict[str, Any]:
    """覆盖写一份面板编辑态。返回写入后的记录（不含额外查询）。"""
    payload = json.dumps(data or {}, ensure_ascii=False)
    stamp = _now()
    with get_conn() as conn:
        conn.execute(
            'INSERT INTO ui_surface_states '
            '(surface_id, message_id, session_id, data, updated_at) '
            'VALUES (?, ?, ?, ?, ?) '
            'ON CONFLICT(surface_id) DO UPDATE SET '
            'data = excluded.data, '
            'message_id = excluded.message_id, '
            'session_id = excluded.session_id, '
            'updated_at = excluded.updated_at',
            (surface_id, message_id, session_id, payload, stamp),
        )
        conn.commit()
    return {
        "surface_id": surface_id,
        "message_id": message_id,
        "session_id": session_id,
        "data": data or {},
        "updated_at": stamp,
    }


def _decode(row: Any) -> dict[str, Any] | None:
    try:
        parsed = json.loads(row["data"] or "{}")
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    return {
        "surface_id": str(row["surface_id"]),
        "message_id": str(row["message_id"] or ""),
        "data": parsed,
    }


def list_session_ui_surface_states(session_id: str) -> list[dict[str, Any]]:
    """取某会话下所有面板的编辑态（前端加载历史后一次性恢复）。

    一次性按会话取（而不是每个面板一次请求）：一块面板一个请求会把
    长会话的恢复变成几十次往返。
    """
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT surface_id, message_id, data FROM ui_surface_states "
            "WHERE session_id = ?",
            (session_id,),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        decoded = _decode(row)
        if decoded is not None:
            out.append(decoded)
    return out


def clear_ui_surface_state(surface_id: str) -> None:
    """清掉一份编辑态（动作提交成功后由前端提示，或会话清理时调用）。"""
    with get_conn() as conn:
        conn.execute("DELETE FROM ui_surface_states WHERE surface_id = ?", (surface_id,))
        conn.commit()


def clear_session_ui_surface_states(session_id: str) -> None:
    """清掉某会话的全部面板编辑态。

    会话清空/删除时必须显式调用：本表没有外键（`surface_id` 是主键，
    一条记录不知道属于哪条消息），不能指望 CASCADE。
    """
    with get_conn() as conn:
        conn.execute("DELETE FROM ui_surface_states WHERE session_id = ?", (session_id,))
        conn.commit()
