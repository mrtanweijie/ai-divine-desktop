"""``digest`` 任务类型（design 027 §3.5）。

「多来源 → 摘要 → 投递」：先把来源抓成文本，填进 prompt 模板，
再走 ``webhook`` 同一条执行 + 投递路径。

来源支持两种：
- 本地文件路径：直接读；
- ``http(s)://`` URL：复用现有 ``web_fetch`` 工具（含 JS 渲染兜底）。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from . import register
from .common import (
    RunRecorder,
    final_answer_from_history,
    run_agent_with_user_prompt,
)
from .delivery import DeliveryPayload, dispatch, parse_channels

logger = logging.getLogger("divine.tasks.digest")


@register("digest")
async def run_digest_task(task: dict[str, Any]) -> None:
    recorder = RunRecorder(task["id"])
    recorder.start()
    try:
        sources = (task.get("digest_json") or {}).get("sources") or []
        workspace = await session_workspace(task)
        gathered = await gather_sources(sources, workspace)
        filled = fill_template((task.get("prompt") or "").strip(), gathered)
        executed = {**task, "prompt": filled}

        history = await run_agent_with_user_prompt(executed)
        final = final_answer_from_history(history)
        recorder.set_output(final)

        channels = parse_channels(task.get("delivery_json"))
        results = await dispatch(
            DeliveryPayload(
                task_title=task.get("title") or "每日摘要",
                run_id=str(recorder.run["id"]),
                content=final,
                meta={
                    "task_id": task["id"],
                    "task_type": "digest",
                    "sources": len(gathered),
                },
            ),
            channels,
        )
        recorder.set_delivery(results)

        if results and not any(r.ok for r in results):
            recorder.fail(
                "; ".join(f"{r.channel}: {r.error}" for r in results)
            )
            return
        recorder.finish("succeeded")
    except Exception as e:  # noqa: BLE001 — handler 异常不能冒到调度器
        logger.exception("digest task failed task_id=%s", task.get("id"))
        recorder.fail(repr(e))


async def session_workspace(task: dict[str, Any]) -> Path:
    """取任务 session 的工作空间；取不到就退回全局默认。"""
    import asyncio

    from ... import db
    from ...config import workspace_dir

    session_id = task.get("session_id")
    if not session_id:
        return workspace_dir()
    found = await asyncio.to_thread(db.session_workspace, session_id)
    return Path(found) if found else workspace_dir()


async def gather_sources(
    sources: list[Any], workspace: Path
) -> list[dict[str, str]]:
    """逐个抓取来源。任一来源失败不阻断其他，失败原因记进 content。"""
    import asyncio

    gathered: list[dict[str, str]] = []
    for source in sources or []:
        target = _target_of(source)
        if not target:
            continue
        path = Path(target)
        if path.is_file():
            gathered.append(await asyncio.to_thread(read_local_file, path))
        elif target.startswith(("http://", "https://")):
            gathered.append(await fetch_url(target, workspace))
        else:
            gathered.append(
                {
                    "name": target,
                    "content": "(无法识别的来源，需为本地路径或 http(s) URL)",
                }
            )
    return gathered


def _target_of(source: Any) -> str:
    if isinstance(source, str):
        return source.strip()
    if isinstance(source, dict):
        return str(source.get("url") or source.get("path") or "").strip()
    return ""


def read_local_file(path: Path) -> dict[str, str]:
    try:
        return {"name": path.name, "content": path.read_text(encoding="utf-8")}
    except Exception as e:  # noqa: BLE001
        return {"name": path.name, "content": f"(读取失败: {e})"}


async def fetch_url(url: str, workspace: Path) -> dict[str, str]:
    """复用已注册的 ``web_fetch`` 工具（registry.get 返回实例，可直接 await）。"""
    try:
        from ...tools.registry import get_tool

        adapter = get_tool("web_fetch")
    except Exception as e:  # noqa: BLE001
        return {"name": url, "content": f"(抓取不可用: {e})"}
    if adapter is None:
        return {"name": url, "content": f"(web_fetch 工具未注册，跳过: {url})"}
    try:
        result = await adapter.run(workspace, {"url": url})
    except Exception as e:  # noqa: BLE001
        return {"name": url, "content": f"(抓取失败: {url} — {e})"}
    if not getattr(result, "success", False):
        return {
            "name": url,
            "content": f"(抓取失败: {url} — {getattr(result, 'message', '')})",
        }
    return {"name": url, "content": getattr(result, "content", "") or ""}


def fill_template(prompt: str, gathered: list[dict[str, str]]) -> str:
    """把来源内容填进 prompt 的 ``{sources}`` 占位符。

    没有占位符时把内容追加在提示词后面——用户写模板时不一定记得占位符。
    """
    blocks = "\n\n".join(
        f"### {item['name']}\n{item['content']}"
        for item in gathered
        if item.get("name")
    )
    if not blocks:
        return prompt
    if "{sources}" in prompt:
        return prompt.replace("{sources}", blocks)
    if not prompt:
        return blocks
    return f"{prompt}\n\n以下是待摘要的内容：\n\n{blocks}"
