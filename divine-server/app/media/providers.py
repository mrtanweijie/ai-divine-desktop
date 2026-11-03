"""视频生成 provider 适配层（035 §5）。

三个硬约定（写进代码，不靠记性）：

1. ``base_url`` 是**主机级**：MiniMax 视频走 ``/v2``，智谱是 ``/api/paas/v4``，
   路径由适配器拼，条目里存主机或完整根都行；
2. 状态字段名各家不同（``task.status`` / ``task_status``），枚举也各写各的
   （``succeeded`` / ``SUCCESS``）→ 这里统一归一为
   ``queued | running | succeeded | failed | expired``；
3. 图生视频能力差异：MiniMax 支持首尾帧（``role=first_frame/last_frame``），
   智谱 CogVideoX 只接首帧。
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

STATUS_MAP_MINIMAX = {
    "queued": "queued",
    "running": "running",
    "succeeded": "succeeded",
    "failed": "failed",
    "cancelled": "expired",
    "expired": "expired",
}

STATUS_MAP_ZHIPU = {
    "queued": "queued",
    "processing": "running",
    "running": "running",
    "success": "succeeded",
    "succeeded": "succeeded",
    "fail": "failed",
    "failed": "failed",
}


class ProviderError(RuntimeError):
    """上游报错（已翻译成人话的 message 由 service 层组装）。"""

    def __init__(self, message: str, *, kind: str = "provider") -> None:
        super().__init__(message)
        self.kind = kind


def _host(base_url: str) -> str:
    """条目里的 base_url 允许填主机（api.minimaxi.com）或带根路径，统一取主机。"""
    host = (base_url or "").strip().rstrip("/")
    for suffix in ("/v1", "/v2", "/v4", "/api/paas/v4", "/api/v1"):
        if host.endswith(suffix):
            host = host[: -len(suffix)]
            break
    if host and not host.startswith("http"):
        host = f"https://{host}"
    return host


def _image_data_url(path: str) -> str:
    """本地首/尾帧 → base64 data URL（MiniMax 接受 data URL；超限前先压缩，见 service）。"""
    data = open(path, "rb").read()  # noqa: SIM115 - 一次性读取，调用方已校验存在
    return f"data:image/png;base64,{base64.b64encode(data).decode()}"


def _minimax_content(
    prompt: str,
    first_frame: str | None,
    last_frame: str | None,
) -> list[dict[str, Any]]:
    """MiniMax v2 的多模态 content 数组：文本必有，帧按 role 附加。"""
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    if first_frame:
        content.append(
            {"type": "image_url", "image_url": {"url": _image_data_url(first_frame)}, "role": "first_frame"}
        )
    if last_frame:
        content.append(
            {"type": "image_url", "image_url": {"url": _image_data_url(last_frame)}, "role": "last_frame"}
        )
    return content


def submit_minimax(
    *,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    params: dict[str, Any],
) -> str:
    """提交 MiniMax v2 任务，返回 remote task_id。"""
    payload: dict[str, Any] = {
        "model": model or "MiniMax-H3",
        "content": _minimax_content(
            prompt,
            params.get("first_frame"),
            params.get("last_frame"),
        ),
    }
    if params.get("duration"):
        payload["duration"] = int(params["duration"])
    if params.get("resolution"):
        payload["resolution"] = str(params["resolution"])
    if params.get("aspect_ratio"):
        payload["ratio"] = str(params["aspect_ratio"])
    response = httpx.post(
        f"{_host(base_url)}/v2/video_generation",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=60,
    )
    if response.status_code in (401, 403):
        raise ProviderError("视频模型的 API Key 无效", kind="auth")
    if response.status_code == 429:
        raise ProviderError("视频生成额度不足或触发限流，请稍后再试", kind="quota")
    if response.status_code >= 400:
        detail = _extract_error(response)
        raise ProviderError(f"提交视频任务失败：{detail}")
    data = response.json()
    task_id = str(data.get("task_id") or "").strip()
    if not task_id:
        raise ProviderError("提交视频任务失败：上游未返回 task_id")
    return task_id


def query_minimax(
    *, base_url: str, api_key: str, remote_task_id: str
) -> dict[str, Any]:
    """轮询 MiniMax：``task.status`` / ``task.content.url``（成功取值）。"""
    response = httpx.get(
        f"{_host(base_url)}/v2/query/video_generation/{remote_task_id}",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=60,
    )
    if response.status_code >= 400:
        raise ProviderError(f"查询任务状态失败（HTTP {response.status_code}）")
    task = (response.json() or {}).get("task") or {}
    status = STATUS_MAP_MINIMAX.get(str(task.get("status") or "").lower(), "running")
    url = ((task.get("content") or {}).get("url")) or None
    return {"status": status, "url": url}


def submit_zhipu(
    *,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    params: dict[str, Any],
) -> str:
    """提交智谱任务。CogVideoX 只接首帧；带 last_frame 是调用方校验的事。"""
    payload: dict[str, Any] = {
        "model": model or "cogvideox-flash",
        "prompt": prompt,
    }
    if params.get("first_frame"):
        payload["image_url"] = _image_data_url(params["first_frame"])
    if params.get("duration"):
        payload["duration"] = int(params["duration"])
    if params.get("resolution"):
        payload["size"] = _zhipu_size(params["resolution"])
    response = httpx.post(
        f"{_host(base_url)}/api/paas/v4/videos/generations",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=60,
    )
    if response.status_code in (401, 403):
        raise ProviderError("视频模型的 API Key 无效", kind="auth")
    if response.status_code == 429:
        raise ProviderError("视频生成额度不足或触发限流，请稍后再试", kind="quota")
    if response.status_code >= 400:
        raise ProviderError(f"提交视频任务失败：{_extract_error(response)}")
    data = response.json()
    task_id = str(data.get("id") or "").strip()
    if not task_id:
        raise ProviderError("提交视频任务失败：上游未返回任务 id")
    return task_id


def query_zhipu(
    *, base_url: str, api_key: str, remote_task_id: str
) -> dict[str, Any]:
    """轮询智谱：``task_status`` / ``video_result[0].url``。"""
    response = httpx.get(
        f"{_host(base_url)}/api/paas/v4/async-result/{remote_task_id}",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=60,
    )
    if response.status_code >= 400:
        raise ProviderError(f"查询任务状态失败（HTTP {response.status_code}）")
    data = response.json() or {}
    status = STATUS_MAP_ZHIPU.get(str(data.get("task_status") or "").lower(), "running")
    url = None
    for item in data.get("video_result") or []:
        url = item.get("url") or url
        break
    return {"status": status, "url": url}


PROVIDERS = {
    "minimax": {"submit": submit_minimax, "query": query_minimax},
    "zhipu": {"submit": submit_zhipu, "query": query_zhipu},
}


def get_provider(name: str) -> dict[str, Any]:
    provider = PROVIDERS.get(name)
    if not provider:
        raise ProviderError(f"不支持的视频供应商：{name}")
    return provider


def _zhipu_size(resolution: str) -> str:
    """分辨率 → 智谱尺寸档（粗映射；官方按模型有差异，越界由上游报错兜底）。"""
    mapping = {"480P": "720x480", "720P": "1280x720", "1080P": "1920x1080"}
    return mapping.get(str(resolution).upper(), "1280x720")


def _extract_error(response: httpx.Response) -> str:
    try:
        data = response.json()
    except Exception:  # noqa: BLE001 - 非 JSON 响应取文本片段
        return (response.text or "")[:200] or f"HTTP {response.status_code}"
    for key in ("message", "error", "detail", "msg"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:200]
        if isinstance(value, dict):
            inner = value.get("message")
            if isinstance(inner, str) and inner.strip():
                return inner.strip()[:200]
    return f"HTTP {response.status_code}"
