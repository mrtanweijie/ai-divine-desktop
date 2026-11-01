"""行程推荐：在用户选定日期的 ±N 天内挑出「更便宜 / 更少请假」的往返组合。

三件事在这里收口，全部是确定性逻辑：

1. **日期窗口**：用户给的日子只是锚点，真正比价的是 ±``window`` 天；
2. **同一趟往返**：优先用「一条往返票」，没有才用同航司的去+返两段拼；
3. **节假日与请假**：每个候选都算清「要请几天假、能连休几天」，
   并给出最近的一个假期窗口。
"""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable

from . import calendar_cn
from .compare import format_duration, format_price, rank

#: 一天年假折多少钱。用于把「便宜 200 但多请一天假」这类取舍量化成一个分数；
#: 不是精算，只是让排序有个一致的尺度。觉得不合适改这一个常量即可。
LEAVE_DAY_COST_CNY = 400

#: ±N 天的默认窗口（用户说「前后三天」）。
DEFAULT_WINDOW = 3


def _as_date(value: Any) -> date | None:
    return calendar_cn._as_date(value)  # noqa: SLF001 — 同包内复用解析


def _in_window(day_text: str, center: date | None, window: int) -> bool:
    if center is None:
        return True
    day = _as_date(day_text)
    if day is None:
        return False
    return abs((day - center).days) <= window


def _pair_one_way(
    offers: list[dict[str, Any]], window: int
) -> list[dict[str, Any]]:
    """把去程/返程两段单程拼成往返（同目的地 + 同航司 + 返程晚于去程）。"""
    paired: list[dict[str, Any]] = []
    by_dest: dict[str, list[dict[str, Any]]] = {}
    for offer in offers:
        by_dest.setdefault(offer["to"], []).append(offer)

    for destination, group in by_dest.items():
        for out in group:
            for back in group:
                if out is back or out["airline"] != back["airline"]:
                    continue
                out_day, back_day = _as_date(out["depart"]), _as_date(back["depart"])
                if not out_day or not back_day or back_day <= out_day:
                    continue
                if (back_day - out_day).days > 21:
                    continue
                paired.append(
                    {
                        "to": destination,
                        "depart": out["depart"],
                        "ret": back["depart"],
                        "price_cny": round(out["price_cny"] + back["price_cny"], 2),
                        "price_raw": "",
                        "currency": out["currency"],
                        "airline": out["airline"],
                        "flight_no": "",
                        "direct": out["direct"] and back["direct"],
                        "dep_time": out["dep_time"],
                        "arr_time": back["arr_time"],
                        "duration_min": (out["duration_min"] or 0) + (back["duration_min"] or 0)
                        if (out["duration_min"] or back["duration_min"])
                        else None,
                        "source": " + ".join(sorted({out["source"], back["source"]})),
                        "url": out["url"] or back["url"],
                        "per_hour": None,
                        "paired": True,
                    }
                )
    return paired


def recommend(
    rows: Iterable[dict[str, Any]],
    *,
    depart: Any = None,
    ret: Any = None,
    window: int = DEFAULT_WINDOW,
    budget: float | None = None,
    direct_only: bool = False,
    limit: int = 8,
) -> dict[str, Any]:
    """返回可直接渲染的推荐结果（候选 + 最佳 + 假期上下文）。"""
    ranked = rank(rows, budget=budget, direct_only=direct_only, limit=400)
    offers: list[dict[str, Any]] = list(ranked["offers"])

    depart_center = _as_date(depart)
    ret_center = _as_date(ret)

    round_trip = [offer for offer in offers if offer["ret"]]
    one_way = [offer for offer in offers if not offer["ret"]]
    candidates = round_trip + _pair_one_way(one_way, window)

    if depart_center:
        candidates = [
            c for c in candidates if _in_window(c["depart"], depart_center, window)
        ]
    if ret_center:
        candidates = [
            c for c in candidates if c["ret"] and _in_window(c["ret"], ret_center, window)
        ]

    for candidate in candidates:
        plan = calendar_cn.leave_plan(candidate["depart"], candidate.get("ret"))
        candidate["leave"] = plan
        # 分数：价格 + 多请一天假的代价。低分优先。
        candidate["score"] = round(
            candidate["price_cny"] + plan.get("leave_days", 0) * LEAVE_DAY_COST_CNY,
            1,
        )

    candidates.sort(key=lambda c: (c["score"], c["price_cny"]))
    for index, candidate in enumerate(candidates):
        candidate["pick"] = index + 1

    best = candidates[0] if candidates else None
    context = calendar_cn.find_holiday(depart_center) if depart_center else None
    plans = (
        calendar_cn.suggest_plans(context["start"], context["end"], max_leave=3)
        if context
        else []
    )

    return {
        "candidates": candidates[:limit],
        "total_candidates": len(candidates),
        "best": best,
        "holiday_context": context,
        "leave_options": plans,
        "window": window,
        "dropped": ranked["dropped"],
        "note": _build_note(best, context, window, len(candidates), plans),
    }


def _build_note(
    best: dict[str, Any] | None,
    context: dict[str, Any] | None,
    window: int,
    total: int,
    plans: list[dict[str, Any]] | None = None,
) -> str:
    if best is None:
        return f"±{window} 天内没有可用报价，建议放宽日期或目的地。"
    leave = best.get("leave") or {}
    trip = f"{best['depart']} → {best['ret']}" if best.get("ret") else best["depart"]
    text = (
        f"±{window} 天内共 {total} 个往返候选，首选 {best['to']} {trip}"
        f"（{format_price(best)}"
        + (
            f"，往返 {format_duration(best.get('duration_min'))}"
            if best.get("ret") and best.get("duration_min")
            else ""
        )
        + "）"
    )
    if leave:
        text += f"；{leave.get('text', '')}，{leave.get('verdict', '')}"
    if context:
        text += f"；最近的假期是{context['text']}"
    if plans:
        # 拼假方案比「请假天数」更有用：用户要的是「请几天能换多长假期」
        text += "；可拼假：" + "、".join(
            f"{plan['range']} {plan['headline']}" for plan in plans[:2]
        )
    return text
