from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


class SettingsStore:
    """Small local settings file layered over environment defaults."""

    def __init__(self) -> None:
        self.path = BACKEND_DIR / "data" / "settings.json"

    def load(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "host": os.getenv("HOST", "127.0.0.1"),
            "port": int(os.getenv("PORT", "8010")),
            "provider": os.getenv("AI_PROVIDER", "auto"),
            "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
            "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            "think_default": False,
            "context_limit": 20,
        }
        if self.path.exists():
            try:
                stored = json.loads(self.path.read_text(encoding="utf-8"))
                data.update({k: v for k, v in stored.items() if k != "api_key"})
                if stored.get("api_key"):
                    data["api_key"] = stored["api_key"]
            except (json.JSONDecodeError, OSError):
                pass
        return data

    def save(self, values: dict[str, Any]) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(values, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return values


settings_store = SettingsStore()


def workspace_dir() -> Path:
    configured = settings_store.load().get("workspace_dir")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = (BACKEND_DIR / path).resolve()
        return path
    return BACKEND_DIR / "workspace"


def data_dir() -> Path:
    configured = os.getenv("DB_PATH")
    path = Path(configured).expanduser() if configured else BACKEND_DIR / "data"
    if not path.is_absolute():
        path = (BACKEND_DIR / path).resolve()
    return path


def db_path() -> Path:
    configured = os.getenv("DB_PATH")
    if configured and configured.endswith(".db"):
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = (BACKEND_DIR / path).resolve()
        return path
    return data_dir() / "ai_workspace.db"


def cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [item.strip() for item in raw.split(",") if item.strip()]


def ensure_directories() -> None:
    workspace_dir().mkdir(parents=True, exist_ok=True)
    for category in ("documents", "spreadsheets", "notes"):
        (workspace_dir() / category).mkdir(parents=True, exist_ok=True)
    db_path().parent.mkdir(parents=True, exist_ok=True)
