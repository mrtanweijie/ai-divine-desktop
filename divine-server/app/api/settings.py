from __future__ import annotations

from fastapi import APIRouter

from ..config import settings_store, workspace_dir
from ..schemas import SettingsUpdate
from ..tools.registry import registry

router = APIRouter(prefix="/settings", tags=["settings"])


def _public(settings: dict) -> dict:
    return {
        "provider": settings.get("provider", "auto"),
        "base_url": settings.get("base_url", ""),
        "model": settings.get("model", ""),
        "has_api_key": bool(settings.get("api_key")),
        "workspace_dir": str(workspace_dir()),
        "think_default": bool(settings.get("think_default", False)),
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
    current.update(updates)
    settings_store.save(current)
    return _public(current)
