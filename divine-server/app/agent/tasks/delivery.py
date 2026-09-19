"""Webhook 投递层骨架（design 027 §3.2 / §4）。

stage 1 只定 Protocol + dispatch 循环 + 注册 API。飞书 / 企微两条内置通道在
stage 2 加。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger("divine.tasks.delivery")


@dataclass
class DeliveryPayload:
    task_title: str
    run_id: str
    content: str
    attachments: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeliveryResult:
    channel: str
    ok: bool
    status_code: int | None = None
    error: str | None = None


@runtime_checkable
class Channel(Protocol):
    name: str

    async def send(
        self,
        payload: DeliveryPayload,
        config: dict[str, Any],
    ) -> DeliveryResult: ...


_REGISTRY: dict[str, Channel] = {}


def register_channel(channel: Channel) -> None:
    _REGISTRY[channel.name] = channel


def get_channel(name: str) -> Channel | None:
    return _REGISTRY.get(name)


def parse_channels(delivery_config: dict[str, Any] | None) -> list[dict[str, Any]]:
    """``delivery_json`` 解码后的 dict → ``channels`` 数组。

    形状见 design 027 §2.1：
    ``{"channels": [{"type": "feishu", "webhook_url": "...", ...}, ...]}``
    缺字段时返回空列表（等价于「不投递」）。
    """
    if not delivery_config:
        return []
    raw = delivery_config.get("channels") or []
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


async def dispatch(
    payload: DeliveryPayload,
    channels: list[dict[str, Any]],
) -> list[DeliveryResult]:
    """顺序调用每个 channel 配置；任一失败不影响其他。

    设计选择：``dispatch`` 自身永不抛异常——handler 把任务跑完、投递败给
    也只是 ``delivery_status`` 里记一条失败，不应让整个 run 标 failed。
    """
    results: list[DeliveryResult] = []
    for spec in channels:
        ctype = spec.get("type") or ""
        channel = get_channel(ctype) if ctype else None
        if channel is None:
            results.append(
                DeliveryResult(
                    channel=str(ctype),
                    ok=False,
                    error=f"unknown channel type: {ctype!r}",
                )
            )
            continue
        try:
            results.append(await channel.send(payload, spec))
        except Exception as e:  # noqa: BLE001 — dispatch 必须兜底
            logger.exception("channel send crashed type=%s", ctype)
            results.append(
                DeliveryResult(channel=str(ctype), ok=False, error=repr(e))
            )
    return results