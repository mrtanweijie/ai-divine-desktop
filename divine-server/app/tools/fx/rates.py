"""汇率：在线查询优先，落盘缓存次之，内置表最后兜底。

为什么不再写死：机票比价要换算 USD/HKD/JPY，汇率写死半年后所有外币价格都会偏。

两个免 key 数据源，分工明确：

* ``open.er-api.com`` —— 最新值，覆盖 160+ 币种（含 MOP/TWD/THB/KRW/SGD/MYR），
  正好补齐 ECB 表里没有的港澳台与东南亚币种；
* ``api.frankfurter.dev`` —— ECB 参考汇率，**提供时间序列**（画折线用），
  但只覆盖 ECB 币种表。

方向约定：``RATES[code]`` = **1 单位外币 = N 元人民币**（乘上去就是人民币），
与上游「1 CNY = N 外币」相反，取倒数后统一存。

失败策略：网络不通 → 用落盘快照；落盘也没有 → 用 ``FALLBACK_RATES`` 并在
``source`` 里标 ``fallback``。**汇率接口挂掉不能让比价功能整体失败**。
"""

from __future__ import annotations

import json
import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

#: 内置兜底汇率（1 外币 = N 元）。只在「在线查不到 + 没缓存」时使用，
#: 值来自 2026-10 的中间价附近，够用即可——它不再是主数据源。
FALLBACK_RATES: dict[str, float] = {
    "CNY": 1.0,
    "RMB": 1.0,
    "USD": 7.15,
    "HKD": 0.92,
    "MOP": 0.89,
    "TWD": 0.22,
    "JPY": 0.048,
    "KRW": 0.0052,
    "SGD": 5.32,
    "THB": 0.2,
    "MYR": 1.6,
    "EUR": 7.78,
    "GBP": 9.1,
    "AUD": 4.72,
}

BASE = "CNY"
#: 缓存有效期：6 小时内不重复联网（汇率日内波动对展示够用）。
CACHE_TTL_SECONDS = 6 * 3600

_ER_API = "https://open.er-api.com/v6/latest/CNY"
_FRANKFURTER = "https://api.frankfurter.dev/v1"

#: 内存快照：{base, rates, source, updated_at, provider}
_SNAPSHOT: dict[str, Any] | None = None


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _cache_file() -> Path:
    override = os.getenv("DIVINE_FX_CACHE")
    if override:
        return Path(override).expanduser()
    try:
        from ...config import data_root

        return data_root() / "fx" / "rates.json"
    except Exception:  # noqa: BLE001
        return Path(__file__).resolve().parents[2] / "data" / "fx" / "rates.json"


def _read_cache() -> dict[str, Any] | None:
    path = _cache_file()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("rates"), dict):
        return None
    return payload


def _write_cache(snapshot: dict[str, Any]) -> None:
    path = _cache_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass  # 缓存写不了不影响主流程


def _fresh(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    try:
        stamp = float(payload.get("epoch") or 0)
    except (TypeError, ValueError):
        return False
    return (time.time() - stamp) < CACHE_TTL_SECONDS


def _invert(raw: dict[str, Any]) -> dict[str, float]:
    """上游「1 CNY = N 外币」→ 本模块「1 外币 = N 元」。"""
    out: dict[str, float] = {BASE: 1.0}
    for code, value in (raw or {}).items():
        try:
            rate = float(value)
        except (TypeError, ValueError):
            continue
        if rate > 0:
            out[str(code).upper()] = round(1 / rate, 6)
    return out


def _fetch_latest(timeout: float = 8.0) -> dict[str, Any] | None:
    try:
        import httpx

        response = httpx.get(_ER_API, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
        payload = response.json()
    except Exception:  # noqa: BLE001 — 网络问题一律降级
        return None
    if str(payload.get("result")) != "success":
        return None
    rates = _invert(payload.get("rates") or {})
    if len(rates) < 5:
        return None
    return {
        "base": BASE,
        "rates": rates,
        "source": "live",
        "provider": "open.er-api.com",
        "updated_at": payload.get("time_last_update_utc") or _now_iso(),
        "epoch": time.time(),
    }


def snapshot(*, force: bool = False, network: bool = True, timeout: float = 8.0) -> dict[str, Any]:
    """返回当前汇率快照（CNY 为基准）。

    顺序：内存 → 落盘（未过期）→ 联网 → 落盘（过期也用）→ 内置兜底。
    ``network=False`` 时**绝不联网**——比价逐行换算会调这里，不能在计算路径上做 IO。
    """
    global _SNAPSHOT

    if _SNAPSHOT and not force and _fresh(_SNAPSHOT):
        return _SNAPSHOT

    cached = _read_cache()
    if not force and _fresh(cached):
        cached["source"] = cached.get("source") or "cache"
        _SNAPSHOT = cached
        return cached

    fetched = _fetch_latest(timeout=timeout) if network else None
    if fetched:
        _SNAPSHOT = fetched
        _write_cache(fetched)
        return fetched

    if cached:
        cached["source"] = "cache-stale"
        _SNAPSHOT = cached
        return cached

    fallback = {
        "base": BASE,
        "rates": dict(FALLBACK_RATES),
        "source": "fallback",
        "provider": "builtin",
        "updated_at": "",
        "epoch": 0.0,
    }
    _SNAPSHOT = fallback
    return fallback


def rates_map() -> dict[str, float]:
    """给比价模块用的纯字典：只读内存/落盘/兜底，**不联网**。"""
    return dict(snapshot(network=False).get("rates") or FALLBACK_RATES)


def live_rate(code: str) -> float | None:
    """某币种当前汇率（1 外币 = N 元）；未知币种返回 None。"""
    return rates_map().get(str(code or "").upper())


#: frankfurter 支持的币种（ECB 参考汇率表）；时间序列只对它们有效。
SERIES_SYMBOLS = (
    "USD", "EUR", "GBP", "JPY", "HKD", "AUD", "CAD", "CHF", "SGD",
    "KRW", "THB", "MYR", "INR", "NZD", "SEK", "NOK", "DKK", "PLN",
)


def series(days: int = 30, symbols: list[str] | None = None, timeout: float = 15.0) -> dict[str, Any]:
    """取最近 ``days`` 天的日线序列（1 外币 = N 元）。

    返回 ``{dates: [...], series: {code: [值...]}, skipped: [不支持序列的币种]}``。
    """
    wanted = [s.upper() for s in (symbols or list(SERIES_SYMBOLS)) if s]
    supported = [code for code in wanted if code in SERIES_SYMBOLS]
    skipped = [code for code in wanted if code not in SERIES_SYMBOLS]
    if not supported:
        return {"dates": [], "series": {}, "skipped": skipped, "source": "none"}

    end = date.today()
    start = end - timedelta(days=max(2, min(int(days), 180)))
    url = f"{_FRANKFURTER}/{start.isoformat()}..{end.isoformat()}"
    params = {"base": BASE, "symbols": ",".join(supported)}

    try:
        import httpx

        response = httpx.get(url, params=params, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
        payload = response.json()
    except Exception:  # noqa: BLE001
        return {"dates": [], "series": {}, "skipped": skipped, "source": "unavailable"}

    rows: dict[str, dict[str, float]] = payload.get("rates") or {}
    dates = sorted(rows)
    out: dict[str, list[float | None]] = {code: [] for code in supported}
    for day in dates:
        day_rates = rows.get(day) or {}
        for code in supported:
            raw = day_rates.get(code)
            out[code].append(round(1 / float(raw), 6) if raw else None)
    return {
        "dates": dates,
        "series": out,
        "skipped": skipped,
        "source": "frankfurter",
        "provider": "api.frankfurter.dev (ECB)",
    }


def clear_cache() -> None:
    """测试用：清内存快照。"""
    global _SNAPSHOT
    _SNAPSHOT = None
