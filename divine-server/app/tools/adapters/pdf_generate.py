from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "pdf_generate",
    "统一 PDF 生成入口：按需求选择 Report/Travel/Roadmap/Book/Slide 配方并渲染。"
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
                "enum": ["report", "travel", "roadmap", "book", "slide", "resume"],
                "description": "文档配方；不传时自动识别",
            },
            "style": {
                "type": "string",
                "enum": ["modern", "academic", "corporate", "minimal", "playful"],
                "description": "排版风格",
            },
            "theme": {
                "type": "string",
                "enum": ["universal", "resume", "professional", "creative", "minimal", "boss_zhipin", "finance", "linkedin", "kami", "kami_white", "modern", "academic", "travel", "travel_mag", "roadmap", "notion", "linear", "apple"],
                "description": "主题 ID，优先于 style；不传时系统按 prompt 场景自动选择（travel_mag 为杂志版旅行手册）",
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
                "description": "简历结构化数据，推荐一页简历结构：name/target/contact/summary/core_skills/work/projects/education；kind=resume 时优先使用此数据渲染，不再走 LLM 生成",
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
        }
        # cover/toc 仅在显式传入时透传（False 表示用户明确不要）；
        # 未传时由引擎设计层按场景自动决定（如季度汇报默认封面+目录）。
        if "cover" in arguments:
            params["cover"] = bool(arguments.get("cover"))
        if "toc" in arguments:
            params["toc"] = bool(arguments.get("toc"))
        return params
