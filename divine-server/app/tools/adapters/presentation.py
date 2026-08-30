from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "presentation",
    "生成 PPT 幻灯片演示文稿，用于汇报、培训、产品介绍等场景；"
    "theme 控制配色与字体；支持 14 种版式（封面/目录/章节页/图文两栏/卡片/"
    "时间轴/分栏/对比/大数字/金句/表格/图表/要点/结尾），"
    "简单图表（柱状/折线/饼/环/面积）由内置原生图表直绘（PowerPoint 内可编辑），"
    "复杂图表请先用 generate_chart 生成 SVG 再以 image.path 引用",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "演示文稿标题"},
            "theme": {
                "type": "string",
                "enum": [
                    "aurora", "glass", "brutalist", "swiss", "mesh",
                    "editorial", "darktech",
                    "universal", "notion", "linear", "apple", "modern",
                    "academic", "travel", "roadmap", "minimal",
                ],
                "description": (
                    "PPT 风格；aurora 极光渐变（现代商务默认）、glass 玻璃拟态、"
                    "brutalist 新粗野撞色、swiss 瑞士极简、mesh 渐变弥散、"
                    "editorial 杂志衬线、darktech 暗黑科技"
                ),
            },
            "path": {
                "type": "string",
                "description": "保存目录，workspace 内相对路径；默认保存到应用输出目录，不写入项目",
            },
            "toc": {
                "type": "boolean",
                "description": (
                    "是否生成目录页；不传时自动判断（≥2 个章节页且内容 ≥5 页时自动插入，"
                    "条目按章节页推导并带页码）"
                ),
            },
            "slides": {
                "type": "array",
                "description": (
                    "幻灯片列表；结尾页通常无需传入（自动补齐）。"
                    "内容密度：每页要点 ≤5 条、每条 ≤2 行"
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "layout": {
                            "type": "string",
                            "enum": [
                                "bullets", "cards", "timeline", "columns",
                                "two_col", "compare", "kpi", "quote",
                                "table", "chart", "toc", "section",
                                "cover", "end", "default",
                            ],
                            "description": (
                                "版式：bullets 要点页（默认）；cards 卡片；"
                                "timeline 时间轴；columns 分栏；two_col 图文两栏；"
                                "compare 左右对比（需 left/right）；kpi 大数字；"
                                "quote 金句；table 表格（需 table）；chart 图表（需 chart）；"
                                "toc 目录；section 章节过渡页；cover 封面；end 结尾页。"
                                "不传时按标题与要点数自动推断"
                            ),
                        },
                        "heading": {"type": "string", "description": "幻灯片标题"},
                        "title": {"type": "string", "description": "幻灯片标题（等价 heading）"},
                        "subtitle": {
                            "type": "string",
                            "description": "副标题（封面/章节页/结尾页/金句出处）",
                        },
                        "body": {
                            "type": "string",
                            "description": "正文内容，换行分隔多个要点",
                        },
                        "content": {"type": "string", "description": "正文内容（等价 body）"},
                        "points": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "要点列表；卡片/时间轴条目可用 '标题|描述' 结构；"
                                "kpi 条目用 '数值|标签|说明'"
                            ),
                        },
                        "chart": {
                            "type": "object",
                            "description": (
                                "简单图表数据（layout=chart 时必填）；"
                                "类型限 bar/column/line/pie/doughnut/area，"
                                "系列 ≤3、数据点 ≤12，超出请改用 generate_chart"
                            ),
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": ["bar", "column", "line", "pie",
                                             "doughnut", "area"],
                                    "description": "图表类型",
                                },
                                "title": {"type": "string", "description": "图表标题（可选）"},
                                "categories": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "类目轴标签",
                                },
                                "series": {
                                    "type": "array",
                                    "description": "数据系列",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "values": {
                                                "type": "array",
                                                "items": {"type": "number"},
                                            },
                                        },
                                        "required": ["name", "values"],
                                    },
                                },
                            },
                            "required": ["type", "categories", "series"],
                        },
                        "table": {
                            "type": "object",
                            "description": "表格数据（layout=table 时必填）",
                            "properties": {
                                "columns": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "列头",
                                },
                                "rows": {
                                    "type": "array",
                                    "items": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "description": "数据行",
                                },
                            },
                            "required": ["columns", "rows"],
                        },
                        "image": {
                            "type": "object",
                            "description": (
                                "配图（two_col 图文两栏使用；chart/table 可用 caption 标注来源）。"
                                "path 为 workspace 内图片路径（png/jpg/svg）；"
                                "无图时自动渲染主题化占位块，后续可由 image_generate 补图"
                            ),
                            "properties": {
                                "path": {"type": "string", "description": "图片路径"},
                                "caption": {"type": "string", "description": "图注/数据来源"},
                                "position": {
                                    "type": "string",
                                    "enum": ["left", "right"],
                                    "description": "图片位置，默认 left",
                                },
                            },
                        },
                        "left": {
                            "type": "object",
                            "description": "对比页左块（layout=compare 时必填）",
                            "properties": {
                                "title": {"type": "string"},
                                "points": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                        "right": {
                            "type": "object",
                            "description": "对比页右块（layout=compare 时必填）",
                            "properties": {
                                "title": {"type": "string"},
                                "points": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                    },
                },
            },
        },
        "required": ["title", "slides"],
    },
)
class PresentationAdapter(ToolAdapter):
    script_name = "presentation.py"
    category = "presentations"
    timeout = 60

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        toc = arguments.get("toc")
        return {
            "title": str(arguments.get("title") or "未命名演示文稿"),
            "theme": str(arguments.get("theme") or arguments.get("style") or "universal").strip(),
            "slides": arguments.get("slides") or [],
            "path": str(arguments.get("path") or ""),
            "toc": None if toc is None else bool(toc),
        }
