"""Render a small set of ECharts options as standalone SVG for PDF embedding."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

# SVG 导出固定在浅底（PDF 嵌入 / 白卡片），系列色板用科研主题定性色的
# light 档排序；灰阶 token 对应 echarts-scientific-themes.html 的 light 档
# （ink / inkSub / axisLabel / axisBase / axisSplit）。
COLORS = [
    "#F3962F",  # qual[0]
    "#036EAD",
    "#DD656D",
    "#506AAA",
    "#61A7D0",
    "#E17692",
    "#728DC1",
    "#FACC8F",  # fill-only：白底对比度仅 1.49，只做兜底末位
]
INK = "#33475F"        # 标题 / 主文字
INK_SUB = "#7A8699"    # 图例名、饼图扇区标注
AXIS_LABEL = "#98A2B3" # 刻度值、柱顶数值标签
AXIS_BASE = "#E4E9F0"  # X 轴 1px 基线（"地面"）
AXIS_SPLIT = "#F2F5F9" # 水平网格线，明度贴近卡片底色


def _safe_name(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "_", name).strip("._")[:60]
    return cleaned or fallback


def _series_list(option: dict[str, Any]) -> list[dict[str, Any]]:
    series = option.get("series")
    if not isinstance(series, list):
        return []
    return [item for item in series if isinstance(item, dict)]


def _chart_type(option: dict[str, Any]) -> str:
    series = _series_list(option)
    if not series:
        return "bar"
    value = series[0].get("type")
    if isinstance(value, str) and value:
        return value
    return "bar"


def _axis_labels(option: dict[str, Any]) -> list[str]:
    axis = option.get("xAxis")
    if isinstance(axis, list):
        axis = axis[0] if axis else {}
    if not isinstance(axis, dict):
        return []
    data = axis.get("data")
    if not isinstance(data, list):
        return []
    return [str(item) for item in data]


def _series_values(series: dict[str, Any]) -> list[float]:
    data = series.get("data")
    if not isinstance(data, list):
        return []
    values: list[float] = []
    for item in data:
        if isinstance(item, (int, float)):
            values.append(float(item))
        elif isinstance(item, dict):
            value = item.get("value")
            if isinstance(value, (int, float)):
                values.append(float(value))
            else:
                values.append(0.0)
        else:
            try:
                values.append(float(str(item)))
            except (TypeError, ValueError):
                values.append(0.0)
    return values


def _pie_items(option: dict[str, Any]) -> list[tuple[str, float]]:
    series = _series_list(option)
    if not series:
        return []
    data = series[0].get("data")
    if not isinstance(data, list):
        return []
    items: list[tuple[str, float]] = []
    for item in data:
        if isinstance(item, dict):
            name = str(item.get("name") or "未命名")
            value = item.get("value")
            if isinstance(value, (int, float)):
                items.append((name, float(value)))
        else:
            try:
                items.append(("", float(item)))
            except (TypeError, ValueError):
                continue
    return items


def _nice_max(value: float) -> float:
    if value <= 0:
        return 1.0
    exponent = math.floor(math.log10(value))
    fraction = value / (10**exponent)
    if fraction <= 1:
        nice = 1
    elif fraction <= 2:
        nice = 2
    elif fraction <= 5:
        nice = 5
    else:
        nice = 10
    return nice * (10**exponent)


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _axis_dict(option: dict[str, Any], key: str) -> dict[str, Any] | None:
    """Resolve an xAxis/yAxis entry to a single dict (arrays take [0])."""
    axis = option.get(key)
    if isinstance(axis, list):
        axis = axis[0] if axis else None
    return axis if isinstance(axis, dict) else None


def _is_horizontal_bar(option: dict[str, Any]) -> bool:
    """True when bars run along x: value x-axis + category y-axis."""
    x_axis = _axis_dict(option, "xAxis")
    y_axis = _axis_dict(option, "yAxis")
    if x_axis is None or y_axis is None:
        return False
    x_is_category = x_axis.get("type") == "category" or isinstance(
        x_axis.get("data"), list
    )
    y_data = y_axis.get("data")
    y_is_category = y_axis.get("type") == "category" or (
        isinstance(y_data, list) and len(y_data) > 0
    )
    return y_is_category and not x_is_category


def _text_width(text: str, size: float) -> float:
    """Rough width: CJK glyphs are square, latin ~0.55em (sans-serif)."""
    width = 0.0
    for char in text:
        width += size if ord(char) > 127 else size * 0.55
    return width


def _clip_text(text: str, size: float, max_width: float) -> str:
    """Clip to max_width by glyph, appending an ellipsis when truncated."""
    if _text_width(text, size) <= max_width:
        return text
    out: list[str] = []
    width = 0.0
    limit = max_width - _text_width("…", size)
    for char in text:
        char_width = size if ord(char) > 127 else size * 0.55
        if width + char_width > limit:
            break
        width += char_width
        out.append(char)
    return "".join(out) + "…"


# Thick bar cap (px, along the bar's minor axis). Mirrors the front-end
# barMaxWidth: 30 so the Python SVG export and the on-page ECharts agree.
_HBAR_MAX_THICKNESS = 30.0


def _hbar_svg(option: dict[str, Any], title: str) -> str:
    """Horizontal bars: y categories run top-down, values extend rightward."""
    width = 760
    height = 380
    caption_lines = _bottom_caption_lines(option)
    caption_height = sum(_caption_line_height(size) for _, size, _ in caption_lines)
    canvas_height = height + caption_height + 8 if caption_height else height
    right = 24
    top = 56
    bottom = 62
    plot_height = height - top - bottom

    series = _series_list(option)
    y_axis = _axis_dict(option, "yAxis")
    y_data = y_axis.get("data") if y_axis else None
    labels = [str(item) for item in y_data] if isinstance(y_data, list) else []
    label_rows = [label.split("\n") for label in labels]

    all_values: list[float] = []
    for item in series:
        values = _series_values(item)
        if not values:
            values = [0.0] * max(1, len(labels))
        all_values.extend(values)
    if not labels:
        labels = [str(index + 1) for index in range(max(len(all_values), 1))]
        label_rows = [[label] for label in labels]
    max_value = _nice_max(max(all_values or [1.0]))
    category_count = max(len(labels), 1)
    row_height = plot_height / category_count
    series_count = max(len(series), 1)
    slot = row_height / series_count if series_count > 1 else row_height

    # Left gutter sized by the longest visible category line.
    longest = 0.0
    for rows in label_rows:
        for row in rows[:2]:
            longest = max(longest, _text_width(row, 10))
    left = max(96, 18 + int(longest) + 10)
    plot_width = width - left - right

    def bar_thickness(item: dict[str, Any]) -> float:
        auto = min(slot * 0.72, _HBAR_MAX_THICKNESS)
        explicit = item.get("barWidth")
        if isinstance(explicit, (int, float)) and not isinstance(explicit, bool):
            return max(2.0, min(float(explicit), auto))
        return max(2.0, auto)

    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{canvas_height}" viewBox="0 0 {width} {canvas_height}">'
        ),
        "<g font-family=\"sans-serif\">",
    ]
    if title:
        parts.append(
            f'<text x="{width / 2}" y="30" text-anchor="middle" '
            f'font-size="20" font-weight="600" fill="{INK}">{_escape(title)}</text>'
        )

    # Vertical value gridlines (baseline drawn separately below).
    for index in range(1, 5):
        ratio = index / 4
        x = left + ratio * plot_width
        parts.append(
            f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" '
            f'y2="{top + plot_height}" stroke="{AXIS_SPLIT}" stroke-width="1"/>'
        )
    parts.append(
        f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" '
        f'y2="{top + plot_height}" stroke="{AXIS_BASE}" stroke-width="1"/>'
    )

    for series_index, item in enumerate(series):
        values = _series_values(item)
        if not values:
            continue
        color = COLORS[series_index % len(COLORS)]
        thickness = bar_thickness(item)
        for index, value in enumerate(values[:category_count]):
            if value <= 0:
                continue
            length = max(2.0, value / max_value * plot_width)
            rect_y = top + index * row_height + series_index * slot + (
                slot - thickness
            ) / 2
            parts.append(
                f'<rect x="{left}" y="{rect_y:.1f}" width="{length:.1f}" '
                f'height="{thickness:.1f}" rx="2" fill="{color}"/>'
            )
            # Value label hugs the bar end: outside when room, else inside.
            label_x = left + length + 6
            anchor = "start"
            if label_x + 34 > left + plot_width:
                label_x = left + length - 6
                anchor = "end"
            parts.append(
                f'<text x="{label_x:.1f}" y="{rect_y + thickness / 2 + 3.5:.1f}" '
                f'text-anchor="{anchor}" font-size="10" fill="{AXIS_LABEL}">'
                f"{value:g}</text>"
            )

    # Y-axis category labels: multi-line via tspan, clipped to the gutter.
    for index, rows in enumerate(label_rows):
        rows = [row for row in rows if row.strip()] or [labels[index]]
        clipped = [_clip_text(row, 10, left - 12) for row in rows[:2]]
        cy = top + row_height * (index + 0.5)
        baseline = cy + 4 - (len(clipped) - 1) * 6.5
        text = (
            f'<text x="{left - 12}" y="{baseline:.1f}" text-anchor="end" '
            f'font-size="10" fill="{AXIS_LABEL}">'
        )
        text += _escape(clipped[0])
        for row in clipped[1:]:
            text += f'<tspan x="{left - 12}" dy="13">{_escape(row)}</tspan>'
        text += "</text>"
        parts.append(text)

    # Bottom value scale labels.
    for index in range(5):
        ratio = index / 4
        x = left + ratio * plot_width
        value = max_value * ratio
        parts.append(
            f'<text x="{x:.1f}" y="{height - 22}" text-anchor="middle" '
            f'font-size="11" fill="{AXIS_LABEL}">{value:g}</text>'
        )

    # xAxis name, bottom-right of the value axis.
    x_axis = _axis_dict(option, "xAxis")
    axis_name = x_axis.get("name") if x_axis else None
    if isinstance(axis_name, str) and axis_name:
        parts.append(
            f'<text x="{width - right}" y="{height - 8}" text-anchor="end" '
            f'font-size="11" fill="{AXIS_LABEL}">{_escape(axis_name)}</text>'
        )

    if len(series) > 1:
        legend_y = height - 34
        legend_x = left
        for index, item in enumerate(series[:6]):
            color = COLORS[index % len(COLORS)]
            name = str(item.get("name") or item.get("seriesName") or f"系列{index + 1}")
            parts.append(
                f'<rect x="{legend_x}" y="{legend_y - 8}" width="10" '
                f'height="10" rx="2" fill="{color}"/>'
            )
            parts.append(
                f'<text x="{legend_x + 15}" y="{legend_y}" font-size="11" '
                f'fill="{INK_SUB}">{_escape(name)}</text>'
            )
            legend_x += 15 + len(name) * 7 + 24

    if caption_height:
        parts.append(_bottom_caption(option, width, canvas_height))
    parts.append("</g></svg>")
    return "".join(parts)


def _cartesian_svg(
    option: dict[str, Any], title: str, chart_type: str
) -> str:
    if chart_type == "bar" and _is_horizontal_bar(option):
        return _hbar_svg(option, title)
    width = 760
    height = 380
    # A "数据来源：…" caption gets its own strip appended below the chart, so
    # the plot layout below stays anchored to the base 380px canvas.
    caption_lines = _bottom_caption_lines(option)
    caption_height = sum(_caption_line_height(size) for _, size, _ in caption_lines)
    canvas_height = height + caption_height + 8 if caption_height else height
    left = 72
    right = 24
    top = 56
    bottom = 62
    plot_width = width - left - right
    plot_height = height - top - bottom
    series = _series_list(option)
    labels = _axis_labels(option)
    all_values: list[float] = []
    for item in series:
        values = _series_values(item)
        if not values:
            values = [0.0] * max(1, len(labels))
        all_values.extend(values)
    max_value = _nice_max(max(all_values or [1.0]))
    if len(labels) == 0:
        labels = [str(index + 1) for index in range(max(len(all_values), 1))]
    category_count = max(len(labels), 1)
    group_width = plot_width / category_count
    series_count = max(len(series), 1)
    bar_width = max(2.0, group_width / series_count * 0.72)

    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{canvas_height}" viewBox="0 0 {width} {canvas_height}">'
        ),
        "<g font-family=\"sans-serif\">",
    ]
    if title:
        parts.append(
            f'<text x="{width / 2}" y="30" text-anchor="middle" '
            f'font-size="20" font-weight="600" fill="{INK}">{_escape(title)}</text>'
        )

    for index in range(5):
        ratio = index / 4
        y = top + plot_height - ratio * plot_height
        value = max_value * ratio
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_width}" '
            f'y2="{y:.1f}" stroke="{AXIS_SPLIT}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="{AXIS_LABEL}">{value:g}</text>'
        )

    parts.append(
        f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" '
        f'y2="{top + plot_height}" stroke="{AXIS_BASE}" stroke-width="1"/>'
    )

    if chart_type == "line":
        for series_index, item in enumerate(series):
            values = _series_values(item)
            if not values:
                continue
            color = COLORS[series_index % len(COLORS)]
            points: list[str] = []
            for index, value in enumerate(values[:category_count]):
                x = left + (index + 0.5) * group_width
                y = top + plot_height - (value / max_value) * plot_height
                points.append(f"{x:.1f},{y:.1f}")
                parts.append(
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}"/>'
                )
            if len(points) >= 2:
                parts.append(
                    f'<polyline points="{" ".join(points)}" fill="none" '
                    f'stroke="{color}" stroke-width="2.5"/>'
                )
    else:
        for series_index, item in enumerate(series):
            values = _series_values(item)
            if not values:
                continue
            color = COLORS[series_index % len(COLORS)]
            for index, value in enumerate(values[:category_count]):
                x = left + index * group_width + series_index * bar_width
                y = top + plot_height - (value / max_value) * plot_height
                bar_height = max(0.0, top + plot_height - y)
                parts.append(
                    f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" '
                    f'height="{bar_height:.1f}" rx="2" fill="{color}"/>'
                )
                if category_count <= 12 and bar_height >= 18:
                    parts.append(
                        f'<text x="{x + bar_width / 2:.1f}" y="{y - 5:.1f}" '
                        f'text-anchor="middle" font-size="10" fill="{AXIS_LABEL}">'
                        f"{value:g}</text>"
                    )

    for index, label in enumerate(labels[:category_count]):
        x = left + (index + 0.5) * group_width
        text = label if len(label) <= 10 else label[:9] + "…"
        parts.append(
            f'<text x="{x:.1f}" y="{height - 22}" text-anchor="middle" '
            f'font-size="11" fill="{AXIS_LABEL}">{_escape(text)}</text>'
        )

    if len(series) > 1:
        legend_y = height - 34
        legend_x = left
        for index, item in enumerate(series[:6]):
            color = COLORS[index % len(COLORS)]
            name = str(item.get("name") or item.get("seriesName") or f"系列{index + 1}")
            parts.append(
                f'<rect x="{legend_x}" y="{legend_y - 8}" width="10" '
                f'height="10" rx="2" fill="{color}"/>'
            )
            parts.append(
                f'<text x="{legend_x + 15}" y="{legend_y}" font-size="11" '
                f'fill="{INK_SUB}">{_escape(name)}</text>'
            )
            legend_x += 15 + len(name) * 7 + 24

    if caption_height:
        parts.append(_bottom_caption(option, width, canvas_height))
    parts.append("</g></svg>")
    return "".join(parts)


def _percent_radius(value: Any, base: float) -> float:
    """Resolve an ECharts radius value (percent string or number) to px."""
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("%"):
            try:
                return float(text[:-1]) / 100.0 * base
            except ValueError:
                return base
        try:
            return float(text)
        except ValueError:
            return base
    try:
        return float(value)
    except (TypeError, ValueError):
        return base


def _slice_color(item: dict[str, Any], index: int) -> str:
    item_style = item.get("itemStyle")
    if isinstance(item_style, dict):
        color = item_style.get("color")
        if isinstance(color, str) and color:
            return color
    return COLORS[index % len(COLORS)]


def _fmt_percent(value: float) -> str:
    if abs(value - round(value)) < 0.05:
        return str(int(round(value)))
    return f"{value:.1f}"


def _annular_path(
    cx: float, cy: float, r0: float, r1: float, a0: float, a1: float
) -> str:
    """SVG path for one donut sector between inner radius r0 and outer r1."""
    large = 1 if (a1 - a0) > math.pi else 0
    x0 = cx + r0 * math.cos(a0)
    y0 = cy + r0 * math.sin(a0)
    x1 = cx + r1 * math.cos(a0)
    y1 = cy + r1 * math.sin(a0)
    x2 = cx + r1 * math.cos(a1)
    y2 = cy + r1 * math.sin(a1)
    x3 = cx + r0 * math.cos(a1)
    y3 = cy + r0 * math.sin(a1)
    return (
        f"M {x0:.1f} {y0:.1f} L {x1:.1f} {y1:.1f} "
        f"A {r1:.1f} {r1:.1f} 0 {large} 1 {x2:.1f} {y2:.1f} "
        f"L {x3:.1f} {y3:.1f} A {r0:.1f} {r0:.1f} 0 {large} 0 {x0:.1f} {y0:.1f} Z"
    )


def _sector_path(cx: float, cy: float, r: float, a0: float, a1: float) -> str:
    large = 1 if (a1 - a0) > math.pi else 0
    x1 = cx + r * math.cos(a0)
    y1 = cy + r * math.sin(a0)
    x2 = cx + r * math.cos(a1)
    y2 = cy + r * math.sin(a1)
    return (
        f"M {cx} {cy} L {x1:.1f} {y1:.1f} "
        f"A {r:.1f} {r:.1f} 0 {large} 1 {x2:.1f} {y2:.1f} Z"
    )


def _pie_legend(option: dict[str, Any], center_y: float) -> str:
    """Vertical legend on the left, matching the on-page pie legend."""
    series = _series_list(option)
    if not series:
        return ""
    data = series[0].get("data")
    if not isinstance(data, list):
        return ""
    items = [
        item for item in data if isinstance(item, dict) and item.get("name")
    ]
    if len(items) <= 1:
        return ""
    parts: list[str] = []
    start_y = center_y - (len(items) * 18) / 2
    for index, item in enumerate(items):
        color = _slice_color(item, index)
        name = str(item.get("name") or "")
        parts.append(
            f'<rect x="16" y="{start_y + index * 18 - 7:.1f}" width="10" '
            f'height="10" rx="2" fill="{color}"/>'
        )
        parts.append(
            f'<text x="33" y="{start_y + index * 18:.1f}" font-size="11" '
            f'fill="{INK_SUB}">{_escape(name)}</text>'
        )
    return "".join(parts)


def _bottom_caption_lines(option: dict[str, Any]) -> list[tuple[str, int, str]]:
    """Collect "数据来源：…" graphic text elements as (line, size, fill)."""
    graphic = option.get("graphic")
    items: list[Any] = []
    if isinstance(graphic, list):
        items = graphic
    elif isinstance(graphic, dict):
        elements = graphic.get("elements")
        items = elements if isinstance(elements, list) else [graphic]
    lines: list[tuple[str, int, str]] = []
    for g in items:
        if not isinstance(g, dict) or g.get("type") != "text":
            continue
        style = g.get("style")
        if not isinstance(style, dict):
            continue
        text = style.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        size = style.get("fontSize")
        size = size if isinstance(size, (int, float)) else 12
        fill = style.get("fill")
        fill = fill if isinstance(fill, str) else INK_SUB
        for line in text.split("\n"):
            if line.strip():
                lines.append((line.strip(), size, fill))
    return lines


def _caption_line_height(size: float) -> int:
    """Comfortable line height (1.5x font size) for caption text lines."""
    return int(round(size * 1.5))


def _bottom_caption(option: dict[str, Any], width: int, height: int) -> str:
    """Render "数据来源：…" graphic text elements at the bottom of the chart."""
    lines = _bottom_caption_lines(option)
    if not lines:
        return ""
    parts: list[str] = []
    total_height = sum(_caption_line_height(size) for _, size, _ in lines)
    y = height - 8 - total_height
    for line, size, fill in lines:
        parts.append(
            f'<text x="{width / 2}" y="{y:.1f}" text-anchor="middle" '
            f'font-size="{size}" fill="{_escape(fill)}">'
            f"{_escape(line)}</text>"
        )
        y += _caption_line_height(size)
    return "".join(parts)


def _pie_svg(option: dict[str, Any], title: str) -> str:
    width = 760
    height = 380
    # A "数据来源：…" caption gets its own strip appended below the chart, so
    # the ring layout below stays anchored to the base 380px canvas.
    caption_lines = _bottom_caption_lines(option)
    caption_height = sum(_caption_line_height(size) for _, size, _ in caption_lines)
    canvas_height = height + caption_height + 8 if caption_height else height
    center_x = 380
    center_y = 205
    radius_base = min(width, height) / 2
    series = _series_list(option)
    raw_data: list[Any] = []
    radius: Any = None
    if series:
        raw_data = series[0].get("data")
        if not isinstance(raw_data, list):
            raw_data = []
        radius = series[0].get("radius")
    inner_r = 0.0
    outer_r = 130.0
    # Mirror the on-page radius cap: when a title/caption is present the ring
    # is capped at 62% of the smaller canvas side so it can't crowd the title.
    has_content = bool(title) or bool(caption_lines)
    cap_outer = 0.62 * radius_base if has_content else 135.0
    if isinstance(radius, (list, tuple)) and len(radius) == 2:
        outer_raw = _percent_radius(radius[1], radius_base)
        inner_raw = _percent_radius(radius[0], radius_base)
        if outer_raw > cap_outer:
            scale = cap_outer / outer_raw
            outer_r = cap_outer
            inner_r = inner_raw * scale
        else:
            outer_r = outer_raw
            inner_r = inner_raw
    elif isinstance(radius, (int, float, str)):
        outer_r = min(_percent_radius(radius, radius_base), cap_outer)
    else:
        outer_r = min(outer_r, cap_outer)
    if inner_r > 0:
        # Plain donut: thin ring (at most ~16% of the smaller side wide).
        inner_r = max(inner_r, outer_r - 0.16 * radius_base)

    items = _pie_items(option)
    total = sum(value for _, value in items if value > 0)
    if total <= 0:
        items = [(name, 1.0) for name, _ in items]
        total = float(len(items)) or 1.0

    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{canvas_height}" viewBox="0 0 {width} {canvas_height}">'
        ),
        "<g font-family=\"sans-serif\">",
    ]
    if title:
        parts.append(
            f'<text x="{width / 2}" y="30" text-anchor="middle" '
            f'font-size="20" font-weight="600" fill="{INK}">{_escape(title)}</text>'
        )

    start = -math.pi / 2
    visible = items[:12]
    for index, (name, value) in enumerate(visible):
        raw = (
            raw_data[index]
            if index < len(raw_data) and isinstance(raw_data[index], dict)
            else {}
        )
        color = _slice_color(raw, index)
        sweep = value / total * 2 * math.pi
        end = start + sweep
        if inner_r > 0:
            path = _annular_path(center_x, center_y, inner_r, outer_r, start, end)
        else:
            path = _sector_path(center_x, center_y, outer_r, start, end)
        parts.append(f'<path d="{path}" fill="{color}"/>')
        mid = start + sweep / 2
        percent = value / total * 100
        # Classic look: name + percent beside the slice (never on the ring).
        label_x = center_x + (outer_r + 34) * math.cos(mid)
        label_y = center_y + (outer_r + 22) * math.sin(mid)
        text = (
            f"{name} {_fmt_percent(percent)}%"
            if name
            else f"{_fmt_percent(percent)}%"
        )
        anchor = "start" if label_x >= center_x else "end"
        parts.append(
            f'<text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="{anchor}" '
            f'font-size="11" fill="{INK_SUB}">{_escape(text)}</text>'
        )
        start = end

    # The on-page chart drops the legend when hidden labels are re-enabled as
    # outside labels; mirror that here so the SVG matches the page.
    label = series[0].get("label") if series else None
    labels_hidden = isinstance(label, dict) and label.get("show") is False
    if not (labels_hidden and len(visible) <= 8):
        parts.append(_pie_legend(option, center_y))
    if caption_height:
        parts.append(_bottom_caption(option, width, canvas_height))
    parts.append("</g></svg>")
    return "".join(parts)


def render_chart_svg(option: dict[str, Any], title: str = "") -> str:
    chart_type = _chart_type(option)
    if chart_type == "pie":
        return _pie_svg(option, title)
    return _cartesian_svg(option, title, chart_type)


def save_chart_svg(
    option: dict[str, Any],
    output_root: Path,
    title: str,
) -> tuple[Path, str]:
    chart_dir = output_root / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)
    name = _safe_name(title, "chart")
    output_path = chart_dir / f"{name}.svg"
    svg = render_chart_svg(option, title)
    output_path.write_text(svg, encoding="utf-8")
    return output_path, svg
