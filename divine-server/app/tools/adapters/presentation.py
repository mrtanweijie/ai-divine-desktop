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
                    "editorial", "darktech", "pop", "keynote", "devconf",
                    "universal", "notion", "linear", "apple", "modern",
                    "academic", "travel", "roadmap", "minimal",
                ],
                "description": (
                    "PPT 风格；aurora 极光渐变（现代商务默认）、glass 玻璃拟态、"
                    "brutalist 新粗野撞色、swiss 瑞士极简、mesh 渐变弥散、"
                    "editorial 杂志衬线、darktech 暗黑科技、"
                    "pop 波普潮流（暖奶油底 + 高饱和圆斑 + 胶囊标签 + 三色下划条）、"
                    "keynote 发布会 Keynote（纯黑舞台 + 单一蓝强调 + 深灰圆角卡，"
                    "适合产品发布会/新品宣讲）、"
                    "devconf 开发者大会（纸白 + 近黑 + 发丝线 + 等宽字体，"
                    "适合技术宣讲/产品功能介绍）"
                ),
            },
            "theme_colors": {
                "type": "object",
                "description": (
                    "可选，主题色覆盖（所有主题生效）。只需传 {\"--color-primary\": "
                    "\"<颜色>\"}（颜色名或色值，如 红色/#E74C3C），"
                    "亮度按背景自动校正；强调色、图表主色、封面点缀随之替换"
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
                    "内容密度：每页要点 ≤5 条、每条 ≤2 行。"
                    "keynote（015 发布会）标准 8 页配方：①cover（brand/event/kicker/date/place）②section 愿景宣言 ③reveal 产品亮相（heading 用 '细体部分|粗体部分'，feature=定位语）④cards 特性三卡 ⑤kpi 性能数据 ⑥table/compare 对比 ⑦bullets 生态三卡（heading 含 '生态'）⑧pricing 价格三卡（points 每条 '档位|名称|配置|价格'，第 2 张自动蓝描边推荐）。"
                    "devconf（016 开发者大会）有标准页面配方，按序组织："
                    "①cover 封面（必须带 brand/event/kicker/date/place）；"
                    "②section 品牌使命宣言（整页深色反转，写 mission 一句话 + points 关键词 2-3 个）；"
                    "③kpi 品牌数据带（用户/活跃/增长/评分 4 项，'数值|标签' 格式，"
                    "subtitle 传一句话品牌背书长句）；"
                    "④overview 产品全景页（heading 含 '全景/架构/一张图看懂'，image=架构图 URL 时自动铺满占位框，body 可放架构图说明文字，"
                    "points 1 条 '本次大会聚焦：|模块说明' 作为底部聚焦行）；"
                    "普通 bullets 主题页不属于标准页序，会追加在收尾之前；"
                    "⑤cards 亮点功能总览（6 个，'功能名|一句话价值' + 关键参数）；"
                    "⑥two_col 亮点深潜 1-2 页（heading=核心主张，points=3 条 '要点|补充'，image=产品截图 URL；image_side 控制图左/图右——第 1 页默认图左，第 2 页默认图右镜像）；"
                    "⑦growth 用户增长页（左大数字：points 首条 '大数值|标签|涨跌'；右侧图表框：可选 chart={type:column, categories:[季], series:[{name, values}]} 画柱状，不传则图表/截图占位，chart_title 传图表标题）；"
                    "⑦.5 kpi_rows 增长指标页（heading=增长的背后是留存：points 前 3 条为 "
                    "'数值|标签|涨跌' KPI 如 '62%|次月留存率|+9pp YoY'，后 3 条为 '引擎名|描述' 增长引擎）；"
                    "⑧table 与竞品/上代对比（016 为 4 列对比表：columns=['能力维度',"
                    "'{{本品}}','{{竞品A}}','{{竞品B}}']，rows 每行['能力','✓ 我方优势','✕ 对方短板']；"
                    "给 compare 也可以，会自动转成对比表；第 2 列固定为本品（表头自动蓝底反白）；"
                    "subtitle 传对比口径注记）；"
                    "⑨bullets 三个选择理由。"
                    "kicker 只写纯文案（如 'Highlights'），渲染器自动加页序号前缀。"
                    "结尾页自动补齐为 CTA 版式（brand + heading 行动号召 + subtitle 官网/渠道 + body 联系方式）"
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "layout": {
                            "type": "string",
                            "enum": [
                                "bullets", "cards", "timeline", "columns",
                                "two_col", "compare", "kpi", "kpi_rows", "overview", "growth",
                                "reveal", "ecosystem", "pricing", "growth", "overview",
                                "quote", "table", "chart", "toc", "section",
                                "cover", "end", "default",
                            ],
                            "description": (
                                "版式：bullets 要点页（默认）；cards 卡片；"
                                "timeline 时间轴；columns 分栏；two_col 图文两栏；"
                                "compare 左右对比（需 left/right）；kpi 大数字；"
                                "kpi_rows 指标+列表组合页（devconf 增长指标页：points 前 3 条为 "
                                "'数值|标签|涨跌' KPI，其余为 '引擎名|描述' 增长引擎）；"
                                "quote 金句；table 表格（需 table）；chart 图表（需 chart）；"
                                "toc 目录；section 章节过渡页（keynote/devconf 下=整页深色品牌使命宣言：heading 写 mission 一句话、points 传 2-3 个品牌关键词）；cover 封面；end 结尾页。"
                                "keynote/devconf 主题建议第 2 页放一个 section 品牌使命页"
                                "（渲染为整页深色反转宣言，黑白呼吸节奏）。"
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
                        "items": {
                            "type": "array",
                            "description": (
                                "结构化条目（与 points 二选一，工具自动转换）："
                                "cards 用 {title, desc}；kpi 用 {value, label, desc}；"
                                "timeline 用 {date, title, desc}；columns 用 {title, points}"
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string", "description": "条目标题"},
                                    "name": {"type": "string", "description": "条目名称（等价 title）"},
                                    "desc": {"type": "string", "description": "条目说明"},
                                    "value": {"type": "string", "description": "(kpi) 数值，如 '295亿'"},
                                    "label": {"type": "string", "description": "(kpi) 指标名，如 'GMV'"},
                                    "delta": {"type": "string", "description": "(kpi) 同比/环比说明，如 '+173%'"},
                                    "date": {"type": "string", "description": "(timeline) 时间，如 '2021年'"},
                                    "points": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "(columns) 该栏要点",
                                    },
                                },
                            },
                        },
                        "quote": {
                            "type": "string",
                            "description": "(layout=quote) 金句正文（与 heading 二选一）",
                        },
                        "brand": {
                            "type": "string",
                            "description": "(layout=cover) 品牌名；keynote/devconf 封面品牌行",
                        },
                        "event": {
                            "type": "string",
                            "description": "(layout=cover) 活动/大会名，如 'DEVCONF 2026 · TRACK A'",
                        },
                        "kicker": {
                            "type": "string",
                            "description": "(layout=cover/内容页) 等宽眉题，如 'Product Keynote'/'Highlights'",
                        },
                        "date": {
                            "type": "string",
                            "description": "(layout=cover) 日期，如 '2026.09.28'",
                        },
                        "place": {
                            "type": "string",
                            "description": "(layout=cover) 地点/直播间",
                        },
                        "note": {
                            "type": "string",
                            "description": "演讲者备注，写入 PPT 备注页（不显示在正文）",
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
