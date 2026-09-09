from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "generate_chart",
    "根据分析结果生成 ECharts 图表配置；当用户要求画图、展示趋势/对比/占比/分布等图表时使用。"
    "option 必须是完整合法的 ECharts option 且包含非空 series 数组，不要在正文输出 HTML、JS 或图表代码。"
    "多系列柱状图不要设 barWidth（宽度交给布局自动分配）；柱状图不要用对数轴"
    "（ECharts 柱子在 log 轴上以 value=1 为基准生长，数值跨 1 或全 <1 时图形错误，"
    "跨数量级数据保持线性轴靠数值标签呈现）；折线/散点需要对数轴时设轴 type:\"log\""
    "（logBase 仅对 log 轴生效）。"
    "配色遵循统一科研主题，不要给系列/扇区逐一手写颜色，分类系列颜色交给主题定性色板自动分配；"
    "确需语义色时用固定值：上涨/盈利/正 #DD656D，下跌/亏损/负 #2F9E6E（A股涨红跌绿），"
    "成功 #2F9E6E、警告 #F3962F、错误 #DD656D、信息 #036EAD、中性 #8A94A6；"
    "图例位置交给主题排版，不要设置 legend 的 left/top/right/bottom/orient"
    "（ECharts 组件互不避让，硬编码图例位置会与标题重叠）；"
    "饼图/环图也不要写 series.center 和 title 的 left/top（环心与标题位置交给主题排版，"
    "环心写 49%~50% 会让顶部外置标签压住副标题）；"
    "热力图或连续数值映射用 visualMap.inRange 的连续色带"
    "（#506AAA→#728DC1→#91BBDF→#B6DBF1→#F6D3D9→#E79FBF→#E17692），不要把热力色逐个硬编码进数据点。"
    "坐标轴保持极简：X 类目轴只留 1px 基线、不要刻度；Y 数值轴隐藏轴线与刻度、只留约 4 条实线水平网格线"
    "（splitNumber: 4）；网格线不要用 dashed；不要写 backgroundColor（画布透明随主题）。"
    "标题分级：主标题讲结论（建议不超过 15 字），时间范围/单位/数据来源等口径放 title.subtext。"
    "数据缺失的类目用 null 占位（折线自动跨空值连线），不要编造数值或补 0。"
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
