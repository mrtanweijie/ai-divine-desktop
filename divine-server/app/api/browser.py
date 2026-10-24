"""浏览器自动化 API：通道状态与引导启动（031 阶段 1 引导 UI 后端）。

- GET  /api/browser/status — 调试端点是否可达、专用 profile 位置
- POST /api/browser/setup  — 引导启动专用 profile Chrome（幂等：已可用直接返回）
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from ..config import data_root
from ..tools.browser_engine.session import (
    discover_cdp_endpoint,
    launch_debug_chrome,
)

logger = logging.getLogger("divine.api.browser")

router = APIRouter(prefix="/browser", tags=["browser"])


@router.get("/status")
def browser_status():
    endpoint = discover_cdp_endpoint()
    return {
        "running": endpoint is not None,
        "endpoint": endpoint,
        "profile_dir": str(data_root() / "browser" / "profile"),
    }


@router.post("/setup")
async def browser_setup():
    """引导启动专用 profile 浏览器（幂等）。"""
    try:
        info = await asyncio.to_thread(launch_debug_chrome)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — 启动异常转可读错误
        logger.exception("browser setup failed")
        raise HTTPException(status_code=500, detail=f"浏览器启动失败: {exc}") from exc
    return {
        "running": True,
        "endpoint": info["url"],
        "launched": info["launched"],
        "profile_dir": info.get("profile_dir"),
    }
