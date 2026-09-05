from __future__ import annotations

from typing import Any

from ..base import ToolAdapter
from ..registry import register_tool


@register_tool(
    "html_resume",
    "简历的可编辑 HTML 输出（职责单一，不产出 PDF）：按统一模板库 19 套模板渲染，"
    "产出可编辑 HTML（浏览器打开点击任意文字即可改，工具条可下载/打印导出 PDF）"
    "与纯净投递版 HTML。PDF 版请用 pdf_generate。"
    "先按简历规则整理 resume_data 再调用；template 按职业/场景选："
    "应届校招 tpl_freshgrad、高管 tpl_executive、产品 tpl_product、数据/算法 tpl_data、"
    "设计师 tpl_creative、转型 tpl_lateral、市场运营 tpl_compact、金融咨询 tpl_professional、"
    "互联网科技 tpl_modern、资深工程师 tpl_minimal、学术科研 tpl_academic、中英双语 tpl_global、"
    "招聘平台海投 boss_zhipin、银行证券 finance、LinkedIn 海外 linkedin、"
    "内容向两页 kami/kami_white、留白单栏 minimal、创意卡片 creative。",
    {
        "type": "object",
        "properties": {
            "resume_data": {
                "type": "object",
                "description": (
                    "简历结构化数据：name/title/contact/summary/experiences/projects/education/skills。"
                    "内容结构规则（按所选模板产出不同板块，勿所有模板套同一份内容）："
                    "experiences 只放各段岗位职责与成果要点，不要内嵌项目；"
                    "独立项目放顶层 projects 数组（可选，无项目时整个\"项目\"板块不出现）；"
                    "源数据若把项目挂在某段 work.projects 下也会自动并入独立\"项目\"板块呈现。"
                    "模板侧重差异：高管 tpl_executive 用 scale/metrics/public_work；学术 tpl_academic "
                    "用 publications；数据 tpl_data 量化 impact；跨界 tpl_lateral 用 transferable/pivot；"
                    "创意 tpl_creative 用 works/skill_groups；应届 tpl_freshgrad 突出课程/竞赛/校园亮点；"
                    "国际 tpl_global 补 en_* 双语。扩展字段：certifications/languages/honors"
                    "（字符串数组）、publications（title/venue/year/tags）、works（作品 name/role/year/"
                    "description/result）、transferable（source/ability/description/mapping）、"
                    "pivot（转型定位）、en_*（双语）、Education.gpa/courses"
                ),
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
                    "creative",
                    "minimal",
                    "boss_zhipin",
                    "finance",
                    "linkedin",
                    "kami",
                    "kami_white",
                ],
                "description": "简历模板 ID（统一模板库 19 套），未传时默认 tpl_professional",
            },
            "layout": {
                "type": "string",
                "enum": ["single", "multi"],
                "description": "页数布局，默认 single（单页）；内容多或用户要 2-3 页时传 multi",
            },
            "color_scheme": {
                "type": "string",
                "description": (
                    "换主色：支持中文色名（如 石墨墨黑/藏青/酒红/红色…）、#hex、"
                    "rgb(...)，或两者混合（石墨墨黑 #2B2B2B）。自动按主色派生整套配色，"
                    "PDF 与 HTML 同参同效果；不传时用模板默认配色"
                ),
            },
            "color_overrides": {
                "type": "object",
                "description": (
                    "可选，CSS 变量级直接换色，如 {'--navy': '#2B2B2B'}，"
                    "优先级高于 color_scheme 派生值；仅高级调用使用"
                ),
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
            "color_scheme": str(arguments.get("color_scheme") or "").strip(),
            "color_overrides": arguments.get("color_overrides") or None,
            "file_name": str(arguments.get("file_name") or "").strip(),
            "path": str(arguments.get("path") or "").strip(),
        }
