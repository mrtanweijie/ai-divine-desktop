import base64
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.config import settings_store  # noqa: E402


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
    api_key = os.getenv("GLM_API_KEY") or settings.get("glm_api_key") or ""
    if not api_key:
        print(
            json.dumps(
                {
                    "success": False,
                    "message": "未配置 GLM_API_KEY，请在 .env 中设置",
                }
            )
        )
        return

    base_url = os.getenv("GLM_BASE_URL") or settings.get("glm_base_url") or ""
    model = os.getenv("GLM_MODEL") or settings.get("glm_model") or "glm-4.6v-flash"

    try:
        from zhipuai import ZhipuAI

        client_kwargs: dict[str, str] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = ZhipuAI(**client_kwargs)
        img_base = base64.b64encode(path.read_bytes()).decode("utf-8")
        content = _call_glm(client, model, img_base)
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
    except Exception as exc:  # noqa: BLE001
        detail = str(exc)
        if "429" in detail or "1305" in detail:
            message = (
                "GLM 免费模型当前繁忙，已自动重试仍失败，请稍后再试；"
                "如持续限流，可切换模型 glm-4.6v-flashx"
            )
        else:
            message = f"GLM 调用失败: {detail}"
        print(
            json.dumps(
                {"success": False, "message": message},
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
