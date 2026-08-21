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

_DEEPSEEK_VISION_MODEL = "deepseek-v4-flash-vision-exp"
_DEEPSEEK_DEFAULT_BASE = "https://api.deepseek.com"
_GLM_DEFAULT_MODEL = "glm-4.6v-flash"


def _looks_like_image_url(url: str) -> bool:
    """True when the URL path ends with a supported image extension."""
    path = url.split("?", 1)[0].split("#", 1)[0]
    return bool(_IMAGE_URL_EXT_RE.search(path))


def _call_glm(client, model: str, img_ref: str) -> str:
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
                thinking={"type": "enabled"},
            )
            return response.choices[0].message.content
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            detail = str(exc)
            retriable = any(
                token in detail for token in ("429", "1305", "502", "503")
            )
            if not retriable or attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    assert last_error is not None
    raise last_error


def _call_deepseek(client, model: str, img_ref: str) -> str:
    """Call DeepSeek's vision model (OpenAI-compatible API) with retries.

    ``img_ref`` is either a remote URL or a ``data:image/...;base64,...`` URI.
    """
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


def _find_vision_entry(settings: dict) -> dict | None:
    """The model entry whose name is the DeepSeek vision model."""
    for entry in _model_entries(settings):
        if str(entry.get("model") or "") == _DEEPSEEK_VISION_MODEL:
            return entry
    return None


def _find_glm_entry(settings: dict) -> dict | None:
    """A configured GLM vision model entry (glm-4.xv / glm-4v style names)."""
    for entry in _model_entries(settings):
        name = str(entry.get("model") or "").lower()
        if name.startswith("glm-") and "v" in name and entry.get("api_key"):
            return entry
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
            or _GLM_DEFAULT_MODEL,
        )
    entry = _find_glm_entry(settings)
    if entry and entry.get("api_key"):
        return (
            str(entry.get("api_key")),
            str(entry.get("base_url") or ""),
            str(entry.get("model") or _GLM_DEFAULT_MODEL),
        )
    return None


def _resolve_deepseek(settings: dict) -> tuple[str, str]:
    """(api_key, base_url) for the DeepSeek vision fallback."""
    vision = _find_vision_entry(settings)
    if vision and vision.get("api_key"):
        return (
            str(vision.get("api_key")),
            str(vision.get("base_url") or _DEEPSEEK_DEFAULT_BASE),
        )
    active = active_model(settings)
    if (
        active
        and str(active.get("model") or "").startswith("deepseek")
        and active.get("api_key")
    ):
        return (
            str(active.get("api_key")),
            str(active.get("base_url") or _DEEPSEEK_DEFAULT_BASE),
        )
    env_key = os.getenv("DEEPSEEK_API_KEY")
    if env_key:
        return env_key, os.getenv("DEEPSEEK_BASE_URL") or _DEEPSEEK_DEFAULT_BASE
    return "", _DEEPSEEK_DEFAULT_BASE


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


def _print_err(message: str) -> None:
    print(json.dumps({"success": False, "message": message}, ensure_ascii=False))


def _run_glm(api_key: str, base_url: str, model: str, img_ref: str) -> str:
    from zhipuai import ZhipuAI

    client_kwargs: dict[str, str] = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = ZhipuAI(**client_kwargs)
    return _call_glm(client, model, img_ref)


def _run_deepseek(api_key: str, base_url: str, img_ref: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url)
    return _call_deepseek(client, _DEEPSEEK_VISION_MODEL, img_ref)


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    params = data.get("params") or {}
    url = str(params.get("url") or "").strip()
    raw = str(params.get("file_path") or "").strip()

    settings = settings_store.load()
    glm = _resolve_glm(settings)

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
        try:
            if glm is not None:
                content = _run_glm(glm[0], glm[1], glm[2], url)
            else:
                api_key, base_url = _resolve_deepseek(settings)
                if not api_key:
                    _print_err(
                        "未配置视觉模型 API Key：请在设置中配置 GLM（推荐，免费）"
                        f"或 {_DEEPSEEK_VISION_MODEL} 对应的 API Key"
                    )
                    return
                content = _run_deepseek(api_key, base_url, url)
            _print_ok(url.rsplit("/", 1)[-1] or url, url, content)
        except Exception as exc:  # noqa: BLE001
            detail = str(exc)
            if glm is not None and ("429" in detail or "1305" in detail):
                _print_err(
                    "GLM 免费模型当前繁忙，已自动重试仍失败，请稍后再试；"
                    "如持续限流，可切换模型 glm-4.6v-flashx"
                )
            else:
                provider = "GLM" if glm is not None else "DeepSeek 视觉模型"
                _print_err(f"{provider} 调用失败: {detail}")
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

    try:
        if glm is not None:
            img_ref = base64.b64encode(path.read_bytes()).decode("utf-8")
            content = _run_glm(glm[0], glm[1], glm[2], img_ref)
        else:
            api_key, base_url = _resolve_deepseek(settings)
            if not api_key:
                _print_err(
                    "未配置视觉模型 API Key：请在设置中配置 GLM（推荐，免费）"
                    f"或 {_DEEPSEEK_VISION_MODEL} 对应的 API Key"
                )
                return
            mime = _IMAGE_MIME.get(path.suffix.lower(), "image/png")
            b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
            img_ref = f"data:{mime};base64,{b64}"
            content = _run_deepseek(api_key, base_url, img_ref)
        _print_ok(path.name, str(path), content)
    except Exception as exc:  # noqa: BLE001
        detail = str(exc)
        if glm is not None and ("429" in detail or "1305" in detail):
            _print_err(
                "GLM 免费模型当前繁忙，已自动重试仍失败，请稍后再试；"
                "如持续限流，可切换模型 glm-4.6v-flashx"
            )
        else:
            provider = "GLM" if glm is not None else "DeepSeek 视觉模型"
            _print_err(f"{provider} 调用失败: {detail}")


if __name__ == "__main__":
    main()
