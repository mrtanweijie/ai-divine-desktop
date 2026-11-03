"""生成模型（图像/视频）的共享配置读取（036）。

图像与视频的面板工具都要按「当前生效模型的能力」渲染选项——
不支持的项目**不渲染**，而不是渲染了再报错（036 §5）。

这里只放"读配置 + 能力矩阵"这类确定性逻辑，不放网络调用。
"""

from __future__ import annotations

import os
from typing import Any

from ..config import normalize_media_models, settings_store

#: 各 provider 的官方默认端点（media_models 条目未填 base_url 时的兜底）
MEDIA_DEFAULT_BASE_URL: dict[str, str] = {
    "minimax": "https://api.minimaxi.com/v1",
    "glm": "https://open.bigmodel.cn/api/paas/v4",
}

#: MiniMax image-01 支持的完整比例档
MINIMAX_RATIOS: tuple[str, ...] = (
    "1:1",
    "4:3",
    "3:4",
    "16:9",
    "9:16",
    "3:2",
    "2:3",
    "21:9",
)

#: GLM-Image 的合法比例（21:9 会被官方静默降到 16:9，所以面板直接不给）。
#: 尺寸映射表在 scripts/image_generate.GLM_ASPECT_TO_SIZE，这里保持同源口径。
GLM_RATIOS: tuple[str, ...] = (
    "1:1",
    "4:3",
    "3:4",
    "16:9",
    "9:16",
    "3:2",
    "2:3",
)

IMAGE_PROVIDERS: dict[str, dict[str, Any]] = {
    "minimax": {
        "label": "MiniMax image-01",
        "supports_reference": True,
        "n_max": 4,
        "ratios": MINIMAX_RATIOS,
        "prompt_optimizer": True,
    },
    "glm": {
        "label": "GLM-Image",
        "supports_reference": False,
        "n_max": 1,
        "ratios": GLM_RATIOS,
        "prompt_optimizer": False,
    },
}

# ---------------------------------------------------------------------------
# 视频能力矩阵（035 §5）：面板渲染与 video_generate 的静默裁剪共用同一份
# ---------------------------------------------------------------------------

#: MiniMax H3 系：4–15s；分辨率 768P / 2K（Max 系另说，先按 H3 口径）
MINIMAX_VIDEO_DURATIONS: tuple[int, ...] = tuple(range(4, 16))
MINIMAX_VIDEO_RESOLUTIONS: tuple[str, ...] = ("768P", "1080P", "2K")

#: 智谱 CogVideoX：5s / 10s；只接首帧
ZHIPU_VIDEO_DURATIONS: tuple[int, ...] = (5, 10)
ZHIPU_VIDEO_RESOLUTIONS: tuple[str, ...] = ("480P", "720P", "1080P")

VIDEO_PROVIDERS: dict[str, dict[str, Any]] = {
    "minimax": {
        "label": "MiniMax 海螺",
        "durations": MINIMAX_VIDEO_DURATIONS,
        "resolutions": MINIMAX_VIDEO_RESOLUTIONS,
        "ratios": MINIMAX_RATIOS,
        "supports_last_frame": True,
    },
    "zhipu": {
        "label": "智谱 CogVideoX",
        "durations": ZHIPU_VIDEO_DURATIONS,
        "resolutions": ZHIPU_VIDEO_RESOLUTIONS,
        "ratios": GLM_RATIOS,
        "supports_last_frame": False,
    },
}


def video_capabilities(provider: str) -> dict[str, Any]:
    """视频 provider 的合法参数集（035 §7.2：面板只渲染支持的项）。"""
    base = VIDEO_PROVIDERS.get(provider) or VIDEO_PROVIDERS["minimax"]
    return dict(base)


def active_video_provider(settings: dict[str, Any] | None = None) -> str:
    """生效视频模型的 provider（与 active_image_provider 同口径）。"""
    settings = settings if settings is not None else settings_store.load()
    entries = [
        entry
        for entry in normalize_media_models(settings.get("media_models"))
        if entry["kind"] == "video"
    ]
    if entries:
        active = next((entry for entry in entries if entry["active"]), entries[0])
        provider = str(active.get("provider") or "").lower()
        if provider in VIDEO_PROVIDERS:
            return provider
    return "minimax"


def active_image_provider(settings: dict[str, Any] | None = None) -> str:
    """判断当前生效的图像生成 provider。

    优先级：media_models(kind=image) 的 active/首个条目 > 旧配置探测
    （只有 GLM key 没有 MiniMax 凭据时才是 glm；其余默认 minimax——
    与 image_generate 脚本的"自动检测"口径一致：有参考图走 MiniMax，默认也是 MiniMax）。
    """
    settings = settings if settings is not None else settings_store.load()
    entries = [
        entry
        for entry in normalize_media_models(settings.get("media_models"))
        if entry["kind"] == "image"
    ]
    if entries:
        active = next((entry for entry in entries if entry["active"]), entries[0])
        provider = str(active.get("provider") or "").lower()
        if provider in IMAGE_PROVIDERS:
            return provider

    def _has_minimax() -> bool:
        if os.getenv("MINIMAX_API_KEY", "").strip():
            return True
        for entry in settings.get("models") or []:
            if not isinstance(entry, dict):
                continue
            vendor = str(entry.get("vendor") or "").lower()
            model = str(entry.get("model") or "").lower()
            base = str(entry.get("base_url") or "").lower()
            if (vendor == "minimax" or model.startswith("minimax") or "minimax" in base) and str(
                entry.get("api_key") or ""
            ).strip():
                return True
        return False

    has_glm = bool(
        str(settings.get("glm_api_key") or "").strip()
        or os.getenv("GLM_API_KEY", "").strip()
    )
    if has_glm and not _has_minimax():
        return "glm"
    return "minimax"


def image_capabilities(provider: str) -> dict[str, Any]:
    """某 provider 的面板渲染能力（选项按这里裁剪，不出现不支持项）。"""
    base = IMAGE_PROVIDERS.get(provider) or IMAGE_PROVIDERS["minimax"]
    return dict(base)


def image_defaults(settings: dict[str, Any], provider: str) -> dict[str, Any]:
    """面板默认值：media 条目 options > settings.image_defaults > 出厂默认。

    `image_defaults` 记录的是**上次成功生成**用的参数（036 §6），
    所以第二次生成基本只需点一下确认。
    """
    caps = image_capabilities(provider)
    saved = settings.get("image_defaults")
    saved = saved if isinstance(saved, dict) else {}
    media = [
        entry
        for entry in normalize_media_models(settings.get("media_models"))
        if entry["kind"] == "image"
    ]
    options = {}
    if media:
        active = next((entry for entry in media if entry["active"]), media[0])
        options = active.get("options") if isinstance(active.get("options"), dict) else {}

    n = options.get("n") or saved.get("n") or 1
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 1
    n = max(1, min(n, int(caps["n_max"])))

    ratio = str(options.get("aspect_ratio") or saved.get("aspect_ratio") or "")
    if ratio not in caps["ratios"]:
        ratio = ""  # 空 = 智能

    optimizer = options.get("prompt_optimizer")
    if optimizer is None:
        optimizer = saved.get("prompt_optimizer")
    return {
        "n": str(n),
        "aspect_ratio": ratio,
        "prompt_optimizer": True if optimizer is None else bool(optimizer),
    }
