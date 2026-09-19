"""定时任务 handler 共用工具（design 027）。

三个新类型（webhook / digest / interactive）都执行同一条路径：
「在任务绑定的 session 里跑一轮 Agent → 取最终答案 → 记录执行历史」。
agent / monitor 的旧语义（强制 full + direct）保留在 ``_approval_and_plan`` 里。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from ... import db
from ...config import workspace_dir

logger = logging.getLogger("divine.tasks.common")

# 改前就存在的两类：强制跑满权限、计划模式直接执行
_LEGACY_FORCED_TYPES = ("agent", "monitor")


def _approval_and_plan(task: dict[str, Any], session: dict[str, Any]) -> tuple[str, str]:
    """决定这一轮 Agent 的 approval_mode / plan_mode。

    - ``agent`` / ``monitor``：与改前一致，强制 ``full`` + ``direct``
      （这两类任务用户在创建时就默认给了完全访问）；
    - 新类型：看 ``allow_full_access`` 开关，关着就退回 session 自己的设置。
    """
    if task.get("task_type") in _LEGACY_FORCED_TYPES or task.get(
        "allow_full_access"
    ):
        return "full", "direct"
    return (
        session.get("approval_mode") or "ask",
        session.get("plan_mode") or "ask",
    )


async def run_agent_with_user_prompt(
    task: dict[str, Any],
) -> list[dict[str, Any]]:
    """在任务的 session 里跑一轮 Agent，返回跑完的 history。

    user message 取 ``task['prompt']``（新类型由用户填），
    回退顺序 prompt → description → title → "定时任务"。
    """
    session_id = task.get("session_id")
    if not session_id:
        logger.warning("scheduled task has no session_id task_id=%s", task["id"])
        return []
    session = await asyncio.to_thread(db.get_session, session_id)
    if session is None:
        logger.warning("scheduled task session gone task_id=%s", task["id"])
        return []
    workspace = Path(
        await asyncio.to_thread(db.session_workspace, session_id)
        or workspace_dir()
    )
    approval_mode, plan_mode = _approval_and_plan(task, session)
    previous_plan_mode = session.get("plan_mode") or "ask"
    user_message = (
        (task.get("prompt") or "").strip()
        or (task.get("description") or "").strip()
        or task.get("title")
        or "定时任务"
    )
    await asyncio.to_thread(db.update_session, session_id, plan_mode=plan_mode)
    try:
        await asyncio.to_thread(db.add_message, session_id, "user", user_message)
        history = await asyncio.to_thread(
            db.history_for_model, session_id, limit=20
        )
        from ...agent import run_agent

        async for _event in run_agent(
            session_id,
            history,
            think=False,
            workspace=workspace,
            approval_mode=approval_mode,
            locale=session.get("locale") or "zh-CN",
        ):
            pass
        return await asyncio.to_thread(
            db.history_for_model, session_id, limit=20
        )
    finally:
        await asyncio.to_thread(
            db.update_session, session_id, plan_mode=previous_plan_mode
        )


def final_answer_from_history(history: list[dict[str, Any]]) -> str:
    """取最后一条非空的 assistant 消息作为「最终答案」（投递内容）。

    Agent 跑完可能留下 tool / user 尾巴（工具结果不会自己变成回答），
    所以从后往前找第一条有内容的 assistant。
    """
    for message in reversed(history or []):
        if message.get("role") != "assistant":
            continue
        content = (message.get("content") or "").strip()
        if content:
            return content
    return ""


class RunRecorder:
    """把一次执行写进 ``task_runs``；handler 只管调方法，不碰 SQL。"""

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        self.run: dict[str, Any] | None = None

    def start(self) -> dict[str, Any]:
        self.run = db.create_run(self.task_id)
        return self.run

    def _require_id(self) -> str:
        if self.run is None:
            raise RuntimeError("RunRecorder.start() 未调用")
        return str(self.run["id"])

    def set_output(self, text: str) -> None:
        if self.run is None:
            return
        db.update_run(self._require_id(), output=text or "")

    def set_delivery(self, results: list[Any]) -> None:
        """``results`` 是 ``DeliveryResult`` 列表；按 channel 名字存。"""
        if self.run is None:
            return
        payload: dict[str, Any] = {}
        for result in results or []:
            payload[getattr(result, "channel", "unknown")] = {
                "ok": bool(getattr(result, "ok", False)),
                "status_code": getattr(result, "status_code", None),
                "error": getattr(result, "error", None),
            }
        db.update_run(self._require_id(), delivery_status_json=payload)

    def finish(
        self,
        status: str,
        error: str = "",
        finished_at: str | None = None,
    ) -> None:
        if self.run is None:
            return
        fields: dict[str, Any] = {"status": status}
        if error:
            fields["error"] = error
        if finished_at:
            fields["finished_at"] = finished_at
        db.update_run(self._require_id(), **fields)

    def fail(self, error: str) -> None:
        self.finish("failed", error=error)

    def skip(self, reason: str) -> None:
        self.finish("skipped", error=reason)
