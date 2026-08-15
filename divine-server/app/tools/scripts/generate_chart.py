import json
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.chart_svg import render_chart_svg


_ALLOWED_SERIES_TYPES = {
    "line",
    "bar",
    "pie",
    "scatter",
    "radar",
    "funnel",
    "gauge",
    "heatmap",
    "boxplot",
    "candlestick",
    "sankey",
    "sunburst",
    "treemap",
    "graph",
    "tree",
    "parallel",
    "effectScatter",
    "pictorialBar",
    "themeRiver",
    "custom",
}

MAX_SERIES = 16
MAX_POINTS = 5000
MAX_OPTION_CHARS = 200_000


def _series_type(item: object) -> str:
    if isinstance(item, dict):
        value = item.get("type")
        return value if isinstance(value, str) else ""
    return ""


def _count_points(series: list[object]) -> int:
    total = 0
    for item in series:
        if not isinstance(item, dict):
            continue
        data = item.get("data")
        if isinstance(data, list):
            total += len(data)
    return total


def _option_title(title: str, option: dict[str, object]) -> str:
    if title:
        return title
    raw_title = option.get("title")
    if isinstance(raw_title, dict):
        text = raw_title.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return "图表"


def main() -> None:
    data = json.load(sys.stdin)
    params = data.get("params") or {}
    option = params.get("option")
    title = str(params.get("title") or "").strip()

    if not isinstance(option, dict):
        print(
            json.dumps(
                {"success": False, "message": "option 必须是合法的 ECharts option 对象"},
                ensure_ascii=False,
            )
        )
        return
    serialized = json.dumps(option, ensure_ascii=False)
    if len(serialized) > MAX_OPTION_CHARS:
        print(
            json.dumps(
                {
                    "success": False,
                    "message": f"图表 option 超过 {MAX_OPTION_CHARS} 字符限制",
                },
                ensure_ascii=False,
            )
        )
        return

    series = option.get("series")
    if not isinstance(series, list) or not series:
        print(
            json.dumps(
                {"success": False, "message": "图表 option 必须包含非空 series 数组"},
                ensure_ascii=False,
            )
        )
        return
    if len(series) > MAX_SERIES:
        print(
            json.dumps(
                {"success": False, "message": f"系列数量不能超过 {MAX_SERIES} 个"},
                ensure_ascii=False,
            )
        )
        return
    if _count_points(series) > MAX_POINTS:
        print(
            json.dumps(
                {
                    "success": False,
                    "message": f"图表数据点不能超过 {MAX_POINTS} 个，请先聚合或抽样",
                },
                ensure_ascii=False,
            )
        )
        return
    unknown_types = sorted(
        {
            series_type
            for item in series
            if (series_type := _series_type(item)) not in _ALLOWED_SERIES_TYPES
        }
    )
    if unknown_types:
        allowed = "、".join(sorted(_ALLOWED_SERIES_TYPES))
        print(
            json.dumps(
                {
                    "success": False,
                    "message": (
                        f"不支持的图表类型：{'、'.join(unknown_types)}；"
                        f"仅支持 {allowed}"
                    ),
                },
                ensure_ascii=False,
            )
        )
        return

    chart_type = _series_type(series[0]) or "line"
    chart_title = _option_title(title, option)
    summary = (
        f"图表已生成：{chart_title}"
        f"（{chart_type}，{len(series)} 个系列）"
    )
    output_root = Path(data.get("output_dir") or data.get("workspace")).resolve()
    chart_dir = output_root / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)
    safe_title = re.sub(r"[\\/:*?\"<>|\s]+", "_", chart_title).strip("._")[:60]
    chart_path = chart_dir / f"{safe_title or 'chart'}-{uuid.uuid4().hex[:8]}.svg"
    chart_path.write_text(
        render_chart_svg(option, chart_title),
        encoding="utf-8",
    )
    relative_file = f"charts/{chart_path.name}"
    print(
        json.dumps(
            {
                "success": True,
                "message": "图表已生成",
                "content": json.dumps(
                    {
                        "success": True,
                        "message": summary,
                        "file": str(chart_path),
                        "relative_file": relative_file,
                    },
                    ensure_ascii=False,
                ),
                "file_name": chart_path.name,
                "filepath": str(chart_path),
                "data": {
                    "title": chart_title,
                    "chart_type": chart_type,
                    "option": option,
                    "filepath": str(chart_path),
                    "relative_file": relative_file,
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
