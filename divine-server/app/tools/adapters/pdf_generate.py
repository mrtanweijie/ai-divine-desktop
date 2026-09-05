from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "pdf_generate",
    "统一 PDF 生成入口：按需求选择 Report/Business/Travel/Roadmap/Book/Slide 配方并渲染。"
    "商业分析报告（kind=business）围绕价值主张、数字化成本结构、私域联名增长策略、"
    "品牌竞争壁垒四大维度推导，自动整理行业对标表格与品牌经营核心数据；"
    "简历场景用 resume_data 传结构化 JSON；prompt 传需求；"
    "kind/style/theme/color_scheme 均可省略（系统按场景自动识别 + LLM 设计师决策，用户风格词优先）；"
    "默认保存到应用输出目录 pdf，指定项目内目录时传 path。",
    {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "用户对 PDF 文档的需求描述"},
            "markdown": {
                "type": "string",
                "description": (
                    "可选，完整 Markdown 正文；传入后直接按该内容渲染 PDF，"
                    "可使用 ![图表标题](图表文件路径) 嵌入之前生成的图表"
                ),
            },
            "kind": {
                "type": "string",
                "enum": ["report", "business", "travel", "roadmap", "book", "slide", "resume"],
                "description": "文档配方；business 为商业分析报告（价值主张/数字化成本结构/私域联名增长策略/品牌竞争壁垒四大维度）；不传时自动识别",
            },
            "style": {
                "type": "string",
                "enum": ["modern", "academic", "corporate", "minimal", "playful"],
                "description": "排版风格",
            },
            "theme": {
                "type": "string",
                "enum": ["universal", "resume", "professional", "creative", "minimal", "boss_zhipin", "finance", "linkedin", "kami", "kami_white", "modern", "academic", "travel", "travel_mag", "roadmap", "notion", "linear", "apple", "tpl_professional", "tpl_modern", "tpl_minimal", "tpl_academic", "tpl_executive", "tpl_creative", "tpl_product", "tpl_data", "tpl_freshgrad", "tpl_lateral", "tpl_compact", "tpl_global"],
                "description": "主题 ID，优先于 style；tpl_* 为 12 套精品简历模板库（tpl_professional 金融咨询经典/tpl_modern 互联网科技/tpl_minimal 资深工程师极简/tpl_academic 学术科研/tpl_executive 高管/tpl_creative 设计师作品/tpl_product 产品经理/tpl_data 数据算法/tpl_freshgrad 应届校招/tpl_lateral 跨界转型/tpl_compact 市场运营双栏/tpl_global 中英双语），简历场景推荐优先使用；不传时系统按 prompt 场景自动选择（travel_mag 为杂志版旅行手册）",
            },
            "output_format": {
                "type": "string",
                "enum": ["pdf", "html", "both"],
                "description": "输出格式，默认 pdf；简历场景选 html/both 时额外生成可编辑 HTML（浏览器打开即可点击修改内容，也可 ⌘P 导出 PDF）与纯净投递版 HTML",
            },
            "resume_layout": {
                "type": "string",
                "enum": ["single", "multi"],
                "description": "简历页数布局，默认 single（单页）；内容较多或用户要求 2-3 页时传 multi（自动加断页保护）",
            },
            "color_scheme": {
                "type": "string",
                "description": (
                    "配色方案：经典 blue/green/warm/monochrome/purple，"
                    "或旅行杂志预设 teal/iceblue/desert/vintage/midnight/pureblack/"
                    "mistsage/mistblue/duskmauve/lotuspink/dunesand/smokegray；"
                    "也支持直接传颜色（如 红色/#E74C3C/rgb(...)）自动派生整套配色；"
                    "不传时系统按 prompt 场景自动选择"
                ),
            },
            "theme_colors": {
                "type": "object",
                "description": (
                    "可选，自定义主题色（对所有主题生效）。只需传 --color-primary"
                    "（颜色名或色值，如红色/#E74C3C/rgb(...)）即可自动派生整套配色；"
                    "也可显式覆盖 --primary/--accent/--primary-light 等变量"
                    "（旅行主题对应 --color-accent/--bg-highlight/--bg-cover）"
                ),
            },
            "paper_size": {
                "type": "string",
                "enum": ["A4", "Letter", "Legal"],
                "description": "纸张大小，默认 A4",
            },
            "cover": {
                "type": "boolean",
                "description": "是否生成封面页；未传时系统按场景自动决定（季度汇报/客户提案/行业洞察/作品集默认生成，周报/PRD 默认不生成）；travel 主题固定生成封面",
            },
            "cover_style": {
                "type": "string",
                "enum": ["left-aligned", "centered", "split", "minimal", "hero-graphic", "terminal"],
                "description": "封面布局风格：left-aligned/centered/split/minimal/hero-graphic 等",
            },
            "toc": {
                "type": "boolean",
                "description": "是否生成目录；未传时系统按场景自动决定（季度汇报/客户提案/行业洞察/PRD 默认生成）；travel 主题固定不生成",
            },
            "images": {
                "type": "boolean",
                "description": (
                    "是否为文档配图（下载内嵌网络图片）。默认 false。"
                    "开启后旅行手册自动为景点配图，其他文档由 LLM 在合适位置插入配图"
                    "（真实 URL 或按关键词取图），失败自动降级为占位块"
                ),
            },
            "file_name": {
                "type": "string",
                "description": "可选，PDF 文件名；默认由 prompt 生成",
            },
            "resume_data": {
                "type": "object",
                "description": "简历结构化数据，推荐一页简历结构：name/target/contact/summary/core_skills/work/projects/education；kind=resume 时优先使用此数据渲染，不再走 LLM 生成。模板库扩展字段：certifications/languages/honors（字符串数组）、publications（论文 title/venue/year/tags）、works（作品 name/role/year/description/result）、transferable（转型 source/ability/description/mapping）、pivot（转型定位一句话）、en_*（双语字段）、Education.gpa/courses",
            },
            "path": {
                "type": "string",
                "description": "保存目录，workspace 内相对路径；默认保存到应用输出目录 pdf",
            },
        },
        "required": ["prompt"],
    },
)
class PdfGenerateAdapter(ToolAdapter):
    script_name = "pdf_generate.py"
    category = "pdf"
    timeout = 300

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        params = {
            "prompt": str(arguments.get("prompt") or "").strip(),
            "kind": str(arguments.get("kind") or "").strip(),
            "style": str(arguments.get("style") or "").strip(),
            "theme": str(arguments.get("theme") or "").strip(),
            "color_scheme": str(arguments.get("color_scheme") or "").strip(),
            "theme_colors": arguments.get("theme_colors") or {},
            "paper_size": str(arguments.get("paper_size") or "A4").strip(),
            "file_name": str(arguments.get("file_name") or "").strip(),
            "resume_data": arguments.get("resume_data") or {},
            "path": str(arguments.get("path") or "").strip(),
            "markdown": str(arguments.get("markdown") or "").strip(),
            "cover_style": str(arguments.get("cover_style") or "").strip(),
            "output_format": str(arguments.get("output_format") or "").strip(),
            "resume_layout": str(arguments.get("resume_layout") or "").strip(),
        }
        # cover/toc 仅在显式传入时透传（False 表示用户明确不要）；
        # 未传时由引擎设计层按场景自动决定（如季度汇报默认封面+目录）。
        if "cover" in arguments:
            params["cover"] = bool(arguments.get("cover"))
        if "toc" in arguments:
            params["toc"] = bool(arguments.get("toc"))
        return params
