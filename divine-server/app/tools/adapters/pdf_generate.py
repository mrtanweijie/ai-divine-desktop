from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "pdf_generate",
    "统一 PDF 生成入口：按需求选择 Report/Business/Travel/Roadmap/Book/Slide 配方并渲染。"
    "商业分析报告（kind=business）围绕价值主张、数字化成本结构、私域联名增长策略、"
    "品牌竞争壁垒四大维度推导，自动整理行业对标表格与品牌经营核心数据；"
    "简历场景用 resume_data 传结构化 JSON；prompt 传需求；本工具只输出 PDF，"
    "简历的可编辑 HTML 版请用 html_resume 工具；"
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
                "enum": ["universal", "resume", "creative", "minimal", "boss_zhipin", "finance", "linkedin", "kami", "kami_white", "modern", "academic", "travel", "travel_mag", "roadmap", "notion", "linear", "apple", "tpl_professional", "tpl_modern", "tpl_minimal", "tpl_academic", "tpl_executive", "tpl_creative", "tpl_product", "tpl_data", "tpl_freshgrad", "tpl_lateral", "tpl_compact", "tpl_global"],
                "description": "简历/PDF 主题 ID（简历为统一模板库 19 套，与 html_resume 同一套）；简历场景推荐 tpl_* 12 套精品模板，creative/minimal/boss_zhipin/finance/linkedin/kami/kami_white 为经典风格；不传时系统按 prompt 场景自动选择（travel_mag 为杂志版旅行手册）",
            },
            "resume_layout": {
                "type": "string",
                "enum": ["single", "multi"],
                "description": "简历页数布局，默认 single（单页）；内容较多或用户要求 2-3 页时传 multi（自动加断页保护）。仅影响 PDF；可编辑 HTML 版用 html_resume 工具（其也有 layout 参数）",
            },
            "color_scheme": {
                "type": "string",
                "description": (
                    "配色方案：经典 blue/green/warm/monochrome/purple，"
                    "或旅行杂志预设 teal/iceblue/desert/vintage/midnight/pureblack/"
                    "mistsage/mistblue/duskmauve/lotuspink/dunesand/smokegray；"
                    "也支持直接传颜色（如 红色/#E74C3C/rgb(...)/石墨墨黑）自动派生整套配色；"
                    "简历场景同样生效（把主色应用到所选模板的头部/标题/强调色，"
                    "PDF 与 html_resume 输出一致）；"
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
                "description": (
                    "简历结构化数据（仅输出 PDF；可编辑 HTML 版用 html_resume 工具），"
                    "推荐结构：name/title/contact/summary/experiences/projects/education/skills。"
                    "内容结构规则（按所选模板产出不同板块，勿让所有模板套同一份内容）："
                    "experiences 只放各段岗位职责与成果要点，不要在经历里内嵌项目；"
                    "独立项目放顶层 projects 数组（可选，无项目时整个\"项目\"板块不出现）；"
                    "若源数据把项目挂在某段 work.projects 下也会自动并入独立的\"项目\"板块呈现。"
                    "模板侧重差异：高管 tpl_executive 需 scale/metrics/public_work；"
                    "学术 tpl_academic 用 publications；数据 tpl_data 量化 impact；"
                    "跨界 tpl_lateral 用 transferable/pivot；创意 tpl_creative 用 works/skill_groups；"
                    "应届 tpl_freshgrad 突出课程/竞赛/校园亮点；国际 tpl_global 补 en_* 双语；"
                    "金融 tpl_professional/科技 tpl_modern/工程 tpl_minimal/产品 tpl_product "
                    "以经历+项目为主。扩展字段：certifications/languages/honors（字符串数组）、"
                    "publications（title/venue/year/tags）、works（name/role/year/description/result）、"
                    "transferable（source/ability/description/mapping）、pivot（转型定位一句话）、"
                    "en_*（双语字段）、Education.gpa/courses"
                ),
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
            "resume_layout": str(arguments.get("resume_layout") or "").strip(),
        }
        # cover/toc 仅在显式传入时透传（False 表示用户明确不要）；
        # 未传时由引擎设计层按场景自动决定（如季度汇报默认封面+目录）。
        if "cover" in arguments:
            params["cover"] = bool(arguments.get("cover"))
        if "toc" in arguments:
            params["toc"] = bool(arguments.get("toc"))
        return params
