"""Webhook 投递层骨架（design 027 §3.2 / stage 1）。

stage 2 才会加 飞书 / 企微 两条内置通道；这里只覆盖 dispatcher / registry /
parse_channels 的契约。
"""

from __future__ import annotations

import asyncio

import pytest

from app.agent.tasks.delivery import (
    Channel,
    DeliveryPayload,
    DeliveryResult,
    dispatch,
    parse_channels,
    register_channel,
)


@pytest.fixture(autouse=True)
def _clean_channel_registry():
    """每条测试前后清空投递通道注册表——通道是模块级单例，
    不清就会跨用例污染。
    """
    from app.agent.tasks import delivery as delivery_module

    saved = dict(delivery_module._REGISTRY)
    delivery_module._REGISTRY.clear()
    yield
    delivery_module._REGISTRY.clear()
    delivery_module._REGISTRY.update(saved)


class _EchoChannel:
    """把 config 整包塞到 meta 返回，假装投递成功的探针。"""

    name = "echo"

    def __init__(self) -> None:
        self.calls: list[tuple[DeliveryPayload, dict]] = []

    async def send(
        self, payload: DeliveryPayload, config: dict
    ) -> DeliveryResult:
        self.calls.append((payload, config))
        return DeliveryResult(
            channel=self.name, ok=True, status_code=200
        )


class _ExplodingChannel:
    name = "boom"

    async def send(
        self, payload: DeliveryPayload, config: dict
    ) -> DeliveryResult:
        raise RuntimeError("network down")


def test_parse_channels_empty_when_no_config():
    assert parse_channels(None) == []
    assert parse_channels({}) == []
    assert parse_channels({"channels": None}) == []
    assert parse_channels({"channels": "not a list"}) == []


def test_parse_channels_filters_non_dicts():
    cfg = {
        "channels": [
            {"type": "feishu", "webhook_url": "u"},
            "garbage",
            42,
        ]
    }
    out = parse_channels(cfg)
    assert out == [{"type": "feishu", "webhook_url": "u"}]


def test_parse_channels_keeps_empty_type_for_dispatch_to_reject():
    """``{"type":""}`` 是合法的 dict（缺 type 是用户配置错误），
    应留给 dispatch 阶段报错「unknown channel」，不要在此处静默吞掉。
    """
    cfg = {"channels": [{"type": ""}, {"type": "feishu"}]}
    out = parse_channels(cfg)
    assert out == [{"type": ""}, {"type": "feishu"}]


def test_dispatch_returns_unknown_channel_result():
    payload = DeliveryPayload(task_title="t", run_id="r", content="x")
    results = asyncio.run(dispatch(payload, [{"type": "ghost"}]))
    assert len(results) == 1
    assert results[0].ok is False
    assert "unknown channel" in (results[0].error or "")


def test_dispatch_uses_registered_channel():
    echo = _EchoChannel()
    register_channel(echo)
    payload = DeliveryPayload(task_title="标题", run_id="r1", content="正文")
    results = asyncio.run(
        dispatch(payload, [{"type": "echo", "extra": 1}])
    )
    assert results[0].ok is True
    assert results[0].channel == "echo"
    assert len(echo.calls) == 1
    assert echo.calls[0][0].task_title == "标题"


def test_dispatch_does_not_crash_on_handler_exception():
    register_channel(_ExplodingChannel())
    payload = DeliveryPayload(task_title="t", run_id="r", content="x")
    results = asyncio.run(dispatch(payload, [{"type": "boom"}]))
    assert results[0].ok is False
    assert "RuntimeError" in (results[0].error or "")


def test_dispatch_runs_channels_in_order_and_independently():
    echo = _EchoChannel()
    register_channel(echo)
    register_channel(_ExplodingChannel())
    payload = DeliveryPayload(task_title="t", run_id="r", content="x")
    results = asyncio.run(
        dispatch(
            payload,
            [
                {"type": "echo"},
                {"type": "boom"},
                {"type": "ghost"},
                {"type": "echo"},
            ],
        )
    )
    statuses = [r.ok for r in results]
    # echo → ok, boom → 抓, ghost → unknown, echo → ok
    assert statuses == [True, False, False, True]
    assert len(echo.calls) == 2


def test_channel_protocol_is_runtime_checkable():
    class Incomplete:
        pass

    assert isinstance(_EchoChannel(), Channel)
    assert not isinstance(Incomplete(), Channel)