"""MiniMax 图片生成工具：文生图 / 图生图。

调用 MiniMax image-01 模型（OpenAI 兼容端点）：
- 文生图：prompt + aspect_ratio
- 图生图：额外传 reference_image（网络 URL 或本地路径）
结果以 base64 返回，保存为 JPEG 文件到工作区输出目录。
"""

import base64
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.config import settings_store  # noqa: E402

DEFAULT_MODEL = "image-01"
# 仅当 settings 里没有 MiniMax 条目、也没有 MINIMAX_BASE_URL 环境变量时的兜底。
# 正常路径：base_url 完全来自用户配置的 MiniMax 条目（前端自动回填）。
DEFAULT_BASE_URL = "https://api.minimaxi.com/v1"
VALID_ASPECT_RATIOS = {"1:1", "16:9", "9:16", "21:9", "2:3", "3:2", "4:3", "3:4"}
MAX_PROMPT_LENGTH = 1500


def _minimax_config(settings: dict) -> tuple[str, str]:
    """MiniMax 提供方条目的 (api_key, base_url)。

    优先级：settings 里的 MiniMax 模型条目 > 环境变量
    MINIMAX_API_KEY / MINIMAX_BASE_URL > 官方默认端点。
    base_url 跟随条目配置（中国站 api.minimaxi.com / 国际站 api.minimax.io）。
    """
    import os

    env_key = os.getenv("MINIMAX_API_KEY", "").strip()
    env_base = os.getenv("MINIMAX_BASE_URL", "").strip()
    models = settings.get("models")
    if isinstance(models, list):
        for entry in models:
            if not isinstance(entry, dict):
                continue
            vendor = str(entry.get("vendor") or "").lower()
            model = str(entry.get("model") or "").lower()
            base_url = str(entry.get("base_url") or "").lower()
            if (
                vendor == "minimax"
                or model.startswith("minimax")
                or "minimax" in base_url
            ):
                key = str(entry.get("api_key") or "").strip()
                if key:
                    return (
                        key,
                        str(entry.get("base_url") or "").strip()
                        or env_base
                        or DEFAULT_BASE_URL,
                    )
    if env_key:
        return env_key, env_base or DEFAULT_BASE_URL
    return "", DEFAULT_BASE_URL


def _image_aspect_ratio(reference_image: str, workspace: Path) -> str | None:
    """读取参考图尺寸，返回最简整数比例；读取失败返回 None。"""
    import io

    try:
        from PIL import Image

        if reference_image.startswith(("http://", "https://")):
            import httpx

            resp = httpx.get(reference_image, timeout=30)
            resp.raise_for_status()
            with Image.open(io.BytesIO(resp.content)) as img:
                width, height = img.size
        else:
            path = Path(reference_image)
            if not path.is_absolute():
                path = workspace / path
            path = path.resolve()
            if not path.is_file():
                return None
            with Image.open(path) as img:
                width, height = img.size
    except Exception:  # noqa: BLE001 — 无法读取尺寸时返回 None
        return None
    if not width or not height:
        return None
    g = __import__("math").gcd(width, height)
    return f"{width // g}:{height // g}"


def _nearest_aspect_ratio(ratio: str) -> str | None:
    """返回与给定比例最接近的支持比例。"""
    if ratio in VALID_ASPECT_RATIOS:
        return ratio
    try:
        w_str, h_str = ratio.split(":")
        target = float(w_str) / float(h_str)
    except (ValueError, ZeroDivisionError):
        return None
    best: str | None = None
    best_diff = float("inf")
    for candidate in VALID_ASPECT_RATIOS:
        cw, ch = candidate.split(":")
        diff = abs(float(cw) / float(ch) - target)
        if diff < best_diff:
            best, best_diff = candidate, diff
    return best


def _detect_image_ext(data: bytes) -> str:
    """根据文件头判断图片格式并返回扩展名，未知格式回退 .jpeg。"""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:2] == b"\xff\xd8":
        return ".jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ".jpeg"


def _reference_image_file(reference_image: str, workspace: Path) -> dict:
    """构造 subject_reference 项。

    网络 URL 直接使用；本地路径转 base64 data URI。
    """
    reference_image = reference_image.strip()
    if reference_image.startswith(("http://", "https://")):
        return {"type": "character", "image_file": reference_image}
    path = Path(reference_image)
    if not path.is_absolute():
        path = workspace / path
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"参考图不存在: {path}")
    suffix = path.suffix.lower()
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(suffix, "image/jpeg")
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"type": "character", "image_file": f"data:{mime};base64,{b64}"}


def _need_aspect_ratio() -> None:
    """图片比例无法自动确定时，让 agent 用选项卡片请用户选择比例。"""
    ratio_list = "、".join(sorted(VALID_ASPECT_RATIOS))
    print(
        json.dumps(
            {
                "success": False,
                "message": (
                    f"图片生成需要指定比例（可选：{ratio_list}）。"
                    "请用选项卡片（```options 代码块）让用户选择图片比例后，"
                    "再用所选比例重新调用 image_generate。"
                ),
            },
            ensure_ascii=False,
        )
    )


def _api_error_message(result: dict) -> str:
    """把 MiniMax 的 base_resp 错误翻译成友好中文提示。"""
    base = result.get("base_resp") or {}
    status_msg = str(base.get("status_msg") or "")
    code = base.get("status_code")
    lowered = status_msg.lower()
    if "insufficient balance" in lowered:
        return "MiniMax 账户余额不足，请充值后重试"
    if "invalid api key" in lowered or "login fail" in lowered:
        return "MiniMax API Key 无效或已失效，请在设置中检查 MiniMax 提供方的 API Key"
    if "invalid params" in lowered:
        return f"MiniMax 参数错误（{code}）：{status_msg}"
    if status_msg:
        return f"MiniMax 返回错误（{code}）：{status_msg}"
    return f"MiniMax 返回错误：{result}"


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"]).resolve()
    output_root = Path(data.get("output_dir") or workspace).resolve()
    params = data.get("params") or {}

    prompt = str(params.get("prompt") or "").strip()
    if not prompt:
        print(json.dumps({"success": False, "message": "缺少 prompt（图片描述）"}))
        return
    # MiniMax image-01 限制 prompt 最长 1500 字符：超长一律自动截断，
    # 避免"让 LLM 精简"在多轮里反复超限导致死循环。
    truncated = False
    if len(prompt) > MAX_PROMPT_LENGTH:
        prompt = prompt[:MAX_PROMPT_LENGTH]
        truncated = True

    settings = settings_store.load()
    api_key, api_base_url = _minimax_config(settings)
    if not api_key:
        print(
            json.dumps(
                {
                    "success": False,
                    "message": (
                        "未配置 MiniMax API Key：请在设置中添加 MiniMax 提供方并填写 API Key"
                    ),
                },
                ensure_ascii=False,
            )
        )
        return

    reference_image = str(params.get("reference_image") or "").strip()
    raw_ratio = str(params.get("aspect_ratio") or "").strip()
    ratio_adapted = False

    if not raw_ratio:
        if reference_image:
            # 图生图：默认按参考图原始比例；不在支持列表时用最接近的比例
            original = _image_aspect_ratio(reference_image, workspace)
            if original and original in VALID_ASPECT_RATIOS:
                raw_ratio = original
            elif original:
                nearest = _nearest_aspect_ratio(original)
                if nearest:
                    raw_ratio = nearest
                    ratio_adapted = True
                else:
                    _need_aspect_ratio()
                    return
            else:
                _need_aspect_ratio()
                return
        else:
            # 文生图：未指定比例 → 让用户选择
            _need_aspect_ratio()
            return

    aspect_ratio = raw_ratio
    if aspect_ratio not in VALID_ASPECT_RATIOS:
        print(
            json.dumps(
                {
                    "success": False,
                    "message": (
                        f"不支持的 aspect_ratio: {aspect_ratio}（支持 "
                        + "/".join(sorted(VALID_ASPECT_RATIOS))
                        + "）"
                    ),
                },
                ensure_ascii=False,
            )
        )
        return

    try:
        count = int(params.get("n") or 1)
    except (TypeError, ValueError):
        print(json.dumps({"success": False, "message": "n 必须是整数"}))
        return
    if count < 1 or count > 4:
        print(json.dumps({"success": False, "message": "n 范围 1-4"}))
        return

    prompt_optimizer = params.get("prompt_optimizer")
    if prompt_optimizer is None:
        prompt_optimizer = True

    payload: dict = {
        "model": str(params.get("model") or DEFAULT_MODEL),
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "response_format": "base64",
        "n": count,
        "prompt_optimizer": bool(prompt_optimizer),
    }
    if reference_image:
        try:
            payload["subject_reference"] = [
                _reference_image_file(reference_image, workspace)
            ]
        except Exception as exc:  # noqa: BLE001
            print(
                json.dumps(
                    {"success": False, "message": f"参考图处理失败: {exc}"},
                    ensure_ascii=False,
                )
            )
            return

    try:
        import httpx

        api_url = f"{api_base_url.rstrip('/')}/image_generation"
        headers = {"Authorization": f"Bearer {api_key}"}
        # 网络抖动/限流（429/5xx）重试一次
        last_response = None
        for attempt in range(2):
            last_response = httpx.post(
                api_url, headers=headers, json=payload, timeout=120
            )
            if last_response.status_code < 500 or attempt == 1:
                break
            time.sleep(2 * (attempt + 1))
        response = last_response
        response.raise_for_status()
        result = response.json()
        data = result.get("data") or {}
        images_b64 = data.get("image_base64") or []
        images_urls = data.get("image_urls") or []
        if not images_b64 and not images_urls:
            print(
                json.dumps(
                    {"success": False, "message": _api_error_message(result)},
                    ensure_ascii=False,
                )
            )
            return
        raw_name = str(params.get("filename") or "").strip()
        image_dir = output_root / "images"
        image_dir.mkdir(parents=True, exist_ok=True)
        written = []
        total = max(len(images_b64), len(images_urls))
        for index in range(total):
            if index < len(images_b64):
                data = base64.b64decode(images_b64[index])
            else:
                download = httpx.get(images_urls[index], timeout=120)
                download.raise_for_status()
                data = download.content
            if raw_name:
                # 始终附加实际格式的扩展名，避免无后缀文件被
                # 预览/read_image 当成未知类型
                base_name = Path(raw_name).stem
                ext = _detect_image_ext(data)
                name = (
                    f"{base_name}{ext}"
                    if total == 1
                    else f"{base_name}-{index + 1}{ext}"
                )
            else:
                name = f"image-{int(time.time() * 1000)}-{index + 1}.jpeg"
            output = image_dir / name
            output.write_bytes(data)
            written.append(output)
    except httpx.HTTPStatusError as exc:
        try:
            result = exc.response.json()
        except Exception:  # noqa: BLE001
            result = {}
        print(
            json.dumps(
                {"success": False, "message": _api_error_message(result)},
                ensure_ascii=False,
            )
        )
        return
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {"success": False, "message": f"图片生成失败: {exc}"},
                ensure_ascii=False,
            )
        )
        return

    notes = []
    if truncated:
        notes.append(f"prompt 超过 {MAX_PROMPT_LENGTH} 字符，已自动截断")
    if ratio_adapted:
        notes.append(f"参考图比例不在支持列表，已用最接近的 {aspect_ratio}")
    message = f"已生成 {len(written)} 张图片"
    if notes:
        message += "（" + "；".join(notes) + "）"
    first = written[0]
    print(
        json.dumps(
            {
                "success": True,
                "message": message,
                "file_name": first.name,
                "filepath": str(first),
                "files": [str(p) for p in written],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
