"""Render a small set of ECharts options as standalone SVG for PDF embedding."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

COLORS = [
    "#2563EB",
    "#10B981",
    "#F59E0B",
    "#8B5CF6",
    "#EF4444",
    "#06B6D4",
    "#F97316",
    "#84CC16",
    "#EC4899",
    "#14B8A6",
]


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


def _cartesian_svg(
    option: dict[str, Any], title: str, chart_type: str
) -> str:
    width = 760
    height = 380
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
            f'height="{height}" viewBox="0 0 {width} {height}">'
        ),
        "<g font-family=\"sans-serif\">",
    ]
    if title:
        parts.append(
            f'<text x="{width / 2}" y="30" text-anchor="middle" '
            f'font-size="20" font-weight="600" fill="#111827">{_escape(title)}</text>'
        )

    for index in range(5):
        ratio = index / 4
        y = top + plot_height - ratio * plot_height
        value = max_value * ratio
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_width}" '
            f'y2="{y:.1f}" stroke="#E5E7EB" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="#6B7280">{value:g}</text>'
        )

    parts.append(
        f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" '
        f'y2="{top + plot_height}" stroke="#9CA3AF" stroke-width="1"/>'
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
                        f'text-anchor="middle" font-size="10" fill="#6B7280">'
                        f"{value:g}</text>"
                    )

    for index, label in enumerate(labels[:category_count]):
        x = left + (index + 0.5) * group_width
        text = label if len(label) <= 10 else label[:9] + "…"
        parts.append(
            f'<text x="{x:.1f}" y="{height - 22}" text-anchor="middle" '
            f'font-size="11" fill="#6B7280">{_escape(text)}</text>'
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
                f'fill="#374151">{_escape(name)}</text>'
            )
            legend_x += 15 + len(name) * 7 + 24

    parts.append("</g></svg>")
    return "".join(parts)


def _pie_svg(option: dict[str, Any], title: str) -> str:
    width = 760
    height = 380
    center_x = 330
    center_y = 210
    radius = 130
    items = _pie_items(option)
    total = sum(value for _, value in items if value > 0)
    if total <= 0:
        items = [(name, 1.0) for name, _ in items]
        total = float(len(items)) or 1.0

    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">'
        ),
        "<g font-family=\"sans-serif\">",
    ]
    if title:
        parts.append(
            f'<text x="{width / 2}" y="30" text-anchor="middle" '
            f'font-size="20" font-weight="600" fill="#111827">{_escape(title)}</text>'
        )

    start = -math.pi / 2
    visible = items[:12]
    for index, (name, value) in enumerate(visible):
        color = COLORS[index % len(COLORS)]
        sweep = value / total * 2 * math.pi
        end = start + sweep
        x1 = center_x + radius * math.cos(start)
        y1 = center_y + radius * math.sin(start)
        x2 = center_x + radius * math.cos(end)
        y2 = center_y + radius * math.sin(end)
        large = 1 if sweep > math.pi else 0
        parts.append(
            f'<path d="M {center_x} {center_y} L {x1:.1f} {y1:.1f} '
            f'A {radius} {radius} 0 {large} 1 {x2:.1f} {y2:.1f} Z" '
            f'fill="{color}" stroke="#FFFFFF" stroke-width="2"/>'
        )
        mid = start + sweep / 2
        label_x = center_x + (radius + 34) * math.cos(mid)
        label_y = center_y + (radius + 22) * math.sin(mid)
        percent = value / total * 100
        text = f"{name} {percent:.1f}%" if name else f"{percent:.1f}%"
        anchor = "start" if label_x >= center_x else "end"
        parts.append(
            f'<text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="{anchor}" '
            f'font-size="11" fill="#374151">{_escape(text)}</text>'
        )
        start = end

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
