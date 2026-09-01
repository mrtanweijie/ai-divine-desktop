from __future__ import annotations

import copy
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


DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"

# 本地 LLM 默认配置（settings_store 默认值与此处常量同源，禁止散落魔法值）
DEFAULT_LOCAL_LLM_PORT = 8016
DEFAULT_LOCAL_LLM_THRESHOLD = 0.75

# Tool-calling paradigm per model entry:
# - "auto":   resolve to native function calling (current behavior)
# - "native": force native function calling (bind_tools)
# - "react":  force ReAct text-mode tool calling (Thought/Action loop)
TOOL_MODES = ("auto", "native", "react")


def _normalize_tool_mode(value: Any) -> str:
    mode = str(value or "").strip()
    return mode if mode in TOOL_MODES else "auto"


def default_model_entry() -> dict[str, Any]:
    """A single model entry mirroring the environment defaults."""
    return {
        "id": "default",
        "name": "DeepSeek V4 Flash",
        "provider": os.getenv("AI_PROVIDER", "auto"),
        "model": os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL),
        "base_url": os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL),
        "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
        "active": True,
        "tool_mode": "auto",
    }


def normalize_models(
    models: Any, legacy: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Coerce a raw models list into a stable shape with exactly one active entry."""
    legacy = legacy or {}
    if not isinstance(models, list) or not models:
        # First run (or legacy settings.json without a models list): build one
        # entry from the top-level/env fields so nothing is lost in migration.
        models = [
            {
                "id": "default",
                "name": str(legacy.get("model") or "") or DEFAULT_MODEL,
                "provider": legacy.get("provider")
                or os.getenv("AI_PROVIDER", "auto"),
                "model": legacy.get("model") or DEFAULT_MODEL,
                "base_url": legacy.get("base_url") or DEFAULT_BASE_URL,
                "api_key": legacy.get("api_key") or "",
                "active": True,
                "tool_mode": _normalize_tool_mode(legacy.get("tool_mode")),
            }
        ]
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(models):
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider") or legacy.get("provider") or "langchain")
        if provider not in ("auto", "langchain", "mock"):
            provider = "langchain"
        vendor = str(item.get("vendor") or legacy.get("vendor") or "").strip()
        custom_models = str(
            item.get("custom_models") or legacy.get("custom_models") or ""
        ).strip()
        raw_model = str(item.get("model") or "").strip()
        if vendor == "custom":
            # 自定义提供方：不允许回退到默认模型（否则标题会变成 deepseek-v4-flash）。
            # model 为空时取自定义模型列表的第一个作为展示模型。
            model = raw_model or next(
                (s.strip() for s in custom_models.split(",") if s.strip()), ""
            )
        else:
            model = raw_model or DEFAULT_MODEL
            if model in ("", "local", "mock"):
                model = DEFAULT_MODEL
        raw_base_url = str(
            item.get("base_url") or legacy.get("base_url") or ""
        ).strip()
        base_url = raw_base_url or ("" if vendor == "custom" else DEFAULT_BASE_URL)
        entry = {
            "id": str(item.get("id") or "").strip() or f"model-{index + 1}",
            "name": str(item.get("name") or "").strip() or model,
            "provider": provider,
            "model": model,
            "base_url": base_url,
            "api_key": str(item.get("api_key") or ""),
            "active": bool(item.get("active", False)),
            "tool_mode": _normalize_tool_mode(
                item.get("tool_mode") or legacy.get("tool_mode")
            ),
            "custom_models": custom_models,
            "vendor": vendor,
        }
        normalized.append(entry)
    if not normalized:
        normalized = [default_model_entry()]
    active_ids = [entry["id"] for entry in normalized if entry["active"]]
    if not active_ids:
        normalized[0]["active"] = True
    elif len(active_ids) > 1:
        keep = active_ids[0]
        for entry in normalized:
            entry["active"] = entry["id"] == keep
    return normalized


def active_model(settings: dict[str, Any]) -> dict[str, Any]:
    """Return the active model entry, falling back to the first entry."""
    models = settings.get("models")
    if isinstance(models, list):
        for entry in models:
            if isinstance(entry, dict) and entry.get("active"):
                return entry
        if models and isinstance(models[0], dict):
            return models[0]
    return default_model_entry()


def mirror_active(settings: dict[str, Any]) -> dict[str, Any]:
    """Mirror the active model entry onto the legacy top-level fields so all
    existing consumers (LLM providers, PDF engine, health endpoint) keep
    working unchanged."""
    entry = active_model(settings)
    settings["provider"] = entry.get("provider", "auto")
    settings["model"] = entry.get("model", DEFAULT_MODEL)
    settings["base_url"] = entry.get("base_url", DEFAULT_BASE_URL)
    settings["api_key"] = entry.get("api_key", "")
    return settings


def merge_model_updates(
    stored: Any, submitted: Any
) -> list[dict[str, Any]]:
    """Merge model entries submitted by the settings UI into the stored list.

    Empty (or missing) api_key keeps the previously saved key, matching the
    legacy single-model behavior where the frontend never echoes keys back.
    """
    stored_list = stored if isinstance(stored, list) else []
    stored_by_id: dict[str, dict[str, Any]] = {}
    for entry in stored_list:
        if isinstance(entry, dict) and entry.get("id"):
            stored_by_id[str(entry["id"])] = entry
    merged: list[dict[str, Any]] = []
    for index, item in enumerate(submitted or []):
        if not isinstance(item, dict):
            continue
        entry_id = str(item.get("id") or "").strip() or f"model-{index + 1}"
        prev = stored_by_id.get(entry_id) or {}
        api_key = item.get("api_key")
        if api_key in (None, ""):
            api_key = prev.get("api_key", "")
        merged.append(
            {
                "id": entry_id,
                "name": str(item.get("name") or prev.get("name") or "").strip(),
                "provider": (
                    item.get("provider") or prev.get("provider") or "langchain"
                ),
                "model": str(
                    item.get("model") or prev.get("model") or ""
                ).strip(),
                "base_url": str(
                    item.get("base_url") or prev.get("base_url") or ""
                ).strip(),
                "api_key": str(api_key or ""),
                "active": bool(item.get("active", False)),
                "tool_mode": _normalize_tool_mode(
                    item.get("tool_mode") or prev.get("tool_mode")
                ),
                "custom_models": str(
                    item.get("custom_models") or prev.get("custom_models") or ""
                ).strip(),
                "vendor": str(
                    item.get("vendor") or prev.get("vendor") or ""
                ).strip(),
            }
        )
    return normalize_models(merged, {})


def apply_legacy_to_active(
    settings: dict[str, Any], updates: dict[str, Any]
) -> dict[str, Any]:
    """Apply legacy single-model updates (provider/model/base_url/api_key)
    to the active entry so old clients keep working against the new layout."""
    models = settings.get("models")
    if not isinstance(models, list) or not models:
        settings["models"] = normalize_models(None, settings)
        models = settings["models"]
    target = next(
        (entry for entry in models if entry.get("active")), models[0]
    )
    for key in ("provider", "model", "base_url"):
        if key in updates and updates[key] not in (None, ""):
            if key == "model" and updates[key] in ("local", "mock"):
                # legacy demo sentinels are not real model names
                continue
            target[key] = updates[key]
    if updates.get("api_key") not in (None, ""):
        target["api_key"] = updates["api_key"]
    settings["models"] = normalize_models(models, {})
    return settings


def projects_root() -> Path:
    env_dir = os.getenv("DIVINE_PROJECTS_DIR")
    if env_dir:
        path = Path(env_dir).expanduser()
        if not path.is_absolute():
            path = Path.home() / path
        return path.resolve()
    return Path.home() / "Documents" / "Divine"


class SettingsStore:
    """Small local settings file layered over environment defaults.

    ``load()`` results are cached in memory and invalidated by file mtime, so
    hot paths (settings are read dozens of times per request) skip the disk
    read + JSON parse + model normalization on every call. Each ``load()``
    returns a deep copy, so callers may freely mutate the dict they receive
    without poisoning the cache; ``save()`` refreshes both cache and mtime.
    """

    def __init__(self) -> None:
        self.path = data_root() / "settings.json"
        self._cache: dict[str, Any] | None = None
        self._mtime_ns: int | None = None
        # 设置文件含 API Key：确保历史遗留文件也收紧为仅本人可读写
        # （Windows 无 POSIX 权限语义，跳过）。
        if os.name != "nt":
            try:
                self.path.chmod(0o600)
            except OSError:
                pass

    def load(self) -> dict[str, Any]:
        try:
            mtime_ns = self.path.stat().st_mtime_ns
        except OSError:
            mtime_ns = None
        if self._cache is not None and mtime_ns == self._mtime_ns:
            return copy.deepcopy(self._cache)
        data = self._build()
        self._cache = data
        self._mtime_ns = mtime_ns
        return copy.deepcopy(data)

    def _build(self) -> dict[str, Any]:
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
            "reasoning_effort": os.getenv(
                "DEEPSEEK_REASONING_EFFORT", "high"
            ),
            "context_limit": 30,
            # 桌面全局快捷键（唤起/隐藏主窗口）
            "global_shortcut_enabled": True,
            # 本地模型配置
            "local_llm_enabled": False,
            "local_llm_mode": "keyword",  # "keyword" | "local" | "hybrid"
            "local_llm_port": DEFAULT_LOCAL_LLM_PORT,
            "local_llm_model": "",
            "local_llm_ctx_size": 4096,
            "local_llm_threshold": DEFAULT_LOCAL_LLM_THRESHOLD,
            # 本地预整理（输入侧预处理）
            "local_llm_preprocess_enabled": True,
            "local_llm_preprocess_auto": True,
            "local_llm_preprocess_threshold": 800,  # token 估算阈值（estimate_tokens）
            "local_llm_preprocess_code_skip": True,
            "installed_models": [],  # [{"id": "...", "name": "...", "path": "...", "size": 0, "enabled": False}]
        }
        if self.path.exists():
            try:
                stored = json.loads(self.path.read_text(encoding="utf-8"))
                data.update({k: v for k, v in stored.items() if k != "api_key"})
                if stored.get("api_key"):
                    data["api_key"] = stored["api_key"]
            except (json.JSONDecodeError, OSError):
                pass
        data["models"] = normalize_models(data.get("models"), data)
        data = mirror_active(data)
        if not data.get("username"):
            data["username"] = "用户"
        data["host"] = os.getenv("HOST", data.get("host", "127.0.0.1"))
        data["port"] = int(os.getenv("PORT", data.get("port", "8019")))
        return data

    def save(self, values: dict[str, Any]) -> dict[str, Any]:
        if "models" in values:
            values["models"] = normalize_models(values.get("models"), values)
            values = mirror_active(values)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(values, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # 写入后保持 0600：write_text 不会重置已存在文件的权限，
        # 但若文件被重建（删除后新建）会按 umask 回落，这里强制固定。
        if os.name != "nt":
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
        self._cache = copy.deepcopy(values)
        try:
            self._mtime_ns = self.path.stat().st_mtime_ns
        except OSError:
            self._mtime_ns = None
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
    plugins_dir().mkdir(parents=True, exist_ok=True)


def plugins_dir() -> Path:
    """Directory for user-installed tool plugins (loaded at startup)."""
    return data_root() / "plugins"
