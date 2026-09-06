"""pdf_form_generate 脚本：基于 docs/pdf-forms HTML 模板库生成可填写的表单 PDF。

三种模式（docs/design/018-pdf-form-html-templates-20260906.md）：
- template_id：实例化内置模板（application/registration/survey/expense）+ values 预填；
- html：模型按字段协议（data-field/data-type/data-label）自由拼装的 HTML；
- sections：v1 声明式字段清单（编译为 HTML，兼容保留）。

管线（docgen/pdf/form_html.py）：协议标记 → WeasyPrint 渲染 → pymupdf 在
链接注解槽位放置 AcroForm 真控件。产物可被 pdf_form_fields 读取、
pdf_form_fill 填写。
"""

from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.docgen.pdf.form_html import (  # noqa: E402
    form_templates_dir,
    load_template,
    place_widgets,
    prepare_html,
    render_pdf,
    set_theme,
    theme_override_css,
    validate_schema,
    verify_form,
)
from app.tools.scripts.file_utils import unique_output_path  # noqa: E402


def _compose_sections_html(sections: list[dict], title: str) -> str:
    """把字段清单编译为协议 HTML——对齐 04-expense 的正式骨架。"""

    def _field_html(field: dict) -> str:
        name = escape(str(field.get("name") or ""))
        if not name:
            return ""
        label = escape(str(field.get("label") or name))
        ftype = str(field.get("type") or "text").strip().lower()
        # sections 用户层类型 → 协议 HTML data-type 归一：
        # dropdown→select、multiline→textarea（协议类型名与控件元素一致）
        ftype = {"dropdown": "select", "multiline": "textarea"}.get(ftype, ftype)
        default = field.get("default")
        req = "true" if field.get("required") else "false"
        req_star = '<i class="req">*</i>' if field.get("required") else ""
        # half:true → col-6 半行；默认整行 col-12（field-grid 自动让相邻 half 并排）
        span = "col-6" if field.get("half") else "col-12"
        open_field = (
            f'<div class="field {span}" data-field="{name}" data-type="{ftype}"'
            f' data-label="{label}" data-required="{req}">'
            f'<div class="field-label">{label}{req_star}</div>'
        )

        if ftype == "checkbox":
            checked = ' data-checked="true"' if default else ""
            return (
                open_field
                + f'<label class="opt"><span class="opt-box" data-shape="check"{checked}></span>'
                + f"{label}</label></div>"
            )
        if ftype == "radio":
            options = [str(o) for o in (field.get("options") or [])]
            opts_html = '<div class="opt-group opt-group--plain">'
            for opt in options:
                checked = ' data-checked="true"' if str(default) == opt else ""
                opts_html += (
                    f'<label class="opt"><span class="opt-box" data-shape="radio"{checked}></span>'
                    f"{escape(opt)}</label>"
                )
            return open_field + opts_html + "</div></div>"
        if ftype == "select":
            options = [str(o) for o in (field.get("options") or [])]
            opts_html = "".join(
                f'<option{" selected" if str(default) == o else ""}>{escape(o)}</option>'
                for o in options
            )
            return open_field + f'<select class="ctrl">{opts_html}</select></div>'
        if ftype == "textarea":
            value = escape(str(default or ""))
            return open_field + f'<textarea class="ctrl ctrl--textarea">{value}</textarea></div>'
        # text / number / money / date → 下划线填空（data-type 随 data-field 下行，
        # prepare_html/place_widgets 按类型映射；date 三段式不在此编译）
        value = escape(str(default or ""))
        return open_field + (
            f'<input class="ctrl ctrl--underline" type="text" value="{value}">'
            "</div>"
        )

    parts: list[str] = [
        '<div class="page-a4"><form class="pdf-form">',
        # 表头：单位 + 标题 + 编号/版本（对齐 04-expense 的 form-head）
        '<header class="form-head"><div class="form-head-main">',
        f'<h1 class="form-title">{escape(title)}</h1>',
        '<div class="form-subtitle">FILLABLE FORM — 可交互填写，填写后可直接打印或存档</div>',
        "</div>",
        '<div class="form-head-meta">',
        '<div><span class="meta-k">表单编号</span> <span class="meta-v">FORM-001</span></div>',
        '<div><span class="meta-k">版本</span> <span class="meta-v">V1.0</span></div>',
        "</div></header>",
    ]

    for index, section in enumerate(sections or [], 1):
        heading = escape(str(section.get("heading") or "").strip())
        parts.append('<section class="form-section">')
        parts.append(
            f'<div class="sec-head"><span class="sec-num">{index}</span>'
            f'<h2 class="sec-title">{heading or "未命名分节"}</h2></div>'
            '<div class="sec-rule"></div>'
        )
        parts.append('<div class="field-grid">')
        for field in section.get("fields") or []:
            parts.append(_field_html(field))
        parts.append("</div></section>")

    parts.append("</form></div>")
    return (
        '<!DOCTYPE html><html lang="zh-CN" data-theme="minimal"><head>'
        '<meta charset="UTF-8"><title>' + escape(title) + "</title>"
        '<link rel="stylesheet" href="forms.css"></head><body>'
        + "".join(parts)
        + "</body></html>"
    )



def main() -> None:
    data = json.load(sys.stdin)
    output_root = Path(data.get("output_dir") or data["workspace"])
    params = data.get("params") or {}
    title = str(params.get("title") or "").strip()
    file_name = str(params.get("file_name") or "").strip()
    values = params.get("values") if isinstance(params.get("values"), dict) else {}
    theme = str(params.get("theme") or "").strip()
    color_scheme = str(params.get("color_scheme") or "").strip()
    theme_colors = params.get("theme_colors") if isinstance(params.get("theme_colors"), dict) else {}

    template_id = str(params.get("template_id") or "").strip()
    custom_html = str(params.get("html") or "").strip()
    sections = params.get("sections")

    if template_id:
        try:
            html = load_template(template_id)
        except ValueError as exc:
            print(json.dumps({"success": False, "message": str(exc)}, ensure_ascii=False))
            return
        title = title or "表单"
    elif custom_html:
        html = custom_html
        title = title or "表单"
    elif isinstance(sections, list) and sections:
        html = _compose_sections_html(sections, title or "表单")
        title = title or "表单"
    else:
        print(
            json.dumps(
                {
                    "success": False,
                    "message": "需要 template_id（内置模板）、html（协议 HTML）或 sections（字段清单）之一",
                },
                ensure_ascii=False,
            )
        )
        return

    if theme:
        html = set_theme(html, theme)

    # 期三协议校验：组合模式拼装错误逐条报出，模型可自纠（字段名重复/类型白名单/裸控件泄漏）
    if not template_id:
        problems = validate_schema(html)
        if problems:
            print(
                json.dumps(
                    {"success": False, "message": "HTML 协议校验失败：" + "；".join(problems)},
                    ensure_ascii=False,
                )
            )
            return

    prepared, meta = prepare_html(html, values)
    if not meta:
        print(
            json.dumps(
                {
                    "success": False,
                    "message": (
                        "HTML 中未找到 data-field 字段标记——请遵循模板库协议："
                        "可填写单元带 data-field/data-type/data-label 属性"
                    ),
                },
                ensure_ascii=False,
            )
        )
        return

    templates_dir = form_templates_dir()
    extra_css = theme_override_css(color_scheme, theme_colors)
    pdf_bytes = render_pdf(prepared, templates_dir, extra_css=extra_css)
    doc, report = place_widgets(pdf_bytes, meta)
    problems = verify_form(doc.tobytes(), meta)
    if problems:
        doc.close()
        print(
            json.dumps(
                {"success": False, "message": "；".join(problems)}, ensure_ascii=False
            )
        )
        return

    output_dir = output_root / "pdf"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = unique_output_path(output_dir, file_name or title, "表单", ".pdf")
    output_path.write_bytes(doc.tobytes())
    doc.close()

    total = sum(item["count"] for item in report["filled"])
    print(
        json.dumps(
            {
                "success": True,
                "message": f"表单 PDF 生成完成（{total} 个交互控件，{report['filled'].__len__()} 个字段组）",
                "file_name": output_path.name,
                "filepath": str(output_path),
                "content": (
                    f"已生成可填写的表单 PDF：{output_path.name}。"
                    "可用 pdf_form_fields 查看字段、pdf_form_fill 填写。"
                    + ("警告：" + "；".join(report["warnings"]) if report["warnings"] else "")
                ),
                "data": {
                    "fields": report["filled"],
                    "warnings": report["warnings"],
                    "template": template_id or None,
                    "mode": "template" if template_id else ("html" if custom_html else "sections"),
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
