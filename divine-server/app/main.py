from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .api import (
    calendar_events,
    chat,
    files,
    local_llm,
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
    await scheduler.start()
    logger.info("=== 侧边端就绪 ===")
    yield
    logger.info("=== 侧边端关闭 ===")
    await scheduler.stop()
    terminal.shutdown_terminal()
    from .tools.bg_process import bg_manager

    await bg_manager.shutdown_all()
    # 停止 llama-server
    try:
        from .agent.local_llm import get_manager

        get_manager().stop()
    except Exception:
        pass


app = FastAPI(
    title="AI Divine",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
app.include_router(local_llm.router, prefix="/api")
app.include_router(skills.router)
app.include_router(terminal.router)


@app.get("/api/health")
def health():
    from .agent.llm import _resolve_tool_mode

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
