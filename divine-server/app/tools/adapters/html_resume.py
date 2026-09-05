from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "html_resume",
    "简历的可编辑 HTML 输出（职责单一，不产出 PDF）：按 12 套简历模板渲染，"
    "产出可编辑 HTML（浏览器打开点击任意文字即可改，工具条可下载/打印导出 PDF）"
    "与纯净投递版 HTML。PDF 版请用 pdf_generate。"
    "先按简历规则整理 resume_data 再调用；template 按职业/场景选："
    "应届校招 tpl_freshgrad、高管 tpl_executive、产品 tpl_product、数据/算法 tpl_data、"
    "设计师 tpl_creative、转型 tpl_lateral、市场运营 tpl_compact、金融咨询 tpl_professional、"
    "互联网科技 tpl_modern、资深工程师 tpl_minimal、学术科研 tpl_academic、中英双语 tpl_global。",
    {
        "type": "object",
        "properties": {
            "resume_data": {
                "type": "object",
                "description": "简历结构化数据：name/target/contact/summary/metrics/skills/work/education/highlights 等；模板库扩展字段 certifications/languages/honors/publications/works/transferable/pivot/en_* 按需",
            },
            "template": {
                "type": "string",
                "enum": [
                    "tpl_professional",
                    "tpl_modern",
                    "tpl_minimal",
                    "tpl_academic",
                    "tpl_executive",
                    "tpl_creative",
                    "tpl_product",
                    "tpl_data",
                    "tpl_freshgrad",
                    "tpl_lateral",
                    "tpl_compact",
                    "tpl_global",
                ],
                "description": "简历模板 ID，未传时默认 tpl_professional",
            },
            "layout": {
                "type": "string",
                "enum": ["single", "multi"],
                "description": "页数布局，默认 single（单页）；内容多或用户要 2-3 页时传 multi",
            },
            "file_name": {
                "type": "string",
                "description": "可选，输出文件名（默认「姓名简历」）",
            },
            "path": {
                "type": "string",
                "description": "保存目录，workspace 内相对路径；默认保存到应用输出目录 html 类别",
            },
        },
        "required": ["resume_data"],
    },
)
class HtmlResumeAdapter(ToolAdapter):
    script_name = "html_resume.py"
    category = "html"
    timeout = 60

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "resume_data": arguments.get("resume_data") or {},
            "template": str(arguments.get("template") or "").strip(),
            "layout": str(arguments.get("layout") or "single").strip(),
            "file_name": str(arguments.get("file_name") or "").strip(),
            "path": str(arguments.get("path") or "").strip(),
        }
