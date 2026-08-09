from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .api import (
    calendar_events,
    chat,
    files,
    projects,
    scheduled_tasks,
    sessions,
    settings,
    terminal,
)
from .config import cors_origins, ensure_directories, settings_store
from .tools.registry import registry


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_directories()
    db.init_db()
    yield
    terminal.shutdown_terminal()


app = FastAPI(
    title="AI Divine",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(scheduled_tasks.router, prefix="/api")
app.include_router(calendar_events.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(terminal.router)


@app.get("/api/health")
def health():
    current = settings_store.load()
    provider = "mock" if not current.get("api_key") else current.get("provider", "auto")
    return {
        "status": "ok",
        "provider": provider,
        "model": current.get("model"),
        "tools": len(registry.list()),
    }
