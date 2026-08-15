from __future__ import annotations

import logging

from fastapi import APIRouter

from ..config import settings_store, workspace_dir
from ..schemas import SettingsUpdate
from ..tools.registry import registry

router = APIRouter(prefix="/settings", tags=["settings"])
logger = logging.getLogger("divine.settings")


def _public(settings: dict) -> dict:
    return {
        "provider": settings.get("provider", "auto"),
        "base_url": settings.get("base_url", ""),
        "model": settings.get("model", ""),
        "has_api_key": bool(settings.get("api_key")),
        "has_glm_key": bool(settings.get("glm_api_key")),
        "workspace_dir": str(workspace_dir()),
        "username": settings.get("username", "用户"),
        "think_default": bool(settings.get("think_default", False)),
        "reasoning_effort": settings.get("reasoning_effort", "high"),
        "context_limit": int(settings.get("context_limit", 20)),
        "tools": registry.list(),
    }


@router.get("")
def get_settings():
    return _public(settings_store.load())


@router.put("")
def update_settings(body: SettingsUpdate):
    current = settings_store.load()
    updates = body.model_dump(exclude_unset=True)
    if updates.get("api_key") == "":
        updates["api_key"] = ""
    if updates.get("glm_api_key") == "":
        updates["glm_api_key"] = ""
    if updates.get("username") == "":
        updates["username"] = "用户"
    current.update(updates)
    settings_store.save(current)
    logger.info(
        "settings updated provider=%s model=%s has_api_key=%s",
        current.get("provider"),
        current.get("model"),
        bool(current.get("api_key")),
    )
    return _public(current)
