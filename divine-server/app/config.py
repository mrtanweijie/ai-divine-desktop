from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def data_root() -> Path:
    env_dir = os.getenv("DIVINE_DATA_DIR")
    if env_dir:
        path = Path(env_dir).expanduser()
        return path.resolve()
    return BACKEND_DIR / "data"


def workspace_root() -> Path:
    env_dir = os.getenv("DIVINE_WORKSPACE_DIR")
    if env_dir:
        path = Path(env_dir).expanduser()
        return path.resolve()
    return BACKEND_DIR / "workspace"


def projects_root() -> Path:
    env_dir = os.getenv("DIVINE_PROJECTS_DIR")
    if env_dir:
        path = Path(env_dir).expanduser()
        if not path.is_absolute():
            path = Path.home() / path
        return path.resolve()
    return Path.home() / "Documents" / "Divine"


class SettingsStore:
    """Small local settings file layered over environment defaults."""

    def __init__(self) -> None:
        self.path = data_root() / "settings.json"

    def load(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "host": os.getenv("HOST", "127.0.0.1"),
            "port": int(os.getenv("PORT", "8019")),
            "provider": os.getenv("AI_PROVIDER", "auto"),
            "glm_api_key": os.getenv("GLM_API_KEY", ""),
            "glm_base_url": os.getenv(
                "GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"
            ),
            "glm_model": os.getenv("GLM_MODEL", "glm-4.6v-flash"),
            "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
            "model": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            "username": "用户",
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
        if data.get("model") in ("", "local", "mock"):
            data["model"] = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        if not data.get("username"):
            data["username"] = "用户"
        data["host"] = os.getenv("HOST", data.get("host", "127.0.0.1"))
        data["port"] = int(os.getenv("PORT", data.get("port", "8019")))
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
    return workspace_root()


def _project_slug_for(workspace: Path) -> str:
    import re

    workspace = workspace.resolve()
    name = workspace.name.strip()
    if _is_git_workspace(workspace):
        current = workspace
        while current != current.parent:
            if (current / ".git").exists():
                name = current.name.strip()
                break
            current = current.parent
    slug = re.sub(r"[^\w\u4e00-\u9fff.\-]+", "_", name).strip("._ ")
    return slug or "workspace"


def _project_slug() -> str:
    return _project_slug_for(workspace_dir())


def _is_git_workspace(workspace: Path) -> bool:
    current = workspace.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return True
    return False


def output_dir() -> Path:
    return output_dir_for_workspace(workspace_dir())


def output_dir_for_workspace(workspace: Path) -> Path:
    configured = settings_store.load().get("output_dir")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = Path.home() / path
        return path.resolve() / _project_slug_for(workspace)
    workspace = workspace.resolve()
    if _is_git_workspace(workspace):
        return data_root() / "outputs" / _project_slug_for(workspace)
    return workspace


def data_dir() -> Path:
    configured = os.getenv("DB_PATH")
    path = Path(configured).expanduser() if configured else data_root()
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
    raw = os.getenv("CORS_ORIGINS", "http://localhost:8010,http://127.0.0.1:8010,tauri://localhost,http://tauri.localhost,https://tauri.localhost")
    return [item.strip() for item in raw.split(",") if item.strip()]


def ensure_directories() -> None:
    workspace_dir().mkdir(parents=True, exist_ok=True)
    output_root = output_dir()
    for category in (
        "documents",
        "spreadsheets",
        "notes",
        "pdf",
        "presentations",
        "diagrams",
        "html",
        "svg",
    ):
        (output_root / category).mkdir(parents=True, exist_ok=True)
    db_path().parent.mkdir(parents=True, exist_ok=True)
