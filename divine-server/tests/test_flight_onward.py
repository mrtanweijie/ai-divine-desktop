"""主动找弃程（034 §10）：几何筛选 + 候选清单工具。

覆盖点：
* 只有「比目的地更远 + 同一大方向 + 延伸段够长」的城市才进清单；
* 反方向、更近的城市必须被排除；
* 三字码/别名能解析，未知城市不抛异常；
* 工具输出把「该查哪条航线」「命中条件」讲清楚，没有候选时说清不适用；
* 工具已注册且挂在 flights 意图上（否则模型拿不到 = 等于没做）。
"""

from __future__ import annotations

import pytest

from app.tools.adapters.flight_hidden_targets import _format_message, build_payload
from app.tools.flight import onward


def test_shanghai_chengdu_finds_western_onward_cities() -> None:
    """上海→成都：继续往西的城市才可能经成都中转（拉萨/稻城/林芝）。"""
    candidates = onward.onward_candidates("上海", "成都", limit=5)
    cities = [item["city"] for item in candidates]

    assert "拉萨" in cities
    assert "上海" not in cities and "成都" not in cities
    assert all(item["leg_km"] >= onward.MIN_ONWARD_KM for item in candidates)
    assert all(item["bearing_delta"] <= onward.MAX_BEARING_DELTA for item in candidates)


def test_opposite_direction_is_rejected() -> None:
    """东北方向的城市（哈尔滨/沈阳）不可能经成都中转。"""
    cities = [item["city"] for item in onward.onward_candidates("上海", "成都", limit=50)]
    assert "哈尔滨" not in cities
    assert "沈阳" not in cities


def test_nearer_city_is_rejected() -> None:
    """重庆比成都更靠东（离上海更近），票买到重庆不可能经成都中转。"""
    cities = [item["city"] for item in onward.onward_candidates("上海", "成都", limit=50)]
    assert "重庆" not in cities


def test_limit_and_ordering() -> None:
    """候选有限，且按「方位偏差小 → 延伸段近」排序。"""
    candidates = onward.onward_candidates("上海", "成都", limit=2)
    assert len(candidates) == 2
    deltas = [item["bearing_delta"] for item in candidates]
    assert deltas == sorted(deltas)


def test_unknown_or_same_city_returns_empty() -> None:
    assert onward.onward_candidates("不存在的城市", "成都") == []
    assert onward.onward_candidates("成都", "成都") == []


def test_iata_and_alias_resolve() -> None:
    assert onward.resolve_city("CTU") == "成都"
    assert onward.resolve_city("成都天府") == "成都"
    assert [item["city"] for item in onward.onward_candidates("上海", "CTU")] == [
        item["city"] for item in onward.onward_candidates("上海", "成都")
    ]


def test_payload_lists_routes_with_hit_condition() -> None:
    """清单要把「查哪条航线」和「命中条件」都写清楚，模型才知道怎么回填。"""
    payload = build_payload({"from_city": "上海", "target_city": "成都"})
    assert payload["target_city"] == "成都"
    assert payload["candidates"], "上海→成都 必须有候选"

    message = _format_message(payload)
    assert "查 上海→" in message
    assert "中转城市 = 成都" in message
    assert "不要硬填" in message or "硬填" in message


def test_payload_handles_no_candidates() -> None:
    """海口→三亚：南端没有更远的同向城市，要明说「不适合找弃程」。"""
    payload = build_payload({"from_city": "海口", "target_city": "三亚"})
    assert payload["candidates"] == []

    message = _format_message(payload)
    assert "找不到" in message
    assert "弃程" in message


def test_payload_reports_unknown_city() -> None:
    payload = build_payload({"from_city": "上海", "target_city": "瓦坎达"})
    assert payload["candidates"] == []
    assert payload["unknown_city"] == "瓦坎达"
    assert "坐标表" in _format_message(payload)


def test_payload_requires_both_cities() -> None:
    with pytest.raises(ValueError):
        build_payload({"from_city": "上海"})
    with pytest.raises(ValueError):
        build_payload({"target_city": "成都"})


def test_limit_is_clamped() -> None:
    """上限 5：每条候选都要一次抓价，给太多反而拖垮一轮对话。"""
    payload = build_payload({"from_city": "上海", "target_city": "成都", "limit": 99})
    assert len(payload["candidates"]) <= 5


def test_tool_is_registered_and_gated_to_flights() -> None:
    """注册 + 意图挂载缺一不可：没注册调不到，没挂载模型拿不到。"""
    from app.agent.tools.tools import _CONTENT_TOOLS
    from app.tools.registry import get_tool

    assert get_tool("flight_hidden_targets") is not None
    assert _CONTENT_TOOLS["flight_hidden_targets"] == "flights"
