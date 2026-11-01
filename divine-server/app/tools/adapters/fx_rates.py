"""fx_rates — 汇率查询 + 可切换币种的折线面板（A2UI 出站）。

三件事：
1. **联网取最新汇率**（open.er-api.com，160+ 币种）并写缓存；
2. **取日线序列**（api.frankfurter.dev / ECB）画折线——序列只覆盖 ECB 币种，
   其余币种进表格（只有最新值），面板会说明；
3. 把 ``rates`` 一并放进 ToolResult，比价（``compare.to_cny``）读同一份缓存，
   **先查汇率再比价**，不再用写死的常数。

折线用「区间首日 = 100」的相对变化：JPY（≈0.048）和 GBP（≈9.1）相差两个数量级，
直接画绝对值会有一条贴着 x 轴看不见；指数化后同图可比，绝对值和涨跌幅放表格。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from ..base import ToolAdapter, ToolExecutionError, ToolResult
from ..fx import rates as fx
from ..registry import register_tool
from ..ui.catalog import MAX_SURFACE_CHARS
from ..ui.validator import validate_ui_surface
from ..ui.versions.v0_9_1 import to_messages

DESCRIPTION = """查询实时汇率，并渲染可切换币种的折线面板（1 单位外币 = N 元人民币）。

何时调用：需要把外币金额换算成人民币（机票/酒店/购物比价）、或用户问汇率/汇率走势时。
面板里的折线是「区间首日 = 100」的相对变化，点图例可切换币种；绝对汇率与涨跌幅在表格里。

数据来源都是免 key 的公共接口：最新值 open.er-api.com，历史序列 api.frankfurter.dev（ECB）。
不在 ECB 表里的币种（MOP/TWD 等）只有最新值，不进折线。

调用后本工具会把汇率写入缓存，后续比价工具直接读它——所以**涉及外币时先调本工具**。

面板顶部是查询条件：「区间」（7/15/30/180/365 天）与「币种」多选，旁边是「重新查询」按钮
（动作 ``fx_refresh``）。用户点按钮会带着 ``days`` / ``symbols`` 回流，此时**按回传参数重新
调用本工具**，``surface_id`` 保持不变——面板会原地刷新，不要新开一块。"""


def _schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "symbols": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要展示的币种，如 [\"USD\",\"JPY\"]；面板回流时是逗号分隔字符串，两种都接受",
            },
            "days": {"type": "integer", "description": "区间天数：7/15/30/180/365，默认 30"},
            "refresh": {"type": "boolean", "description": "忽略 6 小时缓存，强制联网刷新"},
            "title": {"type": "string", "description": "面板标题"},
            "surface_id": {"type": "string", "description": "面板 id，默认 fx-board"},
        },
    }


_DEFAULT_SYMBOLS = ["USD", "EUR", "JPY", "HKD", "GBP", "THB"]
_MAX_SERIES = 8

#: 币种选择器里的候选项（在用户当前选的币种基础上补齐这些）。
_PICKABLE_SYMBOLS = ("USD", "EUR", "JPY", "HKD", "GBP", "THB", "SGD", "KRW", "AUD")


def _pickable_symbols(selected: str) -> list[str]:
    """选择器候选：当前已选 + 常用币种，去重后保留顺序。"""
    codes = [code.strip().upper() for code in str(selected or "").split(",") if code.strip()]
    merged = list(dict.fromkeys([*codes, *_PICKABLE_SYMBOLS]))
    return merged[: _MAX_SERIES + 4]


def _indexed(values: list[float | None]) -> list[float | None]:
    """区间首日归一为 100，便于不同量级币种同图比较。"""
    base = next((v for v in values if v), None)
    if not base:
        return [None for _ in values]
    return [round(v / base * 100, 2) if v else None for v in values]


def _chart_option(dates: list[str], series: dict[str, list[float | None]]) -> dict[str, Any]:
    """单币种不画图例：一条线没有可切换对象，图例只会白占一行高度。"""
    multi = len(series) > 1
    option: dict[str, Any] = {
        "tooltip": {"trigger": "axis"},
        "grid": {
            "left": 46,
            "right": 16,
            "top": 38 if multi else 16,
            "bottom": 26,
        },
        "xAxis": {"type": "category", "data": dates, "boundaryGap": False},
        "yAxis": {"type": "value", "scale": True, "name": "首日=100"},
        "series": [
            {
                "name": code,
                "type": "line",
                "smooth": True,
                "showSymbol": False,
                "data": _indexed(values),
            }
            for code, values in series.items()
        ],
    }
    if multi:
        option["legend"] = {"type": "scroll", "top": 0}
    return option


def _table_rows(
    snapshot_rates: dict[str, float], series: dict[str, list[float | None]]
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for code in sorted(series):
        values = [v for v in series[code] if v]
        latest = snapshot_rates.get(code)
        if latest is None and values:
            latest = values[-1]
        change = "—"
        if len(values) >= 2 and values[0]:
            change = f"{(values[-1] / values[0] - 1) * 100:+.2f}%"
        rows.append(
            {
                "code": code,
                "rate": f"{latest:.4f}" if isinstance(latest, (int, float)) else "—",
                "change": change,
                "scope": "折线 + 最新",
            }
        )
    return rows


def build_surface(
    *,
    surface_id: str,
    title: str,
    snapshot: dict[str, Any],
    dates: list[str],
    series: dict[str, list[float | None]],
    skipped: list[str],
    days: int,
) -> dict[str, Any]:
    rates = snapshot.get("rates") or {}
    rows = _table_rows(rates, series)
    source = snapshot.get("source") or "unknown"
    provider = snapshot.get("provider") or ""
    updated = snapshot.get("updated_at") or "未知"

    note = f"数据源：{provider}（最新）+ api.frankfurter.dev/ECB（历史）；更新于 {updated}。"
    if source in {"fallback", "cache-stale"}:
        note += " 当前使用的是本地兜底/过期缓存，联网刷新后可获得实时值。"
    if skipped:
        note += f" {'、'.join(skipped)} 不在 ECB 序列里，只有最新值、不进折线。"
    note += " 折线为「区间首日 = 100」的相对变化，点图例可切换币种。"

    # 面板顶部就是查询条件：区间 + 币种 + 重新查询。改完点按钮会带着参数回流，
    # 模型按回传值重调本工具、复用同一个 surfaceId，面板原地刷新。
    symbols_value = ",".join(series) if series else ",".join(rates.keys())
    # 换算卡的汇率表：口径与表格列一致（1 单位该币 = N 元），补上基准币 CNY = 1。
    # 只收当前序列里的币种（+CNY）：snapshot 有 160+ 币种，全塞进去选择器就没法用了。
    converter_rates: dict[str, float] = {"CNY": 1.0}
    for code in series:
        value = rates.get(code)
        if isinstance(value, (int, float)) and value > 0:
            converter_rates[code] = float(value)
    # 目标币回落到表里第一个非 CNY；表里只有基准币时就指向 CNY 自身
    # （前端也会按 codes 兜底，这里给的是初值，不能凭空写一个不存在的币种）。
    converter_target = next((code for code in converter_rates if code != "CNY"), "CNY")

    components: list[dict[str, Any]] = [
        {
            "id": "root",
            "component": "Column",
            "gap": "md",
            # 不要再放标题 Text：前端 UISurfaceBlock 已用 surface.title 渲染头部，
            # 这里再画一个就是「两个标题」（踩过）。
            "children": ["filters", "symbols", "chart", "converter", "tbl", "note"],
        },
        {
            "id": "filters",
            "component": "Row",
            "gap": "sm",
            # 5 个区间 chip + 按钮，窄窗口下必须允许换行，否则会溢出面板
            "wrap": True,
            "children": ["range", "refresh"],
        },
        {
            "id": "range",
            "component": "ChoicePicker",
            "value": {"path": "/query/days"},
            "options": [
                {"value": "7", "label": "7 天"},
                {"value": "15", "label": "15 天"},
                {"value": "30", "label": "30 天"},
                {"value": "180", "label": "180 天"},
                {"value": "365", "label": "近一年"},
            ],
        },
        {
            "id": "refresh",
            "component": "Button",
            "variant": "primary",
            "text": "重新查询",
            "action": {
                "name": "fx_refresh",
                "context": [
                    {"key": "days", "value": {"path": "/query/days"}},
                    {"key": "symbols", "value": {"path": "/query/symbols"}},
                ],
            },
        },
        {
            "id": "symbols",
            "component": "ChoicePicker",
            "multiple": True,
            "value": {"path": "/query/symbols"},
            "options": [{"value": code, "label": code} for code in _pickable_symbols(symbols_value)],
        },
        {
            "id": "chart",
            "component": "Chart",
            "height": 280,
            "option": _chart_option(dates, series),
            "caption": f"近 {days} 天汇率走势（1 外币 = N 元人民币，首日归一）",
        },
        {
            "id": "converter",
            "component": "Converter",
            "ratesPath": "/rates",
            "amount": 1000,
            "from": "CNY",
            "to": converter_target,
            "precision": 2,
        },
        {
            "id": "tbl",
            "component": "Table",
            "maxHeight": 260,
            "columns": [
                {"key": "code", "title": "币种"},
                {"key": "rate", "title": "1 外币 = ? 元"},
                {"key": "change", "title": "区间涨跌"},
                {"key": "scope", "title": "数据"},
            ],
            "rows": rows,
        },
        {"id": "note", "component": "Text", "text": note, "variant": "caption"},
    ]

    return {
        "surfaceId": surface_id,
        "title": title,
        "actions": ["fx_refresh"],
        "components": components,
        "data": {
            "query": {"days": str(days), "symbols": symbols_value},
            "rates": converter_rates,
        },
    }


@register_tool("fx_rates", DESCRIPTION, _schema())
class FxRatesAdapter(ToolAdapter):
    """查询汇率并渲染折线面板。"""

    category = "ui"
    timeout = 30

    async def run(
        self,
        workspace: Path,
        arguments: dict[str, Any],
        locale: str | None = None,
        progress_callback: Any | None = None,
    ) -> ToolResult:
        del workspace, locale, progress_callback

        arguments = arguments or {}
        # 面板回流的参数是**字符串**（ChoicePicker 的 value 就是逗号分隔字符串），
        # 模型也可能原样转述，所以两种形态都要吃。
        raw_symbols = arguments.get("symbols") or []
        if isinstance(raw_symbols, str):
            raw_symbols = raw_symbols.split(",")
        if not isinstance(raw_symbols, list):
            raise ToolExecutionError("symbols 必须是字符串数组或逗号分隔字符串")
        symbols = [str(s).strip().upper() for s in raw_symbols if str(s).strip()]
        symbols = symbols[:_MAX_SERIES] or list(_DEFAULT_SYMBOLS)

        days_raw = arguments.get("days")
        try:
            days = int(str(days_raw).strip()) if days_raw is not None else 30
        except (TypeError, ValueError):
            days = 30
        days = days if 2 <= days <= 366 else 30

        # 联网是阻塞调用，放线程里跑，别把事件循环钉住 8-15 秒
        snapshot = await asyncio.to_thread(
            fx.snapshot, force=bool(arguments.get("refresh"))
        )
        history = await asyncio.to_thread(fx.series, days=days, symbols=symbols)
        dates = history.get("dates") or []
        series = history.get("series") or {}

        surface_id = str(arguments.get("surface_id") or "fx-board")
        title = str(arguments.get("title") or "汇率走势（1 外币 = N 元人民币）")

        if series and dates:
            surface = build_surface(
                surface_id=surface_id,
                title=title,
                snapshot=snapshot,
                dates=dates,
                series=series,
                skipped=history.get("skipped") or [],
                days=days,
            )
            validation = validate_ui_surface(surface)
            if not validation.ok:
                first = validation.errors[0] if validation.errors else None
                raise ToolExecutionError(
                    f"汇率面板构建失败（{first.path}）：{first.message}"
                    if first
                    else "汇率面板构建失败"
                )
            normalized = validation.normalized or surface
            if len(json.dumps(normalized, ensure_ascii=False)) > MAX_SURFACE_CHARS:
                raise ToolExecutionError("汇率面板体积超限，请减少币种或缩短区间。")
            payload_messages = to_messages(normalized)
            rendered = True
        else:
            # 序列接口不可用（离线/限流）时不能静默失败：仍然把汇率与说明回给模型，
            # 只是不出图——文字结论比空白面板有用。
            normalized = {}
            payload_messages = []
            rendered = False

        rates = snapshot.get("rates") or {}
        picked = {code: rates.get(code) for code in symbols if rates.get(code)}
        note = (
            f"✓ 已查询汇率（来源 {snapshot.get('provider')} / {snapshot.get('source')}）。"
            + ("面板已呈现，正文只给结论与关键数字，不要复述表格。" if rendered else "历史序列不可用，未出图；可直接用返回的 latest 汇率做换算。")
        )

        data: dict[str, Any] = {
            "surfaceId": surface_id,
            "actionNames": [],
        }
        if rendered:
            data["uiSurface"] = normalized
            data["a2uiMessages"] = payload_messages

        return ToolResult(
            success=True,
            message=note,
            content=json.dumps(
                {
                    "success": True,
                    "source": snapshot.get("source"),
                    "provider": snapshot.get("provider"),
                    "updatedAt": snapshot.get("updated_at"),
                    "base": fx.BASE,
                    "latest": picked,
                    "seriesDays": len(dates),
                    "rendered": rendered,
                },
                ensure_ascii=False,
            ),
            data=data,
        )


__all__ = ["FxRatesAdapter", "build_surface"]
