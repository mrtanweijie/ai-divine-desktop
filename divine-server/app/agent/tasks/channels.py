"""内置 Webhook 投递通道（design 027 §4）。

两个通道都只要一个 webhook URL 就能用；飞书额外支持 ``sign_secret``
（自定义机器人签名校验，可选）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from typing import Any

import httpx

from .delivery import (
    DeliveryPayload,
    DeliveryResult,
    register_channel,
    truncate,
)

logger = logging.getLogger("divine.tasks.channels")

_DEFAULT_TIMEOUT = 15.0


class FeishuChannel:
    """飞书自定义机器人：interactive 卡片消息。"""

    name = "feishu"

    def __init__(
        self,
        timeout: float = _DEFAULT_TIMEOUT,
        transport: Any | None = None,
    ) -> None:
        self.timeout = timeout
        # 测试用：可注入 httpx.MockTransport；生产传 None 走默认实现。
        self.transport = transport

    async def send(
        self, payload: DeliveryPayload, config: dict[str, Any]
    ) -> DeliveryResult:
        url = (config.get("webhook_url") or "").strip()
        if not url:
            return DeliveryResult(
                channel=self.name, ok=False, error="missing webhook_url"
            )
        body: dict[str, Any] = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": payload.task_title,
                    }
                },
                "elements": [
                    {"tag": "markdown", "content": truncate(payload.content)},
                    {
                        "tag": "note",
                        "elements": [
                            {"tag": "plain_text", "content": f"run_id={payload.run_id}"}
                        ],
                    },
                ],
            },
        }
        secret = (config.get("sign_secret") or "").strip()
        if secret:
            timestamp = str(int(time.time()))
            body["timestamp"] = timestamp
            body["sign"] = _feishu_sign(timestamp, secret)

        try:
            async with httpx.AsyncClient(
                    timeout=self.timeout, transport=self.transport
                ) as client:
                resp = await client.post(url, json=body)
        except Exception as e:  # noqa: BLE001 — 网络异常转成结果，不抛给 handler
            logger.warning("feishu send failed: %r", e)
            return DeliveryResult(channel=self.name, ok=False, error=repr(e))
        ok = resp.status_code == 200
        return DeliveryResult(
            channel=self.name,
            ok=ok,
            status_code=resp.status_code,
            error=None if ok else resp.text[:500],
        )


def _feishu_sign(timestamp: str, secret: str) -> str:
    """飞书签名：HMAC-SHA256(key=secret, msg=f"{timestamp}\\n{secret}") → base64。"""
    digest = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}\n{secret}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


class WeComChannel:
    """企业微信群机器人：markdown 消息。"""

    name = "wecom"

    def __init__(
        self,
        timeout: float = _DEFAULT_TIMEOUT,
        transport: Any | None = None,
    ) -> None:
        self.timeout = timeout
        # 测试用：可注入 httpx.MockTransport；生产传 None 走默认实现。
        self.transport = transport

    async def send(
        self, payload: DeliveryPayload, config: dict[str, Any]
    ) -> DeliveryResult:
        url = (config.get("webhook_url") or "").strip()
        if not url:
            return DeliveryResult(
                channel=self.name, ok=False, error="missing webhook_url"
            )
        at_mobiles = [
            str(m).strip()
            for m in (config.get("at_mobiles") or [])
            if str(m).strip()
        ]
        content = f"## {payload.task_title}\n\n{truncate(payload.content)}"
        if at_mobiles:
            content += "\n" + " ".join(f"<@{m}>" for m in at_mobiles)
        body = {"msgtype": "markdown", "markdown": {"content": content}}
        try:
            async with httpx.AsyncClient(
                    timeout=self.timeout, transport=self.transport
                ) as client:
                resp = await client.post(url, json=body)
        except Exception as e:  # noqa: BLE001
            logger.warning("wecom send failed: %r", e)
            return DeliveryResult(channel=self.name, ok=False, error=repr(e))
        ok = resp.status_code == 200
        return DeliveryResult(
            channel=self.name,
            ok=ok,
            status_code=resp.status_code,
            error=None if ok else resp.text[:500],
        )


def register_builtin_channels() -> None:
    """副作用：把两条内置通道注册进 delivery registry。"""
    register_channel(FeishuChannel())
    register_channel(WeComChannel())
