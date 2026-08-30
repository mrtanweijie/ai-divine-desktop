from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter

from ..config import (
    apply_legacy_to_active,
    merge_model_updates,
    settings_store,
    workspace_dir,
)
from ..schemas import SettingsUpdate
from ..tools.registry import registry

router = APIRouter(prefix="/settings", tags=["settings"])
logger = logging.getLogger("divine.settings")


def _public(settings: dict) -> dict:
    models = settings.get("models") or []
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
        # 桌面全局快捷键
        "global_shortcut_enabled": bool(
            settings.get("global_shortcut_enabled", True)
        ),
        # 本地模型配置（意图识别模式等）
        "local_llm_enabled": bool(settings.get("local_llm_enabled", False)),
        "local_llm_mode": settings.get("local_llm_mode", "keyword"),
        "local_llm_port": int(settings.get("local_llm_port", 8016)),
        "local_llm_model": settings.get("local_llm_model", ""),
        "local_llm_ctx_size": int(settings.get("local_llm_ctx_size", 4096)),
        "local_llm_threshold": float(settings.get("local_llm_threshold", 0.75)),
        # 本地预整理（输入侧预处理）
        "local_llm_preprocess_enabled": bool(
            settings.get("local_llm_preprocess_enabled", True)
        ),
        "local_llm_preprocess_auto": bool(
            settings.get("local_llm_preprocess_auto", True)
        ),
        "local_llm_preprocess_threshold": int(
            settings.get("local_llm_preprocess_threshold", 800)
        ),
        "local_llm_preprocess_code_skip": bool(
            settings.get("local_llm_preprocess_code_skip", True)
        ),
        "tools": registry.list(),
        "models": [
            {
                "id": entry.get("id"),
                "name": entry.get("name", ""),
                "provider": entry.get("provider", "langchain"),
                "model": entry.get("model", ""),
                "base_url": entry.get("base_url", ""),
                "has_api_key": bool(entry.get("api_key")),
                "active": bool(entry.get("active", False)),
                "tool_mode": entry.get("tool_mode", "auto"),
                "custom_models": entry.get("custom_models", ""),
                "vendor": entry.get("vendor", ""),
            }
            for entry in models
            if isinstance(entry, dict)
        ],
    }


@router.get("")
def get_settings():
    settings = settings_store.load()
    # 本地模型运行时，动态注入"本地模型"条目（不持久化，先注入再经 _public
    # 白名单转换，保证 has_api_key 等字段齐全），聊天模型切换器即可选它直接对话
    try:
        from ..agent.core import get_manager, local_model_entry

        manager = get_manager()
        if manager.is_ready():
            models = settings.get("models") or []
            settings = dict(settings)
            # 用当前运行的模型名展示（如 Qwen2.5-0.5B-Instruct）
            entry = local_model_entry(manager.port, manager.active_model_name() or "本地模型")
            settings["models"] = models + [entry]
    except Exception:
        pass
    return _public(settings)


@router.put("")
def update_settings(body: SettingsUpdate):
    current = settings_store.load()
    updates = body.model_dump(exclude_unset=True)

    if updates.get("models") is not None:
        # Multi-model save: merge the submitted list, keeping stored api keys
        # for entries whose key field was left empty.
        submitted = updates.pop("models")
        current["models"] = merge_model_updates(
            current.get("models") or [], submitted
        )
    else:
        # Legacy single-model save: apply to the active entry as well, so old
        # clients keep working against the new layout.
        current = apply_legacy_to_active(current, updates)

    if updates.get("api_key") == "":
        updates["api_key"] = ""
    if updates.get("glm_api_key") == "":
        updates["glm_api_key"] = ""
    if updates.get("username") == "":
        updates["username"] = "用户"
    current.update(updates)
    settings_store.save(current)
    logger.info(
        "settings updated provider=%s model=%s models=%d has_api_key=%s",
        current.get("provider"),
        current.get("model"),
        len(current.get("models") or []),
        bool(current.get("api_key")),
    )
    return _public(current)


def _is_deepseek(base_url: str) -> bool:
    return "deepseek" in base_url.lower()


@router.get("/balance")
def get_balance(model_id: str | None = None):
    """Query the DeepSeek account balance for a model entry.

    Only works for DeepSeek endpoints (base_url contains "deepseek").
    Returns ``{"available": false}`` for non-DeepSeek models.
    """
    current = settings_store.load()
    models = current.get("models") or []
    entry = None
    if model_id:
        entry = next(
            (m for m in models if isinstance(m, dict) and m.get("id") == model_id),
            None,
        )
    if entry is None:
        entry = next(
            (m for m in models if isinstance(m, dict) and m.get("active")),
            None,
        )
    if entry is None:
        return {"available": False, "error": "no model configured"}

    base_url = str(entry.get("base_url") or "").strip()
    api_key = str(entry.get("api_key") or "").strip()
    if not _is_deepseek(base_url):
        return {"available": False, "reason": "not_deepseek"}
    if not api_key:
        return {"available": False, "error": "no_api_key"}

    url = f"{base_url.rstrip('/')}/user/balance"
    try:
        resp = httpx.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning(
                "balance query failed status=%s body=%s",
                resp.status_code,
                resp.text[:200],
            )
            return {"available": False, "error": f"http_{resp.status_code}"}
        data = resp.json()
        infos = data.get("balance_infos") or []
        total = infos[0].get("total_balance", "0") if infos else "0"
        currency = infos[0].get("currency", "CNY") if infos else "CNY"
        return {
            "available": bool(data.get("is_available")),
            "balance": total,
            "currency": currency,
        }
    except Exception as exc:
        logger.warning("balance query error: %s", exc)
        return {"available": False, "error": str(exc)}
