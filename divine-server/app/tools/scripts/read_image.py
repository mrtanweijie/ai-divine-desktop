import base64
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.config import active_model, settings_store  # noqa: E402

_IMAGE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}

_DEEPSEEK_VISION_MODEL = "deepseek-v4-flash-vision-exp"
_DEEPSEEK_DEFAULT_BASE = "https://api.deepseek.com"
_GLM_DEFAULT_MODEL = "glm-4.6v-flash"


def _call_glm(client, model: str, img_base: str) -> str:
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
                                "image_url": {"url": img_base},
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


def _call_deepseek(client, model: str, data_uri: str) -> str:
    """Call DeepSeek's vision model (OpenAI-compatible API) with retries."""
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
                                "image_url": {"url": data_uri},
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


def _print_ok(path: Path, content: str) -> None:
    print(
        json.dumps(
            {
                "success": True,
                "message": "图片识别完成",
                "file_name": path.name,
                "filepath": str(path),
                "content": content,
            },
            ensure_ascii=False,
        )
    )


def _print_err(message: str) -> None:
    print(json.dumps({"success": False, "message": message}, ensure_ascii=False))


def _run_glm(settings: dict, api_key: str, base_url: str, model: str, path: Path) -> None:
    try:
        from zhipuai import ZhipuAI

        client_kwargs: dict[str, str] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = ZhipuAI(**client_kwargs)
        img_base = base64.b64encode(path.read_bytes()).decode("utf-8")
        content = _call_glm(client, model, img_base)
        _print_ok(path, content)
    except Exception as exc:  # noqa: BLE001
        detail = str(exc)
        if "429" in detail or "1305" in detail:
            message = (
                "GLM 免费模型当前繁忙，已自动重试仍失败，请稍后再试；"
                "如持续限流，可切换模型 glm-4.6v-flashx"
            )
        else:
            message = f"GLM 调用失败: {detail}"
        _print_err(message)


def _run_deepseek(settings: dict, path: Path) -> None:
    api_key, base_url = _resolve_deepseek(settings)
    if not api_key:
        _print_err(
            "未配置视觉模型 API Key：请在设置中配置 GLM（推荐，免费）"
            f"或 {_DEEPSEEK_VISION_MODEL} 对应的 API Key"
        )
        return
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url)
        mime = _IMAGE_MIME.get(path.suffix.lower(), "image/png")
        b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
        content = _call_deepseek(client, _DEEPSEEK_VISION_MODEL, f"data:{mime};base64,{b64}")
        _print_ok(path, content)
    except Exception as exc:  # noqa: BLE001
        _print_err(f"DeepSeek 视觉模型调用失败: {exc}")


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    params = data.get("params") or {}
    raw = params.get("file_path") or ""
    path = Path(raw)
    if not path.is_absolute():
        path = workspace / path
    path = path.resolve()

    if not path.is_file():
        print(json.dumps({"success": False, "message": f"文件不存在: {path}"}))
        return
    if path.stat().st_size > 10 * 1024 * 1024:
        print(json.dumps({"success": False, "message": "图片超过 10MB"}))
        return

    settings = settings_store.load()
    glm = _resolve_glm(settings)
    if glm is not None:
        # GLM is the free preferred vision provider when configured.
        _run_glm(settings, glm[0], glm[1], glm[2], path)
        return

    # No GLM configured: fall back to DeepSeek's vision model.
    _run_deepseek(settings, path)


if __name__ == "__main__":
    main()
