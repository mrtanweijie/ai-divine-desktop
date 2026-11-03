"""主动找弃程：从「用户目的地」推出值得再查一遍的下游城市。

弃程票要成立，票面终点必须**比目的地更远、且在同一个大方向上**——否则航班不会经由
目的地中转。这里用一张坐标表做纯几何筛选，把「该去查哪几条航线」变成确定性结果；
模型只负责按这份清单去 OTA 抓价。

**这不是航线网络数据**：真实是否经停由航司决定，这里只回答「哪几条航线值得一试」。
命中率靠后面的一次实查验证——抓到航段（`via` / `skip_at`）才算数，抓不到就当普通机票。
"""

from __future__ import annotations

import math
from typing import Any

#: 城市坐标（纬度, 经度）。只收录常被拿来「再飞一段」的城市：
#: 主干城市 + 西部/边疆/海岛这类典型「延伸段」目的地。
CITY_COORDS: dict[str, tuple[float, float]] = {
    "北京": (39.904, 116.407),
    "上海": (31.230, 121.474),
    "广州": (23.129, 113.264),
    "深圳": (22.543, 114.058),
    "成都": (30.573, 104.066),
    "重庆": (29.563, 106.551),
    "杭州": (30.274, 120.155),
    "西安": (34.341, 108.940),
    "昆明": (25.038, 102.718),
    "厦门": (24.479, 118.089),
    "青岛": (36.067, 120.383),
    "三亚": (18.252, 109.512),
    "海口": (20.044, 110.199),
    "大连": (38.914, 121.615),
    "长沙": (28.228, 112.939),
    "武汉": (30.593, 114.306),
    "南京": (32.060, 118.796),
    "郑州": (34.746, 113.625),
    "天津": (39.084, 117.201),
    "贵阳": (26.647, 106.630),
    "桂林": (25.274, 110.290),
    "丽江": (26.872, 100.230),
    "西宁": (36.617, 101.778),
    "兰州": (36.061, 103.834),
    "哈尔滨": (45.803, 126.535),
    "沈阳": (41.805, 123.431),
    "福州": (26.074, 119.297),
    "温州": (27.994, 120.699),
    "宁波": (29.868, 121.544),
    "泉州": (24.874, 118.676),
    "珠海": (22.271, 113.577),
    "拉萨": (29.652, 91.172),
    "乌鲁木齐": (43.825, 87.616),
    "呼和浩特": (40.842, 111.749),
    "延安": (36.585, 109.490),
    # —— 延伸段（小机场，常是弃程票的「票面终点」）——
    "九寨沟": (32.853, 103.683),
    "林芝": (29.303, 94.335),
    "大理": (25.606, 100.268),
    "西双版纳": (21.974, 100.760),
    "腾冲": (24.938, 98.485),
    "香格里拉": (27.827, 99.702),
    "稻城": (29.323, 100.060),
    "喀什": (39.470, 75.990),
    "伊宁": (43.956, 81.330),
    "库尔勒": (41.762, 86.146),
    "敦煌": (40.161, 94.809),
    "张家界": (29.102, 110.479),
    "黄山": (29.733, 118.256),
    "北海": (21.539, 109.294),
    "洛阳": (34.741, 112.437),
    "宜昌": (30.556, 111.482),
    "银川": (38.322, 106.393),
    "嘉峪关": (39.863, 98.341),
    "格尔木": (36.913, 94.903),
    "海拉尔": (49.205, 119.825),
    "满洲里": (49.598, 117.433),
    "喀纳斯": (47.700, 86.870),
    "阿里": (32.114, 80.052),
}

#: 三字码与常见别名 → 城市名。模型两种写法都会出现，统一到这里解析。
ALIASES: dict[str, str] = {
    "BJS": "北京",
    "SHA": "上海",
    "CAN": "广州",
    "SZX": "深圳",
    "CTU": "成都",
    "TFU": "成都",
    "成都天府": "成都",
    "CKG": "重庆",
    "HGH": "杭州",
    "XIY": "西安",
    "KMG": "昆明",
    "XMN": "厦门",
    "TAO": "青岛",
    "SYX": "三亚",
    "HAK": "海口",
    "DLC": "大连",
    "CSX": "长沙",
    "WUH": "武汉",
    "NKG": "南京",
    "CGO": "郑州",
    "TSN": "天津",
    "KWE": "贵阳",
    "KWL": "桂林",
    "LJG": "丽江",
    "XNN": "西宁",
    "LHW": "兰州",
    "HRB": "哈尔滨",
    "SHE": "沈阳",
    "FOC": "福州",
    "WNZ": "温州",
    "NGB": "宁波",
    "JJN": "泉州",
    "ZUH": "珠海",
    "LXA": "拉萨",
    "URC": "乌鲁木齐",
    "HET": "呼和浩特",
    "ENY": "延安",
    "JZH": "九寨沟",
    "LZY": "林芝",
    "DLU": "大理",
    "JHG": "西双版纳",
    "TCZ": "腾冲",
    "DIG": "香格里拉",
    "DCY": "稻城",
    "KHG": "喀什",
    "YIN": "伊宁",
    "KRL": "库尔勒",
    "DNH": "敦煌",
    "DYG": "张家界",
    "TXN": "黄山",
    "BHY": "北海",
    "LYA": "洛阳",
    "YIH": "宜昌",
    "INC": "银川",
    "JGN": "嘉峪关",
    "GOQ": "格尔木",
    "HLD": "海拉尔",
    "NZH": "满洲里",
    "KJI": "喀纳斯",
    "NGQ": "阿里",
}

_EARTH_RADIUS_KM = 6371.0

#: 延伸段至少比目的地再飞这么远，才算「能凑出弃程」。
MIN_ONWARD_KM = 250.0

#: 与「出发地→目的地」的方位角偏差上限（度）。超过就明显不是同一条走向。
MAX_BEARING_DELTA = 60.0

#: 票面终点还必须比目的地离出发地更远这么多倍，避免「反向绕一圈」也算。
FARTHER_RATIO = 1.02


def resolve_city(name: Any) -> str | None:
    """把「成都」「CTU」「成都天府」统一成表里的城市名；不认识返回 None。"""
    text = str(name or "").strip()
    if not text:
        return None
    if text in CITY_COORDS:
        return text
    upper = text.upper()
    if upper in ALIASES:
        return ALIASES[upper]
    return ALIASES.get(text)


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def _bearing_deg(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _angle_delta(a: float, b: float) -> float:
    diff = abs(a - b) % 360
    return min(diff, 360 - diff)


def onward_candidates(
    from_city: Any,
    target_city: Any,
    *,
    limit: int = 3,
    min_leg_km: float = MIN_ONWARD_KM,
    max_bearing_delta: float = MAX_BEARING_DELTA,
) -> list[dict[str, Any]]:
    """返回「票面终点可以设成哪些城市」的候选，按值得一查的程度排序。

    判定条件（全部满足）：
    1. 该城市离出发地比目的地更远（``FARTHER_RATIO``）；
    2. 该城市离目的地至少 ``min_leg_km``（太近可能是同一机场群，凑不出尾段）；
    3. 与「出发地→目的地」的方位角偏差 ≤ ``max_bearing_delta``（同一条走向）。

    排序：方位偏差小的优先（更像同一航线），其次离目的地近的优先（延伸段便宜、
    更容易拼出比直飞更低的总价）。
    """
    origin = resolve_city(from_city)
    target = resolve_city(target_city)
    if not origin or not target or origin == target:
        return []
    origin_coords, target_coords = CITY_COORDS[origin], CITY_COORDS[target]
    base_distance = _haversine_km(origin_coords, target_coords)
    base_bearing = _bearing_deg(origin_coords, target_coords)

    scored: list[tuple[float, float, str, float]] = []
    for city, coords in CITY_COORDS.items():
        if city in (origin, target):
            continue
        distance_from_origin = _haversine_km(origin_coords, coords)
        if distance_from_origin <= base_distance * FARTHER_RATIO:
            continue
        leg_km = _haversine_km(target_coords, coords)
        if leg_km < min_leg_km:
            continue
        delta = _angle_delta(base_bearing, _bearing_deg(origin_coords, coords))
        if delta > max_bearing_delta:
            continue
        scored.append((round(delta, 1), round(leg_km, 1), city, round(distance_from_origin, 1)))

    scored.sort(key=lambda item: (item[0], item[1]))
    return [
        {
            "city": city,
            "leg_km": leg_km,
            "bearing_delta": delta,
            "distance_from_origin_km": distance_from_origin,
            "reason": f"{target}再飞约 {int(leg_km)}km，同向偏差 {delta}°",
        }
        for delta, leg_km, city, distance_from_origin in scored[: max(1, limit)]
    ]
