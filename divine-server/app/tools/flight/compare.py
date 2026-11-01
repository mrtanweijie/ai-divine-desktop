"""机票比价：把抓来的价格行归一、去重、排序，并算性价比与预算命中。

为什么单独成模块：汇率换算、同航线去重、预算判定都是**确定性业务逻辑**，
不该由模型在提示词里口算（001 那条「不要硬编码经验」的反面教训）。放在这里
才能被单测直接钉住，也保证「同一份原始数据 → 永远同一张表」。
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from ..fx.rates import FALLBACK_RATES, rates_map

BASE_CURRENCY = "CNY"

#: 兼容旧引用：真正的汇率走 ``fx.rates``（先查在线、再落盘、最后兜底）。
#: 这里只是「已知币种集合 + 离线兜底」，**不再是主数据源**。
FX_TO_CNY: dict[str, float] = FALLBACK_RATES

_SYMBOL_TO_CODE = {"$": "USD", "￥": "CNY", "¥": "CNY", "€": "EUR", "£": "GBP", "HK$": "HKD"}

_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)")


def _first_number(text: str) -> float | None:
    match = _NUMBER_RE.search(text.replace(",", ""))
    return float(match.group(1)) if match else None


def parse_price(value: Any) -> float | None:
    """解析价格：1200 / "1,280" / "¥550起" / "US$96" 都能出数。"""
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    return _first_number(str(value))


def parse_currency(value: Any, price_hint: Any = None) -> str:
    """显式币种优先；否则从价格字符串的前缀猜（默认人民币）。"""
    code = str(value or "").strip().upper()
    if code in FX_TO_CNY:
        return code
    text = str(price_hint or "").upper()
    for symbol, mapped in _SYMBOL_TO_CODE.items():
        if symbol.upper() in text:
            return mapped
    for known in FX_TO_CNY:
        if known in text:
            return known
    return BASE_CURRENCY


def to_cny(
    price: Any,
    currency: Any = None,
    price_hint: Any = None,
    rates: dict[str, float] | None = None,
) -> float | None:
    """换算成人民币。

    ``rates`` 不传时读 ``fx.rates`` 的缓存（**不联网**）——比价逐行换算不能做 IO；
    需要最新汇率请先调 ``fx_rates`` 工具刷新缓存。
    """
    amount = parse_price(price)
    if amount is None:
        return None
    table = rates if rates is not None else rates_map()
    code = parse_currency(currency, price_hint or price)
    rate = table.get(code) or FALLBACK_RATES.get(code) or 1.0
    return round(amount * rate, 2)


def parse_duration_minutes(value: Any) -> int | None:
    """解析时长："2h35m" / "2小时35分" / "155" / "155分钟"。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower()
    hours = re.search(r"(\d+)\s*(?:h|小时|时)", text)
    minutes = re.search(r"(\d+)\s*(?:m|min|分钟|分)", text)
    if hours or minutes:
        return int(hours.group(1)) * 60 + int(minutes.group(1) if minutes else 0)
    raw = _first_number(text)
    return int(raw) if raw is not None else None


def parse_bool(value: Any) -> bool:
    """直飞判定：容忍 "直飞"/"是"/"经停"/"1"/True 等写法。"""
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if not text:
        return False
    if text in {"1", "true", "yes", "y", "是", "直飞", "direct", "nonstop", "non-stop"}:
        return True
    return False


def _text(value: Any) -> str:
    return str(value or "").strip()


def normalize_offer(row: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """单行归一；返回 (offer, 丢弃原因)。"""
    if not isinstance(row, dict):
        return None, "行不是对象"

    destination = _text(row.get("to") or row.get("destination") or row.get("city"))
    depart = _text(row.get("depart") or row.get("depart_date") or row.get("date"))
    if not destination or not depart:
        return None, "缺少目的地或日期"

    price_cny = to_cny(row.get("price"), row.get("currency"), row.get("price"))
    if price_cny is None:
        return None, f"{destination} {depart} 没有可解析的价格"

    ret = _text(row.get("ret") or row.get("return_date") or row.get("back_date")) or None
    duration = parse_duration_minutes(row.get("duration_min") or row.get("duration"))
    direct = parse_bool(row.get("direct") or row.get("nonstop"))

    return (
        {
            "to": destination,
            "depart": depart,
            "ret": ret,
            "price_cny": price_cny,
            "price_raw": _text(row.get("price")),
            "currency": parse_currency(row.get("currency"), row.get("price")),
            "airline": _text(row.get("airline") or row.get("carrier")) or "—",
            "flight_no": _text(row.get("flight_no")),
            "direct": direct,
            "dep_time": _text(row.get("dep_time")),
            "arr_time": _text(row.get("arr_time")),
            "duration_min": duration,
            "source": _text(row.get("source")) or "—",
            "url": _text(row.get("url")),
            "per_hour": round(price_cny / (duration / 60), 1) if duration else None,
        },
        None,
    )


def dedupe(offers: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """同 (目的地, 去程, 返程) 只留最低价，并记下来源集合。

    「同一趟往返」的判定落在 (目的地, 去程, 返程) 上：同一天去同一天回，
    即使来自携程和 Trip.com 两个源，也应当是**一条**结果而不是两条。
    """
    best: dict[tuple[str, str, str], dict[str, Any]] = {}
    for offer in offers:
        key = (offer["to"], offer["depart"], str(offer["ret"] or ""))
        current = best.get(key)
        if current is None:
            offer = dict(offer, sources=[offer["source"]])
            best[key] = offer
            continue
        if offer["source"] not in current["sources"]:
            current["sources"].append(offer["source"])
        if offer["price_cny"] < current["price_cny"]:
            merged_sources = current["sources"]
            best[key] = dict(offer, sources=merged_sources)
    return list(best.values())


def rank(
    rows: Iterable[dict[str, Any]],
    *,
    budget: float | None = None,
    direct_only: bool = False,
    limit: int = 200,
) -> dict[str, Any]:
    """归一 → 去重 → 过滤 → 排序 → 打标，返回可直接渲染的结果集。"""
    offers: list[dict[str, Any]] = []
    dropped: list[str] = []
    for row in rows:
        offer, reason = normalize_offer(row)
        if offer is None:
            if reason:
                dropped.append(reason)
            continue
        if direct_only and not offer["direct"]:
            continue
        offers.append(offer)

    offers = dedupe(offers)
    offers.sort(key=lambda o: (o["price_cny"], o["duration_min"] or 10**6))

    for index, offer in enumerate(offers):
        offer["within_budget"] = budget is None or offer["price_cny"] <= budget
        offer["best"] = index == 0

    kept = offers[:limit]
    cheapest = kept[0] if kept else None
    return {
        "offers": kept,
        "total": len(offers),
        "truncated": len(offers) > len(kept),
        "dropped": dropped,
        "cheapest": cheapest,
        "within_budget_count": sum(1 for o in kept if o["within_budget"]),
        "direct_count": sum(1 for o in kept if o["direct"]),
    }


def format_price(offer: dict[str, Any]) -> str:
    """表格里的价格：外币同时给出换算后的人民币，避免用户误读币种。"""
    if offer["currency"] == BASE_CURRENCY:
        return f"¥{int(round(offer['price_cny']))}"
    return f"{offer['price_raw'] or offer['currency']} ≈ ¥{int(round(offer['price_cny']))}"


def format_duration(minutes: int | None) -> str:
    if not minutes:
        return "—"
    return f"{minutes // 60}h{minutes % 60:02d}m"
