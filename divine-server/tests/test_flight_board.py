"""机票（033）：节假日请假方案、比价与面板构建的单测。

覆盖点：
* 2026 官方放假安排（含调休上班日）→ 请假天数/连休天数算得对；
* 未收录年份降级为「只认周末」，且带 ``coverage=False``，不假装有官方数据；
* 比价：外币换算、同 (目的地,去程,返程) 去重取最低、只看直飞过滤、预算标记；
* 推荐：±N 天窗口生效、同一趟往返优先、多请一天假会被价格优势抵掉（评分）；
* 面板：确定性构建出的 IR 能过 L2 校验器（不依赖模型产 JSON）。
"""

from __future__ import annotations

import json

import pytest

from app.tools.flight import calendar_cn
from app.tools.flight.compare import rank, to_cny
from app.tools.flight.planner import recommend
from app.tools.ui.validator import validate_ui_surface


@pytest.fixture(autouse=True)
def _isolate_fx(tmp_path, monkeypatch):
    """把汇率缓存指向临时文件：测试必须可重复，不能读机器上的实时汇率。"""
    from app.tools.fx import rates as fx

    monkeypatch.setenv("DIVINE_FX_CACHE", str(tmp_path / "fx.json"))
    fx.clear_cache()
    yield
    fx.clear_cache()


# --------------------------------------------------------------------------
# 节假日 / 请假方案
# --------------------------------------------------------------------------


def test_national_day_is_all_rest() -> None:
    plan = calendar_cn.leave_plan("2026-10-01", "2026-10-07")
    assert plan["ok"]
    assert plan["total_days"] == 7
    assert plan["leave_days"] == 0
    assert plan["rest_days"] == 7
    assert "国庆节" in plan["holidays"]
    assert plan["coverage"] == "official"
    assert plan["estimated"] is False
    assert plan["verdict"] == "全在假期里，不用请假"


def test_bridge_before_national_day_costs_three_leave_days() -> None:
    """9/28–10/7 连休 10 天，中间 9/28、9/29、9/30 三个工作日要请假。"""
    plan = calendar_cn.leave_plan("2026-09-28", "2026-10-07")
    assert plan["leave_days"] == 3
    assert plan["rest_days"] == 7
    assert plan["leave_dates"] == ["2026-09-28", "2026-09-29", "2026-09-30"]


def test_makeup_saturday_counts_as_leave() -> None:
    """10/10 是调休上班的周六 —— 落在行程里就得算请假，不能当周末白送。"""
    plan = calendar_cn.leave_plan("2026-10-07", "2026-10-11")
    assert plan["makeup_days"] == 1
    assert "2026-10-10" in plan["leave_dates"]
    # 10/7 仍在国庆假期、10/11 是周日 → 休息 2 天；10/8、10/9、10/10（调休）都要请假
    assert plan["rest_days"] == 2
    assert plan["leave_days"] == 3


def test_spring_festival_nine_days() -> None:
    plan = calendar_cn.leave_plan("2026-02-15", "2026-02-23")
    assert plan["rest_days"] == 9
    assert plan["leave_days"] == 0
    assert "春节" in plan["holidays"]


def test_unpublished_year_is_inferred_and_flagged() -> None:
    """2027 官方还没发文：按规律推断，但必须标 estimated，不能冒充官方。"""
    assert calendar_cn.data_source(2027) == "estimated"
    plan = calendar_cn.leave_plan("2027-10-01", "2027-10-10")
    assert plan["coverage"] == "estimated"
    assert plan["estimated"] is True
    # 10/8 工作日 + 10/9 推断补班 → 请 2 天连休 10 天
    assert plan["leave_days"] == 2
    assert plan["total_days"] == 10


def test_2027_national_day_window_and_makeup() -> None:
    window = next(w for w in calendar_cn.holiday_windows(2027) if w["name"] == "国庆节")
    assert window["start"] == "2027-10-01"
    assert window["end"] == "2027-10-07"
    assert window["estimated"] is True
    makeup = calendar_cn._year_data(2027)[1]  # noqa: SLF001
    assert "2027-10-09" in makeup, "10/9 周六应被推断为补班，否则「请2休10」算不出来"


def test_midweek_festival_does_not_invent_three_day_block() -> None:
    """2027 端午是周三：硬凑 3 天要补 2 天班，不如只放当天。"""
    window = next(w for w in calendar_cn.holiday_windows(2027) if w["name"] == "端午节")
    assert window["start"] == window["end"] == "2027-06-09"


def test_three_day_block_contains_the_festival_day() -> None:
    """排 3 天小长假时不能把节日当天漏在窗口外（踩过的 bug）。"""
    anchors = {"清明节": "2027-04-05", "端午节": "2027-06-09", "中秋节": "2027-09-15"}
    windows = {w["name"]: w for w in calendar_cn.holiday_windows(2027)}
    for name, anchor in anchors.items():
        window = windows[name]
        assert window["start"] <= anchor <= window["end"], f"{name} 窗口没包住 {anchor}"


def test_suggest_plans_offers_leave_two_get_ten() -> None:
    plans = calendar_cn.suggest_plans("2027-10-01", "2027-10-07", max_leave=3)
    headlines = {plan["headline"]: plan for plan in plans}
    assert "请 2 天休 10 天" in headlines
    best = headlines["请 2 天休 10 天"]
    assert best["range"] == "10/1–10/10"
    assert best["leave_dates"] == ["2027-10-08", "2027-10-09"]


def test_plan_is_found_even_on_a_holiday() -> None:
    context = calendar_cn.find_holiday("2026-10-02")
    assert context is not None
    assert context["name"] == "国庆节"
    assert context["days_away"] == 0
    assert "就在假期内" in context["text"]


# --------------------------------------------------------------------------
# 单日判定与「官方优先」
# --------------------------------------------------------------------------


def test_resolve_date_official_year_has_no_estimate_suffix() -> None:
    verdict = calendar_cn.resolve_date("2026-10-03")
    assert verdict["kind"] == "holiday"
    assert verdict["day_index"] == 3
    assert verdict["source"] == "official"
    assert verdict["estimated"] is False
    assert "推断" not in verdict["text"]
    assert verdict["text"] == "10/3 周六：国庆节第 3 天"


def test_resolve_date_flags_makeup_and_workday() -> None:
    assert calendar_cn.resolve_date("2026-10-10")["kind"] == "makeup"
    assert calendar_cn.resolve_date("2026-11-03")["kind"] == "workday"
    assert calendar_cn.resolve_date("2026-11-07")["kind"] == "weekend"


def test_resolve_date_marks_inferred_year() -> None:
    verdict = calendar_cn.resolve_date("2027-10-09")
    assert verdict["source"] == "estimated"
    assert verdict["estimated"] is True
    assert "按往年规律推断" in verdict["text"]


def test_external_official_file_beats_inference(tmp_path, monkeypatch) -> None:
    """国务院一发 2027 通知，投放 JSON 即可，不再走任何推断。"""
    payload = {
        "2027": {
            "ranges": [
                {"name": "国庆节", "start": "2027-10-01", "end": "2027-10-08", "statutory": 3}
            ],
            "makeup": ["2027-10-09"],
        }
    }
    path = tmp_path / "holidays.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setenv("DIVINE_HOLIDAYS_FILE", str(path))
    monkeypatch.setattr(calendar_cn, "_EXTERNAL_CACHE", {"key": None, "data": {}})

    assert calendar_cn.data_source(2027) == "official"
    verdict = calendar_cn.resolve_date("2027-10-08")
    assert verdict["kind"] == "holiday"
    assert verdict["estimated"] is False
    assert "推断" not in verdict["text"]
    # 窗口跟着官方文件走（10/1–10/8），而不是推断的 10/1–10/7
    window = next(w for w in calendar_cn.holiday_windows(2027) if w["name"] == "国庆节")
    assert window["end"] == "2027-10-08"


def test_external_file_can_override_builtin_official(tmp_path, monkeypatch) -> None:
    payload = {
        "2026": {
            "ranges": [
                {"name": "测试假", "start": "2026-03-01", "end": "2026-03-02", "statutory": 1}
            ],
            "makeup": [],
        }
    }
    path = tmp_path / "holidays.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("DIVINE_HOLIDAYS_FILE", str(path))
    monkeypatch.setattr(calendar_cn, "_EXTERNAL_CACHE", {"key": None, "data": {}})

    assert calendar_cn.resolve_date("2026-03-01")["holiday"] == "测试假"
    # 文件里没有的假期就不再生效——外部文件是整年替换，不是合并
    assert calendar_cn.resolve_date("2026-10-01")["holiday"] is None



def test_reversed_dates_are_normalized() -> None:
    plan = calendar_cn.leave_plan("2026-10-07", "2026-10-01")
    assert plan["depart"] == "2026-10-01"
    assert plan["total_days"] == 7


def test_nearest_holiday_reports_days_away() -> None:
    context = calendar_cn.nearest_holiday("2026-09-20", horizon=30)
    assert context is not None
    assert context["name"] == "中秋节"
    assert context["days_away"] == 5


def test_date_window_expands_both_sides() -> None:
    days = [d.isoformat() for d in calendar_cn.date_window("2026-10-01", 3, 3)]
    assert days[0] == "2026-09-28"
    assert days[-1] == "2026-10-04"
    assert len(days) == 7


# --------------------------------------------------------------------------
# 比价
# --------------------------------------------------------------------------


def test_foreign_currency_is_converted() -> None:
    assert to_cny("96", "USD") == pytest.approx(686.4)
    assert to_cny("US$96") == pytest.approx(686.4)
    assert to_cny("¥1,280起") == pytest.approx(1280)


def test_same_round_trip_from_two_sources_keeps_cheapest() -> None:
    rows = [
        {"to": "三亚", "depart": "2026-10-01", "ret": "2026-10-07",
         "price": 1880, "airline": "MU", "direct": True, "source": "携程"},
        {"to": "三亚", "depart": "2026-10-01", "ret": "2026-10-07",
         "price": "US$240", "currency": "USD", "airline": "MU", "direct": True, "source": "Trip.com"},
    ]
    result = rank(rows)
    assert result["total"] == 1
    offer = result["offers"][0]
    assert offer["price_cny"] == pytest.approx(1716.0)
    assert offer["sources"] == ["携程", "Trip.com"]


def test_direct_only_and_budget_flags() -> None:
    rows = [
        {"to": "成都", "depart": "2026-10-01", "price": 900, "direct": True},
        {"to": "重庆", "depart": "2026-10-01", "price": 700, "direct": "经停"},
    ]
    result = rank(rows, budget=800, direct_only=True)
    assert result["total"] == 1
    assert result["offers"][0]["to"] == "成都"
    assert result["offers"][0]["within_budget"] is False


def test_bad_rows_are_dropped_with_reason() -> None:
    result = rank([{"to": "三亚"}, {"to": "成都", "depart": "2026-10-01", "price": "待定"}])
    assert result["offers"] == []
    assert len(result["dropped"]) == 2


# --------------------------------------------------------------------------
# 推荐（±N 天 + 往返 + 请假）
# --------------------------------------------------------------------------


def _rows() -> list[dict]:
    return [
        {"to": "三亚", "depart": "2026-10-01", "ret": "2026-10-07",
         "price": 1580, "airline": "MU", "direct": True, "source": "携程", "duration": "3h20m"},
        {"to": "成都", "depart": "2026-10-01", "ret": "2026-10-07",
         "price": 1200, "airline": "CA", "direct": True, "source": "携程", "duration": "3h05m"},
        # 早走三天便宜 500，但要多请 3 天假
        {"to": "乌鲁木齐", "depart": "2026-09-28", "ret": "2026-10-07",
         "price": 1080, "airline": "CZ", "direct": False, "source": "携程"},
    ]


def test_window_filters_out_dates_too_far_away() -> None:
    result = recommend(_rows(), depart="2026-10-01", ret="2026-10-07", window=1)
    assert [c["to"] for c in result["candidates"]] == ["成都", "三亚"]


def test_leave_days_penalty_can_outrank_cheaper_fare() -> None:
    result = recommend(_rows(), depart="2026-10-01", ret="2026-10-07", window=3)
    assert result["best"]["to"] == "成都"
    urumqi = next(c for c in result["candidates"] if c["to"] == "乌鲁木齐")
    assert urumqi["leave"]["leave_days"] == 3
    assert urumqi["score"] > result["best"]["score"]


def test_candidate_carries_leave_plan_and_holiday_context() -> None:
    result = recommend(_rows(), depart="2026-10-01", ret="2026-10-07", window=3)
    best = result["best"]
    assert best["leave"]["leave_days"] == 0
    assert result["holiday_context"]["name"] == "国庆节"
    assert "请假" in result["note"] or "不用请假" in result["note"]


def test_one_way_legs_are_paired_when_no_round_trip_offer() -> None:
    rows = [
        {"to": "大阪", "depart": "2026-10-02", "price": 900, "airline": "NH", "direct": True},
        {"to": "大阪", "depart": "2026-10-06", "price": 1100, "airline": "NH", "direct": True},
    ]
    result = recommend(rows, depart="2026-10-02", ret="2026-10-06", window=3)
    assert result["candidates"], "两段同航司单程应能拼成往返"
    paired = result["candidates"][0]
    assert paired["ret"] == "2026-10-06"
    assert paired["price_cny"] == pytest.approx(2000)
    assert paired.get("paired") is True


def test_no_rows_yields_actionable_note() -> None:
    result = recommend([], depart="2026-10-01", ret="2026-10-07")
    assert result["best"] is None
    assert "没有可用报价" in result["note"]


# --------------------------------------------------------------------------
# 面板（确定性 IR 过 L2 校验）
# --------------------------------------------------------------------------


def _surface(rows: list[dict], depart: str = "2026-10-01", ret: str = "2026-10-07") -> dict:
    from app.tools.adapters.flight_board import build_surface

    result = recommend(rows, depart=depart, ret=ret, window=3)
    context = result.get("holiday_context") or {}
    return build_surface(
        surface_id="flight-board",
        title="上海 机票 · ±3 天比价",
        conditions={
            "from_city": "上海",
            "to_scope": "国内热门",
            "depart_date": depart,
            "return_date": ret,
            "budget": 2000,
            "direct_only": False,
        },
        picks=result["candidates"],
        note=result["note"],
        holiday_text=f"假期参考：{context.get('text', '')}",
        leave_plans=result.get("leave_options") or [],
        estimated=bool(context.get("estimated")),
    )


def test_surface_passes_validator() -> None:
    surface = _surface(_rows())
    validation = validate_ui_surface(surface)
    assert validation.ok, [f"{e.path}: {e.message}" for e in validation.errors]
    assert surface["actions"] == ["flight_search"]


def test_surface_has_no_duplicate_title() -> None:
    """标题由前端 surface.title 渲染，面板里不该再有同名 Text。"""
    surface = _surface(_rows())
    assert [
        c
        for c in surface["components"]
        if c.get("component") == "Text" and c.get("text") == surface["title"]
    ] == []


def test_table_rows_are_objects_not_matrix() -> None:
    surface = _surface(_rows())
    table = next(c for c in surface["components"] if c["component"] == "Table")
    rows = surface["data"]["picks"]
    keys = {column["key"] for column in table["columns"]}
    assert rows and all(set(row) == keys for row in rows)


def test_surface_without_quotes_still_valid() -> None:
    surface = _surface([])
    validation = validate_ui_surface(surface)
    assert validation.ok, [f"{e.path}: {e.message}" for e in validation.errors]
    assert all(c["component"] != "Table" for c in surface["components"])


def _texts(surface: dict) -> list[str]:
    return [c.get("text", "") for c in surface["components"] if c["component"] == "Text"]


def test_surface_shows_leave_plans_for_official_year() -> None:
    surface = _surface(_rows())
    assert any("拼假方案" in text for text in _texts(surface))
    # 2026 是官方数据，不应出现「推断」免责句
    assert not any("按近年规律推断" in text for text in _texts(surface))


def test_surface_warns_when_year_is_inferred() -> None:
    rows = [
        {"to": "三亚", "depart": "2027-10-02", "ret": "2027-10-08",
         "price": 1680, "airline": "MU", "direct": True, "source": "携程"},
    ]
    surface = _surface(rows, depart="2027-10-01", ret="2027-10-08")
    texts = _texts(surface)
    assert any("按近年规律推断" in text for text in texts), texts
    assert any("请 2 天休 10 天" in text for text in texts), texts
    assert validate_ui_surface(surface).ok


# --------------------------------------------------------------------------
# 面板工具的接线：发事件 / 落库重建 都要认这些名字
# --------------------------------------------------------------------------


def test_a2ui_tool_names_covers_all_panel_tools() -> None:
    """execution / tools / persistence 三处共用这份名单，漏一个就「有面板没事件」。"""
    from app.agent.core import A2UI_TOOL_NAMES

    assert set(A2UI_TOOL_NAMES) == {"render_ui", "fx_rates", "flight_board"}


def test_persistence_rebuilds_flight_board_from_args() -> None:
    from app.agent.state.persistence import _collect_ui_surfaces

    calls = [
        {
            "name": "flight_board",
            "args": {
                "conditions": {
                    "from_city": "上海",
                    "depart_date": "2026-10-03",
                    "return_date": "2026-10-07",
                },
                "rows": [
                    {
                        "to": "三亚",
                        "depart": "2026-10-03",
                        "ret": "2026-10-07",
                        "price": 1580,
                        "airline": "MU",
                        "direct": True,
                        "source": "携程",
                    }
                ],
            },
        }
    ]
    surfaces = _collect_ui_surfaces(calls)
    assert len(surfaces) == 1
    assert surfaces[0]["surfaceId"] == "flight-board"
    assert validate_ui_surface(surfaces[0]).ok


def test_persistence_uses_cached_surface_for_fx_rates() -> None:
    """fx 面板无法离线重建，靠发事件时的 IR 快照落库——否则 done 之后面板消失。"""
    from app.agent.state import surface_cache
    from app.agent.state.persistence import _collect_ui_surfaces
    from app.tools.adapters.fx_rates import build_surface as build_fx_surface

    surface_cache.clear()
    surface = build_fx_surface(
        surface_id="fx-board",
        title="汇率",
        snapshot={"rates": {"USD": 6.67}, "source": "live", "provider": "test"},
        dates=["2026-10-30", "2026-10-31"],
        series={"USD": [6.66, 6.67]},
        skipped=[],
        days=2,
    )
    surface_cache.remember("call_fx_1", surface, "fx_rates")

    calls = [{"name": "fx_rates", "args": {"symbols": ["USD"]}, "id": "call_fx_1"}]
    got = _collect_ui_surfaces(calls)
    assert len(got) == 1
    assert got[0]["surfaceId"] == "fx-board"

    # call id 对不上时按工具名兜底——宁可复用最近一块，也不要「看到图、结束后没了」
    calls_other_id = [{"name": "fx_rates", "args": {"symbols": ["USD"]}, "id": "call_xxx"}]
    assert len(_collect_ui_surfaces(calls_other_id)) == 1

    # 没有快照（例如 sidecar 重启过）就不落库，也不该报错
    surface_cache.clear()
    assert _collect_ui_surfaces(calls) == []
