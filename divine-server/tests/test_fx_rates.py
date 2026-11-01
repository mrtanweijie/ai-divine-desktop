"""汇率（fx）：方向、降级、指数化折线与面板校验。

重点不是「能不能联网」，而是**断网时不能把功能带崩**：
比价逐行换算走 ``rates_map()``，它必须永不联网、永有返回值。
"""

from __future__ import annotations

import pytest

from app.tools.fx import rates as fx
from app.tools.ui.validator import validate_ui_surface


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVINE_FX_CACHE", str(tmp_path / "fx.json"))
    fx.clear_cache()
    yield
    fx.clear_cache()


def test_upstream_direction_is_inverted() -> None:
    """上游是「1 CNY = N 外币」，我们存「1 外币 = N 元」。"""
    rates = fx._invert({"USD": 0.15, "JPY": 20.0})  # noqa: SLF001
    assert rates["USD"] == pytest.approx(6.666667)
    assert rates["JPY"] == pytest.approx(0.05)
    assert rates["CNY"] == 1.0


def test_offline_falls_back_to_builtin(monkeypatch) -> None:
    monkeypatch.setattr(fx, "_fetch_latest", lambda timeout=8.0: None)
    snapshot = fx.snapshot(network=True)
    assert snapshot["source"] == "fallback"
    assert snapshot["rates"]["USD"] == fx.FALLBACK_RATES["USD"]


def test_rates_map_never_touches_network(monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise AssertionError("比价路径不允许联网")

    monkeypatch.setattr(fx, "_fetch_latest", boom)
    assert fx.rates_map()["USD"] == fx.FALLBACK_RATES["USD"]


def test_live_snapshot_is_written_to_cache(monkeypatch, tmp_path) -> None:
    fake = {
        "base": "CNY",
        "rates": {"CNY": 1.0, "USD": 6.6},
        "source": "live",
        "provider": "test",
        "updated_at": "2026-11-01T00:00:00Z",
        "epoch": 1e12,
    }
    monkeypatch.setattr(fx, "_fetch_latest", lambda timeout=8.0: dict(fake))
    fx.clear_cache()
    assert fx.snapshot(network=True)["source"] == "live"

    fx.clear_cache()  # 清内存，验证落盘可读
    cached = fx.snapshot(network=False)
    assert cached["rates"]["USD"] == 6.6


def test_chart_series_are_indexed_to_hundred() -> None:
    from app.tools.adapters.fx_rates import build_surface

    surface = build_surface(
        surface_id="fx-board",
        title="汇率",
        snapshot={"rates": {"USD": 6.5, "JPY": 0.042}, "source": "live",
                  "provider": "test", "updated_at": "2026-11-01"},
        dates=["2026-10-01", "2026-10-02"],
        series={"USD": [6.5, 6.6], "JPY": [0.042, 0.041]},
        skipped=[],
        days=2,
    )
    chart = next(c for c in surface["components"] if c["component"] == "Chart")
    usd = next(s for s in chart["option"]["series"] if s["name"] == "USD")
    assert usd["data"][0] == 100.0
    assert usd["data"][1] == pytest.approx(101.54, abs=0.01)
    assert validate_ui_surface(surface).ok


def test_surface_has_no_duplicate_title() -> None:
    """标题只由前端 surface.title 渲染；面板里再放一个 Text 就是「两个标题」。"""
    from app.tools.adapters.fx_rates import build_surface

    surface = build_surface(
        surface_id="fx-board",
        title="欧元汇率",
        snapshot={"rates": {"EUR": 7.44}, "source": "live"},
        dates=["2026-10-30"],
        series={"EUR": [7.44]},
        skipped=[],
        days=1,
    )
    dups = [
        c
        for c in surface["components"]
        if c.get("component") == "Text" and c.get("text") == surface["title"]
    ]
    assert dups == []


def test_single_series_hides_legend() -> None:
    from app.tools.adapters.fx_rates import build_surface

    one = build_surface(
        surface_id="fx-1",
        title="t",
        snapshot={"rates": {"EUR": 7.44}, "source": "live"},
        dates=["2026-10-30"],
        series={"EUR": [7.44]},
        skipped=[],
        days=1,
    )
    two = build_surface(
        surface_id="fx-2",
        title="t",
        snapshot={"rates": {"EUR": 7.44, "USD": 6.67}, "source": "live"},
        dates=["2026-10-30"],
        series={"EUR": [7.44], "USD": [6.67]},
        skipped=[],
        days=1,
    )
    chart_one = next(c for c in one["components"] if c["component"] == "Chart")
    chart_two = next(c for c in two["components"] if c["component"] == "Chart")
    assert "legend" not in chart_one["option"]
    assert chart_two["option"]["legend"]["type"] == "scroll"


def test_surface_has_range_and_currency_controls() -> None:
    """面板顶部要有区间/币种选择器 + 重新查询按钮，动作需在 surface.actions 登记。"""
    from app.tools.adapters.fx_rates import build_surface

    surface = build_surface(
        surface_id="fx-board",
        title="汇率",
        snapshot={"rates": {"USD": 6.67, "EUR": 7.44}, "source": "live", "provider": "t"},
        dates=["2026-10-30"],
        series={"USD": [6.67], "EUR": [7.44]},
        skipped=[],
        days=30,
    )
    assert surface["actions"] == ["fx_refresh"]
    assert validate_ui_surface(surface).ok

    pickers = [c for c in surface["components"] if c["component"] == "ChoicePicker"]
    assert len(pickers) == 2, "一个选区间的、一个选币种的"
    multiple = next(c for c in pickers if c.get("multiple"))
    assert multiple["value"] == {"path": "/query/symbols"}
    assert {"value": "USD", "label": "USD"} in multiple["options"]

    range_picker = next(c for c in pickers if not c.get("multiple"))
    values = [option["value"] for option in range_picker["options"]]
    assert values == ["7", "15", "30", "180", "365"]

    button = next(c for c in surface["components"] if c["component"] == "Button")
    assert button["action"]["name"] == "fx_refresh"
    keys = [item["key"] for item in button["action"]["context"]]
    assert keys == ["days", "symbols"]

    assert surface["data"]["query"] == {"days": "30", "symbols": "USD,EUR"}


def test_adapter_accepts_string_params_from_panel(monkeypatch) -> None:
    """ChoicePicker 回传的是字符串（days="180"、symbols="USD,EUR"），不能再报类型错。"""
    import asyncio
    from pathlib import Path

    import app.tools.adapters  # noqa: F401
    from app.tools.adapters import fx_rates as mod
    from app.tools.registry import registry

    seen: dict = {}

    def fake_series(days=30, symbols=None, timeout=15.0):
        seen["days"] = days
        seen["symbols"] = symbols
        return {"dates": ["2026-10-30"], "series": {s: [6.6] for s in symbols}, "skipped": []}

    monkeypatch.setattr(mod.fx, "snapshot", lambda **kw: {
        "rates": {"USD": 6.6, "EUR": 7.4}, "source": "live", "provider": "t", "updated_at": "now",
    })
    monkeypatch.setattr(mod.fx, "series", fake_series)

    adapter = registry.get("fx_rates")
    result = asyncio.run(
        adapter.run(Path("."), {"days": "180", "symbols": "USD,EUR"})
    )
    assert result.success
    assert seen["days"] == 180
    assert seen["symbols"] == ["USD", "EUR"]


def test_surface_lists_only_what_has_series() -> None:
    from app.tools.adapters.fx_rates import build_surface

    surface = build_surface(
        surface_id="fx-board",
        title="汇率",
        snapshot={"rates": {"USD": 6.5}, "source": "live"},
        dates=["2026-10-01"],
        series={"USD": [6.5]},
        skipped=["MOP", "TWD"],
        days=1,
    )
    note = next(c for c in surface["components"] if c["id"] == "note")["text"]
    assert "MOP" in note and "TWD" in note
    assert "只有最新值" in note


def test_converter_card_reads_rates_from_data() -> None:
    """换算卡：表放 data、前端实时算，组件插在图表之后、表格之前。"""
    from app.tools.adapters.fx_rates import build_surface

    surface = build_surface(
        surface_id="fx-board",
        title="汇率",
        snapshot={"rates": {"USD": 6.67, "EUR": 7.44, "JPY": 0.0423}, "source": "live"},
        dates=["2026-10-30", "2026-10-31"],
        series={"USD": [6.66, 6.67], "EUR": [7.4, 7.44]},
        skipped=[],
        days=30,
    )
    converter = next(c for c in surface["components"] if c["component"] == "Converter")
    rates = surface["data"]["rates"]
    # 口径与表格列一致（1 单位该币 = N 元），基准币兜底 1.0
    assert rates["CNY"] == 1.0
    assert rates["USD"] == 6.67
    # 只有最新值、不在序列里的币种不进换算表（否则选择器里全是换算不了的空项）
    assert "JPY" not in rates
    assert converter["ratesPath"] == "/rates"
    assert converter["from"] == "CNY"
    assert converter["to"] == "USD"

    order = next(c for c in surface["components"] if c["id"] == "root")["children"]
    assert order.index("converter") == order.index("chart") + 1
    assert order.index("tbl") == order.index("converter") + 1
    assert validate_ui_surface(surface).ok


def test_converter_target_falls_back_when_no_foreign_currency() -> None:
    """只有基准币时不能凭空写 USD——目标币回落到表里第一个可用币种。"""
    from app.tools.adapters.fx_rates import build_surface

    surface = build_surface(
        surface_id="fx-board",
        title="汇率",
        snapshot={"rates": {"CNY": 1.0}, "source": "live"},
        dates=["2026-10-30"],
        series={"CNY": [1.0]},
        skipped=[],
        days=7,
    )
    converter = next(c for c in surface["components"] if c["component"] == "Converter")
    assert surface["data"]["rates"] == {"CNY": 1.0}
    assert converter["to"] == "CNY"
