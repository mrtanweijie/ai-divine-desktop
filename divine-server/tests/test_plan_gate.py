"""PLAN_CHOICE 门的判据：简单请求不该弹「要不要先出方案」。

事故背景：用户问「人民币兑换美元汇率」，界面先弹了一个方案选择。
两个原因叠加——

1. ``_should_ask_plan`` 在「取不到用户消息 / 取到空文本」时返回 **True**（fail-open），
   而 state 里的消息可能是 dict 形态，``isinstance(HumanMessage)`` 一条都匹配不上；
2. ``fx_rates`` / ``flight_board`` 这类只读工具没登记进 ``_READ_ONLY_TOOLS``，
   于是走了「非只读工具 → 先问方案」的分支。

两处都按「判不出来就不打扰」修掉，这里钉住行为。
"""

from __future__ import annotations

from app.agent.core import _READ_ONLY_TOOLS
from app.agent.core.prompts import _should_ask_plan


def test_no_messages_does_not_ask() -> None:
    assert _should_ask_plan([]) is False


def test_simple_request_does_not_ask() -> None:
    assert _should_ask_plan([{"role": "user", "content": "人民币兑换美元汇率"}]) is False


def test_dict_shaped_messages_are_understood() -> None:
    """state 里是 dict 时也要能读出文本，而不是当作「没有用户消息」。"""
    assert (
        _should_ask_plan(
            [
                {"type": "system", "content": "系统提示"},
                {"type": "human", "content": "帮我看看今天汇率"},
            ]
        )
        is False
    )


def test_explicit_plan_request_asks() -> None:
    assert _should_ask_plan([{"role": "user", "content": "先出方案再动手"}]) is True


def test_duck_typed_message_is_understood(monkeypatch) -> None:
    """打包后可能出现两份 langchain_core，isinstance 失配——按 .type 兜底。"""

    class ForeignHuman:
        type = "human"
        content = "人民币兑换美元汇率"

    assert _should_ask_plan([ForeignHuman()]) is False


def test_explicit_no_plan_skips() -> None:
    assert _should_ask_plan([{"role": "user", "content": "不要方案，直接做"}]) is False


def test_complex_request_asks() -> None:
    text = "重构整个项目结构，拆成多个模块，批量迁移所有文件并补测试"
    assert _should_ask_plan([{"role": "user", "content": text}]) is True


def test_read_only_panel_tools_are_whitelisted() -> None:
    """纯展示/只读工具必须进白名单，否则第一次调用就会触发方案门。"""
    for name in ("fx_rates", "flight_board", "render_graph", "render_ui"):
        assert name in _READ_ONLY_TOOLS, f"{name} 应视为只读，不该触发 plan_choice"
