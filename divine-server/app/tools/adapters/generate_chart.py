from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "generate_chart",
    "根据分析结果生成 ECharts 图表配置；当用户要求画图、展示趋势/对比/占比/分布等图表时使用。"
    "option 必须是完整合法的 ECharts option 且包含非空 series 数组，不要在正文输出 HTML、JS 或图表代码。"
    "默认只返回 option 由前端内联渲染，不生成 SVG 文件；"
    "只有用户明确要求导出 SVG 或需要嵌入 PDF 时才传 export_svg=true。",
    {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "图表标题，可选；未传时读取 option.title.text",
            },
            "option": {
                "type": "object",
                "description": (
                    "完整 ECharts option，series 必须存在且非空；series.type 仅限 "
                    "line/bar/pie/scatter/radar/funnel/gauge/heatmap/boxplot/candlestick/"
                    "sankey/sunburst/treemap/graph/tree/parallel/effectScatter/pictorialBar/"
                    "themeRiver/custom 之一"
                ),
            },
            "export_svg": {
                "type": "boolean",
                "description": (
                    "是否生成 SVG 文件；默认 false 只返回 option 由前端内联渲染；"
                    "用户明确要求导出/保存 SVG 或需要嵌入 PDF 时传 true"
                ),
                "default": False,
            },
        },
        "required": ["option"],
    },
)
class GenerateChartAdapter(ToolAdapter):
    script_name = "generate_chart.py"
    category = "charts"
    timeout = 10

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        option = arguments.get("option")
        return {
            "title": str(arguments.get("title") or "").strip(),
            "option": option if isinstance(option, dict) else {},
            "export_svg": bool(arguments.get("export_svg")),
        }
