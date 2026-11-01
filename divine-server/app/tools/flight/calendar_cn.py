"""中国法定节假日：**官方安排优先，未公布年份按近年规律推断**。

三层数据，按可信度从高到低：

1. ``_OFFICIAL`` —— 已由国务院办公厅发文公布的年份（2026），逐日精确，含调休上班日；
2. ``_LUNAR_ANCHORS`` —— 农历节日的公历锚点（春节/端午/中秋/清明）。这是天文事实、
   与政策无关，因此未来几年可以可靠地写出来；**政策（放几天、怎么调休）才是变量**；
3. ``_infer_year`` —— 未公布年份的推断：按 2025 年起的现行口径（春节 9 天含除夕、
   元旦/清明/端午/中秋各 3 天、劳动 5 天、国庆 7 天）排出放假块，再按
   「块内工作日数 − 法定天数」反推需要几个调休，把调休放在假期块前后最近的周末。

**所有推断结果都带 ``estimated=True``**，``leave_plan`` 会把它透传成
``coverage="estimated"``，上层据此在面板和正文里注明「按往年规律推断，以国务院通知为准」——
不给用户一个看起来像官方的假日期。

农历锚点只写到 2028：再往后没有可靠依据，``_infer_year`` 会放弃农历节日、只推断
固定日期的假期（元旦/劳动/国庆），并且仍标记为推断。
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

#: 已公布年份 → [(起, 止, 名称, 法定天数)]
_OFFICIAL: dict[int, list[tuple[str, str, str, int]]] = {
    2026: [
        ("2026-01-01", "2026-01-03", "元旦", 1),
        ("2026-02-15", "2026-02-23", "春节", 4),
        ("2026-04-04", "2026-04-06", "清明节", 1),
        ("2026-05-01", "2026-05-05", "劳动节", 2),
        ("2026-06-19", "2026-06-21", "端午节", 1),
        ("2026-09-25", "2026-09-27", "中秋节", 1),
        ("2026-10-01", "2026-10-07", "国庆节", 3),
    ],
}

#: 已公布年份 → 调休上班日。
_OFFICIAL_MAKEUP: dict[int, set[str]] = {
    2026: {
        "2026-01-04",
        "2026-02-14",
        "2026-02-28",
        "2026-05-09",
        "2026-09-20",
        "2026-10-10",
    },
}

#: 农历节日 → 公历锚点（天文事实，非政策）。只收录能确认的年份；
#: 缺这一年时只推断固定日期假期，农历假期交给官方数据。
_LUNAR_ANCHORS: dict[int, dict[str, str]] = {
    2027: {
        "spring": "2027-02-06",  # 正月初一
        "qingming": "2027-04-05",
        "dragon": "2027-06-09",  # 五月初五
        "mid": "2027-09-15",  # 八月十五
    },
    2028: {
        "spring": "2028-01-26",
        "qingming": "2028-04-04",
        "dragon": "2028-05-28",
        "mid": "2028-10-03",
    },
}

#: 现行放假口径（2025 年起）：(名称, 相对锚点的起点偏移, 天数, 法定天数)
#: 春节从「初一 - 2」开始共 9 天（含除夕），这条在 2026 官方数据上验证过。
_RULES: tuple[tuple[str, str, int, int, int], ...] = (
    # name, anchor_key, start_offset, days, statutory
    ("元旦", "new_year", 0, 3, 1),
    ("春节", "spring", -2, 9, 4),
    ("清明节", "qingming", -1, 3, 1),
    ("劳动节", "labour", 0, 5, 2),
    ("端午节", "dragon", 0, 3, 1),
    ("中秋节", "mid", 0, 3, 1),
    ("国庆节", "national", 0, 7, 3),
)

#: 2025 年起「减少调休」，单个假期最多补 2 天班。
_MAX_MAKEUP = 2

#: 外部官方数据文件（**优先级最高**）：`<data_root>/flight/holidays.json`。
#: 国务院一发布新一年通知，把文件放进去即可生效，**不用改代码、也不会再走推断**：
#:
#: ```json
#: { "2027": { "ranges": [{"name": "国庆节", "start": "2027-10-01",
#:                        "end": "2027-10-07", "statutory": 3}],
#:             "makeup": ["2027-09-26", "2027-10-09"] } }
#: ```
#: 测试可用 ``DIVINE_HOLIDAYS_FILE`` 指向临时文件。
_HOLIDAYS_FILE_ENV = "DIVINE_HOLIDAYS_FILE"
_EXTERNAL_CACHE: dict[str, Any] = {"key": None, "data": {}}

_DAY = timedelta(days=1)


def _as_date(value: Any) -> date | None:
    """容错解析：date / 'YYYY-MM-DD' / 'YYYY/M/D'。"""
    if isinstance(value, date):
        return value
    text = str(value or "").strip().replace("/", "-").replace(".", "-")
    if not text:
        return None
    parts = text.split("-")
    if len(parts) != 3:
        return None
    try:
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (TypeError, ValueError):
        return None


def _iso(day: date) -> str:
    return day.isoformat()


def holidays_file() -> Path:
    """外部官方数据路径：环境变量优先，其次数据目录下的 flight/holidays.json。"""
    override = os.getenv(_HOLIDAYS_FILE_ENV)
    if override:
        return Path(override).expanduser()
    try:
        from ...config import data_root

        return data_root() / "flight" / "holidays.json"
    except Exception:  # noqa: BLE001 — 拿不到配置就退回仓库内 data/
        return Path(__file__).resolve().parents[2] / "data" / "flight" / "holidays.json"


def _external_years() -> dict[int, tuple[list[tuple[str, str, str, int]], set[str]]]:
    """读取外部官方数据；按 (路径, mtime, 大小) 缓存，避免每次判日都读盘。"""
    path = holidays_file()
    try:
        stat = path.stat()
    except OSError:
        _EXTERNAL_CACHE.update(key=None, data={})
        return {}

    key = f"{path}:{stat.st_mtime_ns}:{stat.st_size}"
    if _EXTERNAL_CACHE["key"] == key:
        return _EXTERNAL_CACHE["data"]

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {}

    parsed: dict[int, tuple[list[tuple[str, str, str, int]], set[str]]] = {}
    for year_text, block in (payload if isinstance(payload, dict) else {}).items():
        try:
            year = int(year_text)
        except (TypeError, ValueError):
            continue
        if not isinstance(block, dict):
            continue

        ranges: list[tuple[str, str, str, int]] = []
        for item in block.get("ranges") or []:
            if not isinstance(item, dict):
                continue
            start, end = _as_date(item.get("start")), _as_date(item.get("end"))
            name = str(item.get("name") or "").strip()
            if start is None or end is None or not name or end < start:
                continue
            ranges.append((_iso(start), _iso(end), name, int(item.get("statutory") or 1)))

        makeup: set[str] = set()
        for raw in block.get("makeup") or []:
            day = _as_date(raw)
            if day is not None:
                makeup.add(_iso(day))

        if ranges:
            parsed[year] = (ranges, makeup)

    _EXTERNAL_CACHE.update(key=key, data=parsed)
    return parsed


def _fixed_anchor(year: int, key: str) -> date | None:
    """固定公历锚点；农历锚点查表，查不到返回 None。"""
    if key == "new_year":
        return date(year, 1, 1)
    if key == "labour":
        return date(year, 5, 1)
    if key == "national":
        return date(year, 10, 1)
    anchor = _LUNAR_ANCHORS.get(year, {}).get(key)
    return _as_date(anchor) if anchor else None


def _workdays(start: date, end: date) -> int:
    count = 0
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            count += 1
        cursor += _DAY
    return count


def _nearest_weekend_days(start: date, end: date, limit: int) -> list[date]:
    """假期块前后最近的周末日，按「离块越近越先」交替取（前、后、前、后…）。"""
    before: list[date] = []
    cursor = start - _DAY
    while len(before) < limit and (start - cursor).days <= 21:
        if cursor.weekday() >= 5:
            before.append(cursor)
        cursor -= _DAY
    after: list[date] = []
    cursor = end + _DAY
    while len(after) < limit and (cursor - end).days <= 21:
        if cursor.weekday() >= 5:
            after.append(cursor)
        cursor += _DAY

    picked: list[date] = []
    for index in range(limit):
        if index < len(before):
            picked.append(before[index])
        if len(picked) >= limit:
            break
        if index < len(after):
            picked.append(after[index])
    return picked[:limit]


def _weekend_inside(start: date, end: date) -> int:
    count = 0
    cursor = start
    while cursor <= end:
        if cursor.weekday() >= 5:
            count += 1
        cursor += _DAY
    return count


def _three_day_block(anchor: date, statutory: int) -> tuple[date, date, int]:
    """3 天小长假的排法：优先选「能吃到一个周末」的组合。

    周三的端午不应该硬凑 3 天再补 2 天班——那种情况下退回只放法定 1 天。
    返回 (start, end, 需要调休的天数)。
    """
    best: tuple[int, int, date, date] | None = None
    # 只在「包含节日当天」的排法里挑：shift 必须 ≤ 0，否则会排出 6/10–6/12
    # 这种漏掉端午本身的假（真踩过）。
    for shift in (-2, -1, 0):
        start = anchor + timedelta(days=shift)
        end = start + timedelta(days=2)
        needed = _workdays(start, end) - statutory
        weekend = _weekend_inside(start, end)
        score = (weekend, -needed)
        if best is None or score > (best[0], best[1]):
            best = (weekend, -needed, start, end)
    assert best is not None
    weekend, neg_needed, start, end = best
    needed = -neg_needed
    if needed > 1:
        # 怎么排都要补 2 天班 → 不连环放假，只放法定当天
        start = anchor
        end = anchor + timedelta(days=max(statutory - 1, 0))
        needed = 0
    return start, end, max(needed, 0)


def _infer_year(year: int) -> tuple[list[tuple[str, str, str, int]], set[str]]:
    """按现行口径推断某年放假安排；缺农历锚点则只推断固定日期假期。"""
    ranges: list[tuple[str, str, str, int]] = []
    makeup: set[str] = set()

    for name, anchor_key, offset, days, statutory in _RULES:
        anchor = _fixed_anchor(year, anchor_key)
        if anchor is None:
            continue
        if days == 3:
            start, end, needed = _three_day_block(anchor, statutory)
        else:
            start = anchor + timedelta(days=offset)
            end = start + timedelta(days=days - 1)
            needed = min(max(_workdays(start, end) - statutory, 0), _MAX_MAKEUP)
        ranges.append((_iso(start), _iso(end), name, statutory))
        if needed:
            for day in _nearest_weekend_days(start, end, needed):
                makeup.add(_iso(day))

    return ranges, makeup


def _year_data(year: int) -> tuple[list[tuple[str, str, str, int]], set[str], str]:
    """返回 (假期块, 调休日, 数据来源 official/estimated/none)。

    **解析顺序是硬约束**：外部官方文件 → 内置官方表 → 推断。
    官方一旦可用就绝不走推断——用户只给日期时，先按这里判「是不是假期」。
    """
    external = _external_years().get(year)
    if external:
        return external[0], external[1], "official"
    if year in _OFFICIAL:
        return _OFFICIAL[year], _OFFICIAL_MAKEUP.get(year, set()), "official"
    inferred_ranges, inferred_makeup = _infer_year(year)
    if inferred_ranges:
        return inferred_ranges, inferred_makeup, "estimated"
    return [], set(), "none"


def data_source(year: int) -> str:
    """official（已公布） / estimated（按规律推断） / none（无依据）。"""
    return _year_data(year)[2]


def has_coverage(year: int) -> bool:
    """该年份是否有可用数据（官方或推断）。"""
    return data_source(year) != "none"


def holiday_name(value: Any) -> str | None:
    day = _as_date(value)
    if day is None:
        return None
    for start_text, end_text, name, _ in _year_data(day.year)[0]:
        if _as_date(start_text) <= day <= _as_date(end_text):
            return name
    return None


def is_makeup_workday(value: Any) -> bool:
    day = _as_date(value)
    if day is None:
        return False
    return _iso(day) in _year_data(day.year)[1]


def is_rest_day(value: Any) -> bool:
    """法定休息日：周末或节假日，但调休上班日除外。"""
    day = _as_date(value)
    if day is None:
        return False
    if is_makeup_workday(day):
        return False
    return holiday_name(day) is not None or day.weekday() >= 5


def day_kind(value: Any) -> str:
    """holiday / weekend / makeup / workday。"""
    day = _as_date(value)
    if day is None:
        return "unknown"
    if is_makeup_workday(day):
        return "makeup"
    if holiday_name(day) is not None:
        return "holiday"
    return "weekend" if day.weekday() >= 5 else "workday"


def _month_day(day: date) -> str:
    return f"{day.month}/{day.day}"


_WEEKDAY_CN = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def resolve_date(value: Any) -> dict[str, Any]:
    """**单日判定入口**：用户一给日期，先回答「这是不是假期」。

    官方已公布就用官方（``source="official"``）；只有官方没有的年份才退回推断，
    并在文案里注明「按往年规律推断」——这样上层不需要关心数据从哪来。
    """
    day = _as_date(value)
    if day is None:
        return {"ok": False, "reason": "日期无法解析"}

    source = data_source(day.year)
    kind = day_kind(day)
    name = holiday_name(day)

    day_index = None
    if name:
        for start_text, _end, window_name, _stat in _year_data(day.year)[0]:
            if window_name == name:
                start = _as_date(start_text)
                if start:
                    day_index = (day - start).days + 1
                break

    if kind == "holiday":
        label = f"{name}第 {day_index} 天" if day_index else str(name)
    elif kind == "makeup":
        label = "调休上班"
    elif kind == "weekend":
        label = "周末"
    else:
        label = "工作日"

    suffix = "（按往年规律推断，以国务院通知为准）" if source == "estimated" else ""
    weekday = _WEEKDAY_CN[day.weekday()]
    return {
        "ok": True,
        "date": _iso(day),
        "weekday": weekday,
        "kind": kind,
        "holiday": name,
        "day_index": day_index,
        "source": source,
        "estimated": source == "estimated",
        "is_rest": kind in {"holiday", "weekend"},
        "text": f"{_month_day(day)} {weekday}：{label}{suffix}",
    }


def leave_plan(depart: Any, ret: Any) -> dict[str, Any]:
    """给定出行区间，算「要请几天假、能连休几天」。

    ``ret`` 缺失时按单程处理。请假天数 = 区间内的工作日（含调休上班日）。
    ``coverage`` 透出数据来源：official / estimated / weekend-only。
    """
    start = _as_date(depart)
    end = _as_date(ret) or start
    if start is None:
        return {"ok": False, "reason": "出发日期无法解析"}
    if end < start:
        start, end = end, start

    total = (end - start).days + 1
    leave_dates: list[str] = []
    holidays: list[str] = []
    rest_days = 0
    weekend_days = 0
    makeup_days = 0
    sources: set[str] = set()
    cursor = start
    while cursor <= end:
        sources.add(data_source(cursor.year))
        kind = day_kind(cursor)
        if kind == "holiday":
            rest_days += 1
            name = holiday_name(cursor)
            if name and name not in holidays:
                holidays.append(name)
        elif kind == "weekend":
            rest_days += 1
            weekend_days += 1
        elif kind == "makeup":
            makeup_days += 1
            leave_dates.append(_iso(cursor))
        else:
            leave_dates.append(_iso(cursor))
        cursor += _DAY

    leave_days = len(leave_dates)
    if "none" in sources or not sources:
        coverage = "weekend-only"
    elif "estimated" in sources:
        coverage = "estimated"
    else:
        coverage = "official"

    segments: list[str] = []
    if holidays:
        segments.append("法定 " + "、".join(holidays))
    if weekend_days:
        segments.append(f"周末 {weekend_days} 天")
    if leave_days:
        segments.append(f"请 {leave_days} 天")
    if makeup_days:
        segments.append(f"含调休上班 {makeup_days} 天")

    if leave_days == 0:
        verdict = "全在假期里，不用请假"
    elif leave_days <= 2:
        verdict = f"只要请 {leave_days} 天，性价比高"
    else:
        verdict = f"需请 {leave_days} 天"

    return {
        "ok": True,
        "depart": _iso(start),
        "return": _iso(end),
        "range": f"{_month_day(start)}–{_month_day(end)}",
        "total_days": total,
        "rest_days": rest_days,
        "leave_days": leave_days,
        "weekend_days": weekend_days,
        "makeup_days": makeup_days,
        "holidays": holidays,
        "leave_dates": leave_dates,
        "coverage": coverage,
        "estimated": coverage != "official",
        "text": f"{_month_day(start)}–{_month_day(end)} 共 {total} 天"
        + ("：" + " · ".join(segments) if segments else ""),
        "verdict": verdict,
    }


def holiday_windows(year: int) -> list[dict[str, Any]]:
    """某年全部假期块（官方或推断），供「按节假日找航班」使用。"""
    ranges, _, source = _year_data(year)
    out: list[dict[str, Any]] = []
    for start_text, end_text, name, statutory in ranges:
        start, end = _as_date(start_text), _as_date(end_text)
        out.append(
            {
                "name": name,
                "start": start_text,
                "end": end_text,
                "days": (end - start).days + 1,
                "statutory": statutory,
                "source": source,
                "estimated": source != "official",
            }
        )
    return out


def find_holiday(value: Any, horizon: int = 60) -> dict[str, Any] | None:
    """返回 ``horizon`` 天内最近（或正在其中）的假期块。"""
    day = _as_date(value)
    if day is None:
        return None
    best: dict[str, Any] | None = None
    for year in (day.year, day.year + 1):
        for window in holiday_windows(year):
            start, end = _as_date(window["start"]), _as_date(window["end"])
            offset = (start - day).days
            if start <= day <= end or 0 <= offset <= horizon:
                if best is None or offset < best["days_away"]:
                    best = dict(window, days_away=max(offset, 0))
    if best:
        best["text"] = (
            f"{best['name']} {_month_day(_as_date(best['start']))}–"
            f"{_month_day(_as_date(best['end']))} 共 {best['days']} 天"
            + ("（就在假期内）" if best["days_away"] == 0 else f"，还有 {best['days_away']} 天")
            + ("，按往年规律推断" if best["estimated"] else "")
        )
    return best


def suggest_plans(
    start: Any,
    end: Any,
    *,
    max_leave: int = 3,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """围绕一个假期块，枚举「往前后各借几天」的拼假方案。

    例：2027 国庆 10/1–10/7 推断 + 10/9 推断补班 →
    10/1–10/10 只需请 10/8、10/9 两天，得到「请 2 天休 10 天」。
    """
    base_start, base_end = _as_date(start), _as_date(end)
    if base_start is None or base_end is None:
        return []

    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    for before in range(0, 8):
        for after in range(0, 8):
            left = base_start - timedelta(days=before)
            right = base_end + timedelta(days=after)
            plan = leave_plan(left, right)
            if not plan.get("ok") or plan["leave_days"] > max_leave:
                continue
            key = (plan["depart"], plan["return"])
            candidates[key] = plan

    plans = sorted(
        candidates.values(),
        key=lambda p: (-p["total_days"], p["leave_days"]),
    )

    # 只保留「帕累托有效」的方案：更长且请假不更多的才值得看
    picked: list[dict[str, Any]] = []
    for plan in plans:
        if all(
            not (other["total_days"] >= plan["total_days"] and other["leave_days"] <= plan["leave_days"])
            for other in picked
        ):
            plan = dict(plan)
            plan["headline"] = (
                f"请 {plan['leave_days']} 天休 {plan['total_days']} 天"
                if plan["leave_days"]
                else f"不请假休 {plan['total_days']} 天"
            )
            picked.append(plan)
        if len(picked) >= limit:
            break
    return picked


def nearest_holiday(value: Any, horizon: int = 45) -> dict[str, Any] | None:
    """兼容旧接口：= find_holiday。"""
    return find_holiday(value, horizon)


def date_window(center: Any, before: int = 3, after: int = 3) -> list[date]:
    day = _as_date(center)
    if day is None:
        return []
    return [day + timedelta(days=offset) for offset in range(-before, after + 1)]


def expand_dates(values: Iterable[Any], before: int = 3, after: int = 3) -> list[str]:
    seen: set[str] = set()
    for value in values:
        for day in date_window(value, before, after):
            seen.add(day.isoformat())
    return sorted(seen)
