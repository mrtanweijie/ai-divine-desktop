from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "word_document",
    "生成一份 Word 文档，用于周报、合同、会议纪要、报告等场景；"
    "sections 支持 heading/列表/表格/图片/代码块/引用等元素，"
    "markdown 参数可直接转换现成 Markdown 内容；"
    "theme 控制字体、标题装饰、行距和页边距，cover 生成封面页，toc 生成目录页",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "文档标题"},
            "theme": {
                "type": "string",
                "enum": [
                    "universal",
                    "notion",
                    "linear",
                    "apple",
                    "modern",
                    "academic",
                    "travel",
                    "roadmap",
                    "minimal",
                ],
                "description": "文档风格，默认 universal",
            },
            "path": {
                "type": "string",
                "description": "保存目录，workspace 内相对路径；默认保存到应用输出目录，不写入项目",
            },
            "cover": {
                "type": "boolean",
                "description": "正式文档生成独立封面页（标题/副标题/日期），默认 false",
                "default": False,
            },
            "toc": {
                "type": "boolean",
                "description": "生成目录页（打开文档后需更新域），默认 false",
                "default": False,
            },
            "markdown": {
                "type": "string",
                "description": (
                    "现成 Markdown 全文，与 sections 二选一，优先使用；"
                    "标题/列表/表格/代码块/引用/图片/行内格式都会转换"
                ),
            },
            "sections": {
                "type": "array",
                "description": "文档章节，按 type 指定元素类型，不传 type 时为正文段落",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": [
                                "heading",
                                "paragraph",
                                "bullet_list",
                                "numbered_list",
                                "table",
                                "quote",
                                "code_block",
                                "image",
                                "page_break",
                                "toc",
                            ],
                            "description": "元素类型；heading 支持 h1/h2/h3 别名",
                        },
                        "heading": {"type": "string", "description": "段落小标题"},
                        "body": {
                            "type": "string",
                            "description": "正文；支持 **加粗**、`代码`、[文字](链接) 及逐行 markdown 块级语法",
                        },
                        "items": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "列表条目（bullet_list / numbered_list）",
                        },
                        "headers": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "表格表头（table）",
                        },
                        "rows": {
                            "type": "array",
                            "items": {"type": "array", "items": {"type": "string"}},
                            "description": "表格数据行（table）",
                        },
                        "src": {
                            "type": "string",
                            "description": "图片路径或 URL（image）",
                        },
                        "caption": {"type": "string", "description": "表格/图片说明文字"},
                        "level": {
                            "type": "integer",
                            "description": "标题级别 1-3（heading）",
                        },
                    },
                },
            },
        },
        "required": ["title"],
    },
)
class WordDocumentAdapter(ToolAdapter):
    script_name = "word_document.py"
    category = "documents"
    timeout = 60

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": str(arguments.get("title") or "未命名文档"),
            "theme": str(arguments.get("theme") or arguments.get("style") or "universal").strip(),
            "sections": arguments.get("sections") or [],
            "markdown": str(arguments.get("markdown") or ""),
            "cover": bool(arguments.get("cover")),
            "toc": bool(arguments.get("toc")),
            "path": str(arguments.get("path") or ""),
        }
