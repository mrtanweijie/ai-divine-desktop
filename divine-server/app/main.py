from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import db
from .api import (
    calendar_events,
    chat,
    files,
    git,
    local_llm,
    mcp,
    memories,
    model_providers,
    pdf_themes,
    projects,
    scheduled_tasks,
    sessions,
    settings,
    skills,
    terminal,
)
from .config import cors_origins, ensure_directories, settings_store
from .scheduler import scheduler
from .tools.registry import registry

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("=== 侧边端启动 ===")
    ensure_directories()
    db.init_db()
    # 启动时清理过期工具运行记录（tool_runs 防膨胀 retention）
    try:
        from .db.tool_runs import prune_tool_runs

        removed = await asyncio.to_thread(prune_tool_runs)
        if removed:
            logger.info("pruned %d expired tool_runs", removed)
    except Exception:  # noqa: BLE001 — 清理失败不影响启动
        logger.exception("tool_runs retention failed")
    # 用户插件：加载 data/plugins/ 下的工具（幂等，坏插件跳过不影响启动）
    try:
        from .config import plugins_dir
        from .tools.registry import load_plugins_from

        load_plugins_from(plugins_dir())
    except Exception:  # noqa: BLE001 — 插件加载失败不影响服务启动
        logger.exception("插件加载失败")
    await scheduler.start()
    logger.info("=== 侧边端就绪 ===")
    yield
    logger.info("=== 侧边端关闭 ===")
    await scheduler.stop()
    terminal.shutdown_terminal()
    from .tools.bg_process import bg_manager

    await bg_manager.shutdown_all()
    # 关闭 MCP server 连接（stdio 子进程）
    try:
        from .mcp.manager import mcp_manager

        await mcp_manager.shutdown()
    except Exception:  # noqa: BLE001
        pass
    # 停止 llama-server
    try:
        from .agent.core import get_manager

        get_manager().stop()
    except Exception:
        pass
    # 关闭 LangGraph checkpointer 的 aiosqlite 连接（worker 线程非
    # daemon，不关闭会阻止进程退出）
    try:
        from .agent.core.checkpointer import close_checkpointers

        await close_checkpointers()
    except Exception:
        pass


app = FastAPI(
    title="AI Divine",
    version="0.2.1",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def register_exception_handlers(app: FastAPI) -> None:
    """统一 API 错误响应格式为 ``{"detail": ...}``。

    - HTTPException：FastAPI 默认已返回 ``{"detail"}``，显式注册保证跨版本一致。
    - 未捕获异常：原本会走 Starlette 默认 500（detail 固定英文、无上下文），
      这里统一为 500 + 截断的错误信息（本地桌面应用，返回可读 detail 便于
      前端展示与排查；日志由 log_requests middleware 记录，避免重复）。
    """

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code, content={"detail": exc.detail}
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        detail = str(exc)[:500] or "服务器内部错误"
        return JSONResponse(status_code=500, content={"detail": detail})


register_exception_handlers(app)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    try:
        response = await call_next(request)
        elapsed = (time.time() - start) * 1000
        if elapsed > 1000:
            logger.warning(
                "慢请求 %s %s → %d (%.0fms)",
                request.method,
                request.url.path,
                response.status_code,
                elapsed,
            )
        return response
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        logger.error(
            "请求异常 %s %s → %s (%.0fms)",
            request.method,
            request.url.path,
            e,
            elapsed,
        )
        raise

app.include_router(chat.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(scheduled_tasks.router, prefix="/api")
app.include_router(calendar_events.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(pdf_themes.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(memories.router, prefix="/api")
app.include_router(model_providers.router, prefix="/api")
app.include_router(local_llm.router, prefix="/api")
app.include_router(git.router, prefix="/api")
app.include_router(mcp.router, prefix="/api")
app.include_router(skills.router)
app.include_router(terminal.router)


@app.get("/api/health")
def health():
    from .agent.core import _resolve_tool_mode

    current = settings_store.load()
    provider = "mock" if not current.get("api_key") else current.get("provider", "auto")
    result = {
        "status": "ok",
        "provider": provider,
        "model": current.get("model"),
        "tools": len(registry.list()),
        "tool_mode": _resolve_tool_mode(None, None, current),
    }
    logger.debug("健康检查: %s", result)
    return result
