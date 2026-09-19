"""``webhook`` 任务类型（design 027 §3.3）。

执行 = 用任务上的提示词跑一轮 Agent → 取最终答案 → 推到配置的频道。
``digest`` / ``interactive`` 在 stage 3 / 4 单独加文件，共用 ``common``。
"""

from __future__ import annotations

import logging
from typing import Any

from . import register
from .common import (
    RunRecorder,
    final_answer_from_history,
    run_agent_with_user_prompt,
)
from .delivery import DeliveryPayload, dispatch, parse_channels

logger = logging.getLogger("divine.tasks.webhook")


@register("webhook")
async def run_webhook_task(task: dict[str, Any]) -> None:
    recorder = RunRecorder(task["id"])
    recorder.start()
    try:
        history = await run_agent_with_user_prompt(task)
        final = final_answer_from_history(history)
        recorder.set_output(final)

        # Agent 没产出内容（例如会话不可用）时**绝不投递**：否则会往飞书/企微
        # 发一条空消息，通道返回 200 还会被记成 succeeded，执行历史里完全看不出问题。
        if not final.strip():
            recorder.skip("Agent 未产出内容，已跳过投递")
            return

        channels = parse_channels(task.get("delivery_json"))
        results = await dispatch(
            DeliveryPayload(
                task_title=task.get("title") or "定时任务",
                run_id=str(recorder.run["id"]),
                content=final,
                meta={"task_id": task["id"], "task_type": "webhook"},
            ),
            channels,
        )
        recorder.set_delivery(results)

        if results and not any(r.ok for r in results):
            # 全通道都挂：标 failed，让人能在执行历史里直接看到原因
            recorder.fail(
                "; ".join(f"{r.channel}: {r.error}" for r in results)
            )
            return
        recorder.finish("succeeded")
    except Exception as e:  # noqa: BLE001 — handler 异常不能冒到调度器
        logger.exception("webhook task failed task_id=%s", task.get("id"))
        recorder.fail(repr(e))
