import base64
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.config import active_model, settings_store  # noqa: E402
from app.file_types import VISION_IMAGE_EXTENSIONS  # noqa: E402

_VISION_SUFFIXES = tuple(sorted(VISION_IMAGE_EXTENSIONS))
_VISION_EXT_ALT = "|".join(
    sorted(ext.lstrip(".") for ext in VISION_IMAGE_EXTENSIONS)
)

_IMAGE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

# Only URLs that look like images (path ends with a supported suffix) are
# accepted; arbitrary web links must not be sent to the vision API.
_IMAGE_URL_EXT_RE = re.compile(rf"\.(?:{_VISION_EXT_ALT})$", re.IGNORECASE)

# Known multimodal model prefixes that support image understanding
# This list is extensible - add new multimodal model prefixes here
_MULTIMODAL_MODEL_PREFIXES = [
    "mimo-",
    "gpt-5",
    "gpt-4o",
    "gpt-4-vision",
    "claude-3",
    "gemini",
    "deepseek-v4-flash-vision",
    "glm-5v",
    "glm-4.6v",
    "glm-4v",
    "qwen-vl",
    "minimax-",
]


def _looks_like_image_url(url: str) -> bool:
    """True when the URL path ends with a supported image extension."""
    path = url.split("?", 1)[0].split("#", 1)[0]
    return bool(_IMAGE_URL_EXT_RE.search(path))


def _is_multimodal_model(model_name: str) -> bool:
    """Check if a model name suggests multimodal capability."""
    model_lower = model_name.lower()
    return any(model_lower.startswith(prefix) for prefix in _MULTIMODAL_MODEL_PREFIXES)


def _call_multimodal(client, model: str, img_ref: str) -> str:
    """Generic multimodal model call with image understanding."""
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": img_ref},
                            },
                            {
                                "type": "text",
                                "text": "请描述这张图片的内容，尽量详细。",
                            },
                        ],
                    }
                ],
            )
            return response.choices[0].message.content
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            detail = str(exc)
            retriable = any(
                token in detail for token in ("429", "502", "503")
            )
            if not retriable or attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    assert last_error is not None
    raise last_error


def _model_entries(settings: dict) -> list[dict]:
    models = settings.get("models")
    if not isinstance(models, list):
        return []
    return [entry for entry in models if isinstance(entry, dict)]


def _resolve_by_model_id(
    settings: dict, model_id: str
) -> dict | None:
    """Resolve an (possibly expanded) model id to a model entry.

    ``model_id`` may be ``{baseId}::{modelName}`` (the chat switcher expands
    providers into their full model list); the base id selects the entry and
    the model name overrides its ``model`` field.
    """
    if not model_id:
        return None
    base_id, _, model_name = model_id.partition("::")
    for entry in _model_entries(settings):
        if str(entry.get("id") or "") == base_id:
            if model_name.strip():
                resolved = dict(entry)
                resolved["model"] = model_name.strip()
                return resolved
            return entry
    return None


def _find_multimodal_entry(settings: dict) -> dict | None:
    """Find a configured multimodal model entry.

    Active entry wins first; otherwise the first configured multimodal entry
    (in order). This way, even if the active default model is text-only (e.g.
    deepseek-v4-flash), a configured vision-capable model (e.g. mimo-*) is used
    instead of falling back to GLM.
    """
    entries = _model_entries(settings)
    active = active_model(settings)
    active_id = str(active.get("id") or "") if active else ""
    # 优先 active 条目
    for entry in entries:
        if str(entry.get("id") or "") == active_id:
            if (
                _is_multimodal_model(str(entry.get("model") or ""))
                and entry.get("api_key")
            ):
                return entry
    # 再按配置顺序找第一个多模态条目
    for entry in entries:
        model_name = str(entry.get("model") or "")
        if _is_multimodal_model(model_name) and entry.get("api_key"):
            return entry
    return None


def _resolve_multimodal(settings: dict) -> tuple[str, str, str] | None:
    """(api_key, base_url, model) when a multimodal model is configured, else None."""
    entry = _find_multimodal_entry(settings)
    if entry and entry.get("api_key"):
        return (
            str(entry.get("api_key")),
            str(entry.get("base_url") or ""),
            str(entry.get("model") or ""),
        )
    return None


def _resolve_vision_provider(
    settings: dict, model_id: str | None
) -> tuple[str, str, str, bool] | None:
    """Pick the provider for image understanding, in priority order:

    1. The session's actual model (from ``model_id``) if it is multimodal;
    2. Any configured multimodal entry (active first, then in order);
    3. None (caller falls back to GLM).

    Returns ``(api_key, base_url, model, is_session_model)`` — the last flag
    tells the caller whether the model is the current session's model or a
    fallback entry from the settings, so error messages can be accurate.
    """
    if model_id:
        entry = _resolve_by_model_id(settings, model_id)
        if entry and _is_multimodal_model(str(entry.get("model") or "")) and entry.get(
            "api_key"
        ):
            return (
                str(entry.get("api_key")),
                str(entry.get("base_url") or ""),
                str(entry.get("model") or ""),
                True,
            )
    resolved = _resolve_multimodal(settings)
    if resolved:
        return (*resolved, False)
    return None


def _resolve_glm(settings: dict) -> tuple[str, str, str] | None:
    """(api_key, base_url, model) when GLM vision is configured, else None."""
    key = os.getenv("GLM_API_KEY") or settings.get("glm_api_key") or ""
    if key:
        return (
            key,
            os.getenv("GLM_BASE_URL") or settings.get("glm_base_url") or "",
            os.getenv("GLM_MODEL")
            or settings.get("glm_model")
            or "glm-4.6v-flash",
        )
    return None


def _resolve_deepseek(settings: dict) -> tuple[str, str]:
    """(api_key, base_url) for the DeepSeek vision fallback."""
    active = active_model(settings)
    if (
        active
        and str(active.get("model") or "").startswith("deepseek")
        and active.get("api_key")
    ):
        return (
            str(active.get("api_key")),
            str(active.get("base_url") or "https://api.deepseek.com"),
        )
    env_key = os.getenv("DEEPSEEK_API_KEY")
    if env_key:
        return env_key, os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
    return "", "https://api.deepseek.com"


def _print_ok(file_name: str, filepath: str, content: str) -> None:
    print(
        json.dumps(
            {
                "success": True,
                "message": "图片识别完成",
                "file_name": file_name,
                "filepath": filepath,
                "content": content,
            },
            ensure_ascii=False,
        )
    )


def _print_err(message: str, suggested_models: list[dict] | None = None) -> None:
    payload: dict[str, Any] = {
        "success": False,
        "message": message,
    }
    if suggested_models:
        payload["suggested_models"] = suggested_models
    print(json.dumps(payload, ensure_ascii=False))


def _vision_suggestions(
    settings: dict, model_id: str | None
) -> list[dict]:
    """配置里其它支持图片识别的模型（排除当前 model_id 指向的条目），
    供"是否切换模型"的询问使用。"""
    provider_labels = {
        "deepseek": "DeepSeek",
        "xiaomi": "Xiaomi (MiMo)",
        "glm": "GLM (智谱)",
        "openai": "OpenAI",
        "minimax": "MiniMax",
        "qwen": "Qwen (通义千问)",
        "custom": "自定义",
    }
    current_base = ""
    if model_id:
        current_base, _, _ = model_id.partition("::")
    suggestions: list[dict] = []
    for entry in _model_entries(settings):
        if not entry.get("api_key"):
            continue
        if str(entry.get("id") or "") == current_base:
            continue
        model_name = str(entry.get("model") or "")
        if _is_multimodal_model(model_name):
            vendor = str(entry.get("vendor") or "")
            provider_label = provider_labels.get(vendor, vendor or "自定义")
            suggestions.append(
                {
                    "id": f"{entry.get('id')}::{model_name}",
                    "name": model_name,
                    "provider": provider_label,
                }
            )
    return suggestions


def _model_label(is_session_model: bool, name: str) -> str:
    """报错文案里的模型归属：是当前会话模型还是配置里回退的模型。"""
    if is_session_model:
        return f"当前会话模型（{name}）"
    return f"配置里已尝试的识别模型（{name}）"


def _recognize(
    settings: dict,
    model_id: str | None,
    img_ref: str,
    file_name: str,
    filepath: str,
) -> None:
    """图片识别：GLM 免费模型优先，繁忙时用会话模型，
    会话模型不支持图片则列出配置里其它支持图片的模型，询问用户是否切换。"""
    glm = _resolve_glm(settings)  # (api_key, base_url, model)
    session_mm = _resolve_vision_provider(settings, model_id)

    # 1) 优先 GLM 免费模型（免费且稳定支持图片）
    if glm is not None:
        try:
            content = _run_multimodal(glm[0], glm[1], glm[2], img_ref)
            _print_ok(file_name, filepath, content)
            return
        except Exception as exc:
            detail = str(exc)
            if "429" in detail or "1305" in detail:
                # GLM 繁忙 → 回退会话模型
                if session_mm is not None:
                    try:
                        content = _run_multimodal(
                            session_mm[0], session_mm[1], session_mm[2], img_ref
                        )
                        _print_ok(file_name, filepath, content)
                        return
                    except Exception as session_exc:
                        suggestions = _vision_suggestions(settings, model_id)
                        _print_err(
                            "GLM 免费模型繁忙，且"
                            + _model_label(session_mm[3], session_mm[2])
                            + "无法识别图片："
                            + str(session_exc)
                            + "。检测到配置里以下模型支持图片识别，是否需要切换？",
                            suggestions,
                        )
                        return
                suggestions = _vision_suggestions(settings, model_id)
                _print_err(
                    "GLM 免费模型当前繁忙，已自动重试仍失败，请稍后再试；"
                    "如持续限流，可切换模型 glm-4.6v-flashx。"
                    + (
                        "配置里以下模型支持图片识别，是否需要切换？"
                        if suggestions
                        else ""
                    ),
                    suggestions,
                )
                return
            # GLM 其它错误 → 同样尝试会话模型后报错
            if session_mm is not None:
                try:
                    content = _run_multimodal(
                        session_mm[0], session_mm[1], session_mm[2], img_ref
                    )
                    _print_ok(file_name, filepath, content)
                    return
                except Exception:
                    pass
            suggestions = _vision_suggestions(settings, model_id)
            _print_err(f"GLM 免费模型调用失败: {detail}", suggestions)
            return

    # 2) 无 GLM key → 用会话模型（若支持图片）
    if session_mm is not None:
        try:
            content = _run_multimodal(
                session_mm[0], session_mm[1], session_mm[2], img_ref
            )
            _print_ok(file_name, filepath, content)
            return
        except Exception as exc:
            suggestions = _vision_suggestions(settings, model_id)
            _print_err(
                f"{_model_label(session_mm[3], session_mm[2])}无法识别图片：{exc}。"
                + (
                    "配置里以下模型支持图片识别，是否需要切换？"
                    if suggestions
                    else ""
                ),
                suggestions,
            )
            return

    # 3) 都没有 → 报错并给出建议
    suggestions = _vision_suggestions(settings, model_id)
    _print_err(
        "未配置图片识别模型：请配置 GLM API Key（免费）"
        + (
            "，或切换到以下支持图片识别的模型？"
            if suggestions
            else "或支持多模态的模型。"
        ),
        suggestions,
    )


def _run_multimodal(api_key: str, base_url: str, model: str, img_ref: str) -> str:
    """Run multimodal model with image understanding."""
    from openai import OpenAI

    client_kwargs: dict[str, str] = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = OpenAI(**client_kwargs)
    return _call_multimodal(client, model, img_ref)


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    params = data.get("params") or {}
    url = str(params.get("url") or "").strip()
    raw = str(params.get("file_path") or "").strip()
    model_id = str(params.get("model_id") or "").strip() or None

    settings = settings_store.load()

    if url:
        if not (url.startswith("http://") or url.startswith("https://")):
            _print_err("图片链接必须以 http:// 或 https:// 开头")
            return
        if not _looks_like_image_url(url):
            _print_err(
                "链接看起来不是图片（URL 不以 "
                + "/".join(ext.lstrip(".") for ext in _VISION_SUFFIXES)
                + " 结尾），已跳过图片识别；如需分析网页内容请使用其他方式。"
            )
            return
        _recognize(settings, model_id, url, url.rsplit("/", 1)[-1] or url, url)
        return

    if not raw:
        _print_err("请提供 file_path（本地图片路径）或 url（图片链接）")
        return

    path = Path(raw)
    if not path.is_absolute():
        path = workspace / path
    path = path.resolve()

    if not path.is_file():
        _print_err(f"文件不存在: {path}")
        return
    if path.stat().st_size > 10 * 1024 * 1024:
        _print_err("图片超过 10MB")
        return
    if path.suffix.lower() not in _VISION_SUFFIXES:
        _print_err(
            "不支持的图片格式（仅支持 "
            + "/".join(ext.lstrip(".") for ext in _VISION_SUFFIXES)
            + "），请先转换格式"
        )
        return

    mime = _IMAGE_MIME.get(path.suffix.lower(), "image/png")
    b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
    img_ref = f"data:{mime};base64,{b64}"
    _recognize(settings, model_id, img_ref, path.name, str(path))


if __name__ == "__main__":
    main()
