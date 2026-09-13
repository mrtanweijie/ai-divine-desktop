"""PPT slides 归一化层：把模型的自然表达收敛到渲染器窄键（宽进窄出）。

背景（docs/fix/001-ppt-empty-slides-20260906.md §3.1）：渲染器 14 个版式各自只读窄键
（points 字符串数组 + "标题|描述" 竖线分隔），模型常发结构化 items /
quote / events 等别名键——之前这些键被静默丢弃，兜底渲染"暂无内容"。
本层在渲染前做键归一，未识别键如实上报 warnings，不再静默。

别名键清单以 tool_runs 历史真实输入为准（霸王茶姬/智谱/OP.GG 等样本）。
"""

from __future__ import annotations

from typing import Any

# dict 条目的标题/描述键族（cards/timeline 通用）
_TITLE_KEYS = ("title", "heading", "name", "label", "event")
_DESC_KEYS = ("desc", "description", "body", "text", "content", "detail", "value")
# kpi 专用：value|label|delta 顺序
_KPI_VALUE_KEYS = ("value", "num", "number", "current")
_KPI_LABEL_KEYS = ("label", "name", "title", "metric")
_KPI_DELTA_KEYS = ("delta", "desc", "change", "trend", "note", "yoy")
# timeline 专用：日期前置
_DATE_KEYS = ("date", "time", "year", "period", "stage", "phase")

_STANDARD_KEYS = {
    "layout", "heading", "title", "subtitle", "body", "content", "text",
    "points", "chart", "table", "image", "left", "right", "toc", "note",
    "quote", "items", "events", "cards", "milestones", "steps", "bullets",
    "list", "cols", "_pages",
    # 封面元信息（keynote/devconf 样张主题使用）
    "brand", "event", "kicker", "date", "place", "speaker",
}

# 内容版式（空页检测范围；cover/section/end/toc 天然少字不参与）
CONTENT_LAYOUTS = {
    "bullets", "cards", "timeline", "columns", "two_col", "compare",
    "kpi", "quote", "table", "chart",
}

# 正文内容量阈值（字符）：标题不计入——事故页全有标题但正文为空
_EMPTY_PAGE_CHARS = 6


def _first(item: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _point_from_dict(item: dict, layout: str) -> str:
    """dict 条目 → 竖线分隔字符串，按版式语境选择键序。"""
    if layout == "kpi":
        parts = [
            _first(item, _KPI_VALUE_KEYS),
            _first(item, _KPI_LABEL_KEYS),
            _first(item, _KPI_DELTA_KEYS),
        ]
        joined = "|".join(part for part in parts if part)
        if joined:
            return joined
    date = _first(item, _DATE_KEYS)
    title = _first(item, _TITLE_KEYS)
    desc = _first(item, _DESC_KEYS)
    if date and layout in ("timeline", "milestones"):
        head = f"{date}：{title}" if title else date
        return f"{head}|{desc}" if desc else head
    if title and desc:
        return f"{title}|{desc}"
    return title or desc or str(item)


def _to_points(value: Any, layout: str) -> list[str]:
    """list 条目（str/dict 混合）→ points 字符串数组。"""
    if not isinstance(value, list):
        return []
    points: list[str] = []
    for entry in value:
        if isinstance(entry, dict):
            point = _point_from_dict(entry, layout)
        else:
            point = str(entry).strip()
        if point:
            points.append(point)
    return points


def _normalize_compare_side(side: Any, warnings: list[str], where: str) -> Any:
    """compare 的 left/right：bullets/items 别名 → points。"""
    if not isinstance(side, dict):
        return side
    if side.get("points"):
        return side
    for key in ("bullets", "items", "list"):
        value = side.get(key)
        if isinstance(value, list) and value:
            points = [
                _point_from_dict(entry, "") if isinstance(entry, dict) else str(entry).strip()
                for entry in value
            ]
            points = [p for p in points if p]
            if points:
                warnings.append(f"{where} 的 {key} 已转换为 points")
                merged = dict(side)
                merged["points"] = points
                return merged
    return side


def normalize_slide(item: Any) -> tuple[dict, list[str]]:
    """归一化单页；返回 (归一化副本, warnings)。非 dict 原样返回。"""
    warnings: list[str] = []
    if not isinstance(item, dict):
        return item, warnings
    out = dict(item)
    layout = str(out.get("layout") or "").strip().lower()

    # 1) 标题别名：title → heading（渲染器多数版式优先读 heading）
    if not out.get("heading") and out.get("title"):
        out["heading"] = str(out["title"])

    # 2) quote：quote/text 键是金句正文（渲染器把 heading 当金句渲染），
    #    事故样本里 heading="核心结论" 与 quote 并存——quote 布式下 quote 键优先
    if layout == "quote" and str(out.get("quote") or "").strip():
        out["heading"] = str(out["quote"])
        warnings.append("quote 键已作为金句正文")
    elif "quote" in out and out.get("quote") and not out.get("heading"):
        out["heading"] = str(out["quote"])
        warnings.append("quote 键已转换为标题文本")

    # 3) bullets/list/body 字符串 → points
    if not out.get("points"):
        for key in ("bullets", "list"):
            value = out.get(key)
            if isinstance(value, list) and value:
                out["points"] = _to_points(value, layout)
                if out["points"]:
                    warnings.append(f"{key} 键已转换为 points")
                    break
    if not out.get("points"):
        for key in ("body", "content", "text"):
            value = out.get(key)
            if isinstance(value, str) and value.strip() and "\n" in value:
                lines = [line.strip() for line in value.splitlines() if line.strip()]
                if len(lines) > 1:
                    out["points"] = lines
                    warnings.append(f"{key} 多行文本已拆分为 points")
                    break

    # 4) 结构化 items/events/cards/milestones/steps → points（版式感知键序）
    if not out.get("points"):
        for key in ("items", "events", "cards", "milestones", "steps"):
            value = out.get(key)
            if isinstance(value, list) and value:
                points = _to_points(value, layout)
                if points:
                    out["points"] = points
                    warnings.append(f"{key} 键已转换为 points（{layout or '自动'}版式）")
                    break

    # 5) compare 双栏内别名
    if layout == "compare" or ("left" in out and "right" in out):
        if isinstance(out.get("left"), dict) and isinstance(out.get("right"), dict):
            out["left"] = _normalize_compare_side(out["left"], warnings, "left")
            out["right"] = _normalize_compare_side(out["right"], warnings, "right")

    # 6) 未识别键如实上报（不再静默丢弃）
    extras = sorted(set(out) - _STANDARD_KEYS)
    for key in extras:
        warnings.append(f"未识别的键 {key!r} 已忽略")

    return out, warnings


def normalize_slides(items: list[Any]) -> tuple[list[Any], list[str]]:
    """归一化整份 slides；返回 (归一化列表, 汇总 warnings)。"""
    normalized: list[Any] = []
    warnings: list[str] = []
    for index, item in enumerate(items or [], 1):
        slide, slide_warnings = normalize_slide(item)
        normalized.append(slide)
        for warning in slide_warnings:
            warnings.append(f"第 {index} 页：{warning}")
    return normalized, warnings


def check_empty_pages(items: list[Any], layouts: list[str]) -> list[str]:
    """内容版式空页检测：正文内容量低于阈值即告警（cover/section/end/toc 豁免）。

    标题不计入内容量——事故样本每页都有标题、正文全空，标题参与计算会漏检。
    quote 布式例外：heading 本身就是金句正文。
    """
    warnings: list[str] = []
    for index, (item, layout) in enumerate(zip(items, layouts), 1):
        if layout not in CONTENT_LAYOUTS:
            continue
        slide = item if isinstance(item, dict) else {}
        volume = 0
        points = slide.get("points")
        if isinstance(points, list):
            volume += sum(len(str(p)) for p in points)
        for key in ("body", "content", "left", "right", "chart", "table"):
            # chart / table 也算实质内容，否则图表页会被误判为「内容过少」
            value = slide.get(key)
            if isinstance(value, str):
                volume += len(value.strip())
            elif isinstance(value, dict):
                volume += sum(len(str(v)) for v in value.values())
        if layout == "quote":
            volume += len(str(slide.get("heading") or "").strip())
        if volume < _EMPTY_PAGE_CHARS:
            warnings.append(
                f"第 {index} 页（{layout}）正文内容为空或过少，建议补充要点后重试"
            )
    return warnings
