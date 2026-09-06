from __future__ import annotations

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "pdf_form_generate",
    "生成带 AcroForm 真控件的**可填写**表单 PDF，三种模式任选："
    "① template_id 实例化内置模板（application 事项申请/registration 信息登记/survey 调查问卷/expense 费用报销）+ values 预填；"
    "② html 传遵循字段协议（data-field/data-type/data-label）的自定义表单 HTML；"
    "③ sections 声明式字段清单（兼容旧用法）。"
    "产物可被 pdf_form_fields 读取、pdf_form_fill 填写；支持 theme 换肤（minimal/corporate/tech/forest）与自定义主题色。"
    "只要静态表单观感（不需要真控件）时用 pdf_generate 即可。扫描件不在支持范围。"
    "**场景选型指引（重要）**：费用报销/发票/明细列表类表单 → 用 expense 模板（含明细表+金额合计，"
    "不要把明细行拆成 item1_xxx/item2_xxx 平铺字段）；请假/采购/用车/审批申请 → application 模板；"
    "员工信息/入职登记 → registration 模板；调查/问卷 → survey 模板。"
    "只有内置模板覆盖不了的定制表单才用 html/sections 自拼。",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "表单标题（同时作为默认文件名）"},
            "template_id": {
                "type": "string",
                "enum": ["application", "registration", "survey", "expense"],
                "description": "内置模板：application 事项申请/registration 信息登记/survey 调查/expense 费用报销",
            },
            "values": {
                "type": "object",
                "additionalProperties": {"type": "string"},
                "description": '字段预填值 {"applicant_name": "李铭"}；单选/下拉的值需为选项之一',
            },
            "theme": {
                "type": "string",
                "enum": ["minimal", "corporate", "tech", "forest"],
                "description": "主题换肤，默认 minimal",
            },
            "color_scheme": {
                "type": "string",
                "description": "自定义主题色：色名（黑色/石墨墨黑/藏青…）或 #十六进制，自动派生整套",
            },
            "theme_colors": {
                "type": "object",
                "additionalProperties": {"type": "string"},
                "description": '变量级主题覆盖，如 {"--color-primary": "#1A1A1A", "--color-accent": "#C9A227"}',
            },
            "html": {
                "type": "string",
                "description": "自定义表单 HTML（遵循字段协议：可填写单元带 data-field/data-type/data-label；可链接 forms.css）",
            },
            "file_name": {
                "type": "string",
                "description": "输出文件名（不含 .pdf），默认用标题",
            },
            "sections": {
                "type": "array",
                "description": "表单分节，按顺序渲染；空间不足自动分页。文本类字段默认整行，可给 half:true 让两字段并排半行",
                "items": {
                    "type": "object",
                    "properties": {
                        "heading": {"type": "string", "description": "分节标题"},
                        "description": {"type": "string", "description": "分节说明（可选）"},
                        "fields": {
                            "type": "array",
                            "description": "字段清单，按行渲染",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {
                                        "type": "string",
                                        "description": "字段名（填写时引用，全文档唯一），如 name/phone/agree",
                                    },
                                    "label": {"type": "string", "description": "页面上的字段标签"},
                                    "type": {
                                        "type": "string",
                                        "enum": [
                                            "text", "multiline", "checkbox", "radio",
                                            "select", "date", "number", "money",
                                        ],
                                        "description": "控件类型：单行文本/多行文本/复选/单选组/下拉/日期/数字/金额",
                                    },
                                    "options": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "(radio/select 必填) 选项数组",
                                    },
                                    "default": {
                                        "description": "默认值：text 为字符串，checkbox 为布尔，radio/select 为选项",
                                    },
                                    "required": {"type": "boolean", "description": "是否必填，默认 false"},
                                    "half": {"type": "boolean", "description": "true 时该字段只占半行（与相邻 half 字段并排）"},
                                },
                                "required": ["name", "label", "type"],
                            },
                        },
                    },
                    "required": ["fields"],
                },
            },
        },
        "required": ["title"],
    },
)
class PdfFormGenerateAdapter(ToolAdapter):
    script_name = "pdf_form_generate.py"
    category = "pdf"
    timeout = 120

    def build_params(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": str(arguments.get("title") or ""),
            "file_name": str(arguments.get("file_name") or ""),
            "template_id": str(arguments.get("template_id") or ""),
            "html": str(arguments.get("html") or ""),
            "sections": arguments.get("sections") or [],
            "values": arguments.get("values") if isinstance(arguments.get("values"), dict) else {},
            "theme": str(arguments.get("theme") or ""),
            "color_scheme": str(arguments.get("color_scheme") or ""),
            "theme_colors": arguments.get("theme_colors") if isinstance(arguments.get("theme_colors"), dict) else {},
        }


