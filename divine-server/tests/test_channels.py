"""飞书 / 企微 内置通道（design 027 §4）。

用 ``httpx.MockTransport`` 注入，不起真实网络。
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.agent.tasks.channels import FeishuChannel, WeComChannel
from app.agent.tasks.delivery import DeliveryPayload


def _payload(content: str = "正文") -> DeliveryPayload:
    return DeliveryPayload(
        task_title="每日热点", run_id="run-1", content=content
    )


def _recorder(status: int = 200, body: dict | None = None):
    """返回 (transport, captured) —— captured 收集请求信息。"""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = json.loads(request.content)
        return httpx.Response(status, json=body if body is not None else {"code": 0})

    return httpx.MockTransport(handler), captured


def test_feishu_sends_interactive_card():
    transport, captured = _recorder()
    channel = FeishuChannel(transport=transport)
    result = asyncio.run(
        channel.send(_payload("热点内容"), {"webhook_url": "https://f.example/h"})
    )
    assert result.ok is True
    assert result.status_code == 200
    assert captured["url"] == "https://f.example/h"
    body = captured["json"]
    assert body["msg_type"] == "interactive"
    assert body["card"]["header"]["title"]["content"] == "每日热点"
    assert body["card"]["elements"][0]["tag"] == "markdown"
    assert body["card"]["elements"][0]["content"] == "热点内容"
    assert "run-1" in json.dumps(body, ensure_ascii=False)


def test_feishu_adds_signature_when_secret_present():
    transport, captured = _recorder()
    channel = FeishuChannel(transport=transport)
    asyncio.run(
        channel.send(
            _payload(),
            {"webhook_url": "https://f.example/h", "sign_secret": "s3cret"},
        )
    )
    body = captured["json"]
    assert "timestamp" in body and "sign" in body
    # 签名可复算：HMAC-SHA256(key=secret, msg=f"{ts}\n{secret}")
    import base64
    import hashlib
    import hmac

    expected = base64.b64encode(
        hmac.new(
            b"s3cret",
            f"{body['timestamp']}\ns3cret".encode("utf-8"),
            hashlib.sha256,
        ).digest()
    ).decode()
    assert body["sign"] == expected


def test_feishu_missing_url_returns_error_without_request():
    channel = FeishuChannel(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    result = asyncio.run(channel.send(_payload(), {}))
    assert result.ok is False
    assert "missing webhook_url" in (result.error or "")


def test_wecom_sends_markdown_with_title():
    transport, captured = _recorder()
    channel = WeComChannel(transport=transport)
    result = asyncio.run(
        channel.send(
            _payload("摘要"), {"webhook_url": "https://w.example/h"}
        )
    )
    assert result.ok is True
    body = captured["json"]
    assert body["msgtype"] == "markdown"
    assert body["markdown"]["content"].startswith("## 每日热点")
    assert "摘要" in body["markdown"]["content"]


def test_wecom_appends_at_mobiles():
    transport, captured = _recorder()
    channel = WeComChannel(transport=transport)
    asyncio.run(
        channel.send(
            _payload(),
            {
                "webhook_url": "https://w.example/h",
                "at_mobiles": ["13800138000", " 13900139000 "],
            },
        )
    )
    content = captured["json"]["markdown"]["content"]
    assert "<@13800138000>" in content
    assert "<@13900139000>" in content


def test_channel_reports_http_error():
    transport, _ = _recorder(status=500, body={"errmsg": "boom"})
    channel = FeishuChannel(transport=transport)
    result = asyncio.run(
        channel.send(_payload(), {"webhook_url": "https://f.example/h"})
    )
    assert result.ok is False
    assert result.status_code == 500


def test_channel_catches_network_exception():
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    channel = FeishuChannel(transport=httpx.MockTransport(boom))
    result = asyncio.run(
        channel.send(_payload(), {"webhook_url": "https://f.example/h"})
    )
    assert result.ok is False
    assert "ConnectError" in (result.error or "")


def test_long_content_is_truncated():
    transport, captured = _recorder()
    channel = FeishuChannel(transport=transport)
    long_text = "x" * 9000
    asyncio.run(
        channel.send(_payload(long_text), {"webhook_url": "https://f.example/h"})
    )
    content = captured["json"]["card"]["elements"][0]["content"]
    assert len(content) < len(long_text)
    assert content.endswith("...(已截断)")


@pytest.mark.parametrize("channel_cls", [FeishuChannel, WeComChannel])
def test_builtin_channels_expose_name(channel_cls):
    assert channel_cls().name in ("feishu", "wecom")
