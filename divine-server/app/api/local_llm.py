"""本地模型管理 API。

端点：
- GET  /api/local_llm/status          获取状态（硬件 + 推荐 + 已安装）
- POST /api/local_llm/mode            切换意图识别模式
- POST /api/local_llm/start           启动 llama-server
- POST /api/local_llm/stop            停止 llama-server
- POST /api/local_llm/install         安装模型（从仓库下载）
- POST /api/local_llm/uninstall       卸载模型
- GET  /api/local_llm/hardware        获取硬件信息
- GET  /api/local_llm/recommended     获取推荐模型列表
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import settings_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/local_llm", tags=["local_llm"])


class ModeRequest(BaseModel):
    mode: str  # "keyword" | "local" | "hybrid"


class StartRequest(BaseModel):
    model_id: str


class InstallRequest(BaseModel):
    model_id: str


class UninstallRequest(BaseModel):
    model_id: str


class CustomInstallRequest(BaseModel):
    url: str
    name: str | None = None
    key: str | None = None


class RegisterLocalRequest(BaseModel):
    path: str


@router.get("/status")
async def get_status():
    """获取本地模型状态（硬件 + 推荐 + 已安装）。"""
    try:
        from ..agent.core import get_manager

        manager = get_manager()
        return manager.get_status()
    except Exception as e:
        raise HTTPException(500, f"获取状态失败: {e}")


@router.get("/hardware")
async def get_hardware():
    """获取硬件信息。"""
    try:
        from ..agent.core import detect_hardware

        hw = detect_hardware()
        return {
            "ram_total_gb": hw.ram_total_gb,
            "ram_available_gb": hw.ram_available_gb,
            "cpu_cores": hw.cpu_cores,
            "has_gpu": hw.has_gpu,
            "gpu_name": hw.gpu_name,
            "gpu_memory_gb": hw.gpu_memory_gb,
            "platform": hw.platform,
            "arch": hw.arch,
        }
    except Exception as e:
        logger.warning("获取硬件信息失败: %s", e)
        return {"error": str(e)}


@router.get("/recommended")
async def get_recommended():
    """获取推荐模型列表。"""
    try:
        from ..agent.core import detect_hardware, get_recommended_models

        hardware = detect_hardware()
        models = get_recommended_models(hardware)
        return {
            "models": [
                {
                    "id": m.id,
                    "name": m.name,
                    "description": m.description,
                    "size_gb": m.size_gb,
                    "required_ram_gb": m.required_ram_gb,
                    "quantization": m.quantization,
                    "recommended": m.recommended,
                    "tags": m.tags,
                }
                for m in models
            ]
        }
    except Exception as e:
        logger.warning("获取推荐模型失败: %s", e)
        return {"models": []}


@router.post("/mode")
async def set_mode(req: ModeRequest):
    """切换意图识别模式。"""
    if req.mode not in ("keyword", "local", "hybrid"):
        raise HTTPException(400, "mode 必须是 keyword/local/hybrid")

    settings = settings_store.load()
    settings["local_llm_mode"] = req.mode
    settings["local_llm_enabled"] = req.mode != "keyword"
    settings_store.save(settings)

    return {"ok": True, "mode": req.mode}


@router.post("/start")
async def start_model(req: StartRequest):
    """启动指定模型。"""
    try:
        from ..agent.core import get_manager

        manager = get_manager()

        # 检查 llama-server 是否存在
        binary = manager._find_binary()
        if not binary:
            raise HTTPException(
                500,
                detail="llama-server 未安装。请先安装：brew install llama.cpp",
            )

        status = manager.get_status()

        # 查找已安装模型
        model = next(
            (m for m in status["installed_models"] if m["id"] == req.model_id),
            None,
        )
        if not model:
            raise HTTPException(404, "模型未安装")

        if not Path(model["path"]).exists():
            raise HTTPException(404, "模型文件不存在")

        settings = settings_store.load()
        ctx_size = settings.get("local_llm_ctx_size", 4096)
        # 阻塞调用（含最多 20s 的就绪等待）放入线程池，避免卡住事件循环
        ok, err = await asyncio.to_thread(
            manager.start,
            req.model_id,
            model["path"],
            ctx_size,
            20.0,
        )

        if not ok:
            raise HTTPException(
                500,
                detail=err or "启动 llama-server 失败，请检查日志",
            )

        # 更新启用状态
        settings["local_llm_enabled"] = True
        settings["local_llm_mode"] = "local"
        settings_store.save(settings)

        return {"ok": True, "model_id": req.model_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"启动失败: {e}")


@router.post("/stop")
async def stop_model():
    """停止 llama-server。"""
    try:
        from ..agent.core import get_manager

        manager = get_manager()
        manager.stop()
    except Exception:
        pass

    settings = settings_store.load()
    settings["local_llm_enabled"] = False
    settings["local_llm_mode"] = "keyword"
    settings_store.save(settings)

    return {"ok": True}


@router.post("/install")
async def install_model(req: InstallRequest):
    """安装模型（从仓库下载）。"""
    try:
        from ..agent.core import get_manager

        manager = get_manager()

        # 检查是否已安装
        status = manager.get_status()
        if any(m["id"] == req.model_id for m in status["installed_models"]):
            return {"ok": True, "message": "模型已安装"}

        # 下载（阻塞下载放线程池，避免卡住事件循环与进度轮询）
        ok = await asyncio.to_thread(manager.install_model, req.model_id)
        if not ok:
            raise HTTPException(
                500,
                detail="下载模型失败，请检查网络连接后重试。如果是网络受限地区，可能需要使用镜像源。",
            )

        return {"ok": True, "model_id": req.model_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"安装失败: {e}")


@router.post("/uninstall")
async def uninstall_model(req: UninstallRequest):
    """卸载模型。"""
    try:
        from ..agent.core import get_manager

        manager = get_manager()
        ok = manager.uninstall_model(req.model_id)
        if not ok:
            raise HTTPException(404, "模型不存在")

        return {"ok": True, "model_id": req.model_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"卸载失败: {e}")


@router.post("/install_custom")
async def install_custom_model(req: CustomInstallRequest):
    """安装自定义模型（从指定 URL 下载 GGUF，不走内置仓库）。"""
    if not req.url.strip():
        raise HTTPException(400, "URL 不能为空")
    try:
        from ..agent.core import get_manager

        manager = get_manager()
        key = req.key or f"custom-{int(time.time())}"
        # 阻塞下载放入线程池，避免卡住事件循环
        ok, message = await asyncio.to_thread(
            manager.install_custom_model,
            req.url.strip(),
            req.name,
            key,
        )
        if not ok:
            raise HTTPException(500, detail=message)
        return {"ok": True, "path": message, "key": key}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"安装失败: {e}")


@router.post("/register_local")
async def register_local_model(req: RegisterLocalRequest):
    """注册本地 .gguf 文件（复制到模型目录）。"""
    if not req.path.strip():
        raise HTTPException(400, "路径不能为空")
    try:
        from ..agent.core import get_manager

        manager = get_manager()
        ok, message = await asyncio.to_thread(
            manager.register_local_model, req.path.strip()
        )
        if not ok:
            raise HTTPException(500, detail=message)
        return {"ok": True, "path": message}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"注册失败: {e}")


@router.get("/download_progress/{model_id}")
async def get_download_progress(model_id: str):
    """获取下载进度。"""
    try:
        from ..agent.core import get_manager

        manager = get_manager()
        progress = manager._download_progress.get(model_id)
        return progress or {"downloaded": 0, "total": 0, "percent": 0}
    except Exception:
        return {"downloaded": 0, "total": 0, "percent": 0}
