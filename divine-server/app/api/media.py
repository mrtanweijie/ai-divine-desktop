"""媒体生成任务接口（035 §9.3）：面板与工具卡共用的真相源。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..config import normalize_media_models
from ..db import media_tasks
from ..media import service
from ..media.providers import query_minimax, query_zhipu


def query_status(*, provider: str, base_url: str, api_key: str, remote_task_id: str):
    """health 探测用：按 provider 转发一次查询（不提交生成）。"""
    query = query_minimax if provider == "minimax" else query_zhipu
    return query(base_url=base_url, api_key=api_key, remote_task_id=remote_task_id)

router = APIRouter(prefix="/media", tags=["media"])


def _public(task: dict[str, Any]) -> dict[str, Any]:
    """对前端的任务形态：id/状态/文件/参数/错误，去掉内部字段。"""
    return {
        "id": task["id"],
        "session_id": task.get("session_id"),
        "kind": task.get("kind"),
        "provider": task.get("provider"),
        "model": task.get("model"),
        "prompt": task.get("prompt"),
        "params": task.get("params") or {},
        "status": task.get("status"),
        "file_path": task.get("file_path"),
        "extras": task.get("extras") or {},
        "error": task.get("error"),
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
    }


@router.get("/tasks")
def list_media_tasks(
    status: str = "active",
    include_dismissed: bool = False,
    limit: int = 100,
) -> dict[str, Any]:
    """面板拉任务：``active`` = queued/running，``done`` = 终态，``all`` = 全部。

    「不再等待」的任务（extras.dismissed）默认隐藏，面板用
    ``include_dismissed=true`` 显示「已隐藏 N 个（仍在生成）」。
    """
    limit = max(1, min(limit, 200))
    if status == "active":
        statuses = ["queued", "running"]
    elif status == "done":
        statuses = list(media_tasks.TERMINAL_STATUSES)
    else:
        statuses = None
    tasks = media_tasks.list_tasks(statuses=statuses, limit=limit)
    if not include_dismissed:
        tasks = [task for task in tasks if not (task.get("extras") or {}).get("dismissed")]
    hidden = sum(
        1 for task in tasks if (task.get("extras") or {}).get("dismissed")
    ) if include_dismissed else 0
    return {
        "tasks": [_public(task) for task in tasks],
        "dismissed_running": hidden if status == "active" else 0,
    }


@router.post("/tasks/{task_id}/dismiss")
def dismiss_task(task_id: str) -> dict[str, Any]:
    """「不再等待」：本地隐藏 + 停止打扰；**轮询继续**，云端跑完仍可取回（035 §9.2）。"""
    task = media_tasks.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["status"] in media_tasks.TERMINAL_STATUSES:
        return {"ok": True, "task": _public(task)}
    extras = dict(task.get("extras") or {})
    extras["dismissed"] = True
    updated = media_tasks.update_task(task_id, extras=extras)
    service.broadcast_changed(task_id, str(updated["status"]))  # type: ignore[arg-type]
    return {"ok": True, "task": _public(updated)}


@router.post("/tasks/{task_id}/reshow")
def reshow_task(task_id: str) -> dict[str, Any]:
    """把「不再等待」的任务放回面板进行中列表。"""
    task = media_tasks.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    extras = dict(task.get("extras") or {})
    extras["dismissed"] = False
    updated = media_tasks.update_task(task_id, extras=extras)
    service.broadcast_changed(task_id, str(updated["status"]))  # type: ignore[arg-type]
    return {"ok": True, "task": _public(updated)}


@router.post("/tasks/{task_id}/retry")
def retry_task(task_id: str) -> dict[str, Any]:
    """面板「重试」：同参数重新提交（显式绕过 60s 幂等，035 §9.2）。"""
    task = media_tasks.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["status"] in ("queued", "running"):
        raise HTTPException(status_code=409, detail="任务仍在生成中，无需重试")
    try:
        result = service.submit_video_task(
            prompt=str(task.get("prompt") or ""),
            params={**(task.get("params") or {}), "_force": True},
            session_id=task.get("session_id"),
        )
    except Exception as exc:  # noqa: BLE001 - 重试失败原因直接回面板
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "task": _public(result["task"])}


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str) -> dict[str, Any]:
    """删除任务行（仅终态；生成中的先「不再等待」）。文件不动——删用户文件比占磁盘更糟。"""
    task = media_tasks.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["status"] in ("queued", "running"):
        raise HTTPException(status_code=409, detail="任务仍在生成中，请先「不再等待」")
    media_tasks.delete_task(task_id)
    return {"ok": True}


@router.post("/tasks/{task_id}/save-as")
def save_as(task_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """「另存为」：把生成的视频复制到用户选的路径（Tauri save 对话框给出）。"""
    from pathlib import Path

    import shutil

    task = media_tasks.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    source = str(task.get("file_path") or "")
    if not source or not Path(source).is_file():
        raise HTTPException(status_code=404, detail="视频文件不存在或已被删除")
    dest_raw = str(body.get("dest") or "").strip()
    if not dest_raw:
        raise HTTPException(status_code=400, detail="缺少目标路径")
    dest = Path(dest_raw).expanduser()
    if dest.is_dir():
        dest = dest / Path(source).name
    if not str(dest.parent).strip():
        raise HTTPException(status_code=400, detail="目标路径无效")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"保存失败：{exc}") from exc
    return {"ok": True, "dest": str(dest)}


@router.get("/health")
def health(provider: str = "minimax") -> dict[str, Any]:
    """连通性测试（设置页「测试」按钮）：**不提交生成任务**、不扣费。

    用一个必然不存在的任务号去查询——上游若回 401/403 说明 key 无效；
    其余响应（含 404）说明鉴权通过。UI 文案如实写「已连通（未实测生成）」。
    """
    from ..config import settings_store

    settings = settings_store.load()
    entries = [
        entry
        for entry in normalize_media_models(settings.get("media_models"))
        if entry["kind"] == "video" and entry.get("provider") == provider
    ]
    entry = next((item for item in entries if item["active"]), entries[0] if entries else None)
    if not entry:
        raise HTTPException(status_code=404, detail=f"未配置 {provider} 视频模型")
    api_key = str(entry.get("api_key") or "").strip()
    if not api_key:
        return {"ok": False, "message": "未配置 API Key"}
    try:
        service.query_status(
            provider=provider,
            base_url=str(entry.get("base_url") or ""),
            api_key=api_key,
            remote_task_id="divine-connectivity-probe",
        )
    except Exception as exc:  # noqa: BLE001 - 401/403 会在这里翻译成"key 无效"
        message = str(exc)
        if "Key" in message or "无效" in message:
            return {"ok": False, "message": "API Key 无效"}
        return {"ok": True, "message": "已连通（未实测生成）"}
    return {"ok": True, "message": "已连通（未实测生成）"}
