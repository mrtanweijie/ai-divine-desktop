"""pdf_form_generate（HTML 模板管线）回归：

- 模板实例化（application）+ values 预填 + 控件放置；
- 组合模式（自定义协议 HTML）与 sections 兼容模式；
- 契约校验（未知模板/无字段标记/字段名重复）；
- 闭环：生成 → pdf_form_fields → pdf_form_fill → verify。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.docgen.pdf.form import fill_fields, verify_filled


def _run_script(payload: dict, tmp_path: Path) -> dict:
    script = Path(__file__).resolve().parents[1] / "app" / "tools" / "scripts" / "pdf_form_generate.py"
    import os

    env = {
        **os.environ,
        "DIVINE_DATA_DIR": str(tmp_path / "data"),
        "DB_PATH": str(tmp_path / "eval-form-gen.db"),
    }
    completed = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    return json.loads(completed.stdout)


def _widgets(path: Path) -> dict[str, list]:
    doc = pymupdf.open(str(path))
    result: dict[str, list] = {}
    for page in doc:
        for w in page.widgets() or []:
            result.setdefault(w.field_name, []).append(w)
    doc.close()
    return result


APPLICATION_SPEC = {
    "template_id": "application",
    "values": {"applicant_name": "李铭", "matter_type": "采购申请"},
    "file_name": "事项申请表",
}


def test_generate_from_template_with_values(tmp_path):
    """模板实例化 + values 预填：控件集合 == 模板 data-field 集合。"""
    output = _run_script(
        {"workspace": str(tmp_path), "output_dir": str(tmp_path), "params": dict(APPLICATION_SPEC)},
        tmp_path,
    )
    assert output["success"] is True
    assert Path(output["filepath"]).parent == tmp_path / "pdf"
    assert output["data"]["mode"] == "template"

    widgets = _widgets(Path(output["filepath"]))
    # 模板的全部 data-field（含分组单选 name::选项 展开）都有控件
    expected_names = {
        "applicant_name", "employee_no", "department", "position", "phone", "email",
        "matter_type::请假", "matter_type::采购申请", "matter_type::用车申请",
    }
    assert expected_names <= set(widgets)
    # values 预填：文本默认值 + 单选按值勾选
    assert widgets["applicant_name"][0].field_value == "李铭"
    matter_values = {w.field_value for w in widgets["matter_type::采购申请"]}
    assert "Yes" in matter_values
    other = {w.field_value for w in widgets["matter_type::请假"]}
    assert "Off" in other


def test_generate_from_template_default_theme_and_meta(tmp_path):
    output = _run_script(
        {
            "workspace": str(tmp_path),
            "output_dir": str(tmp_path),
            "params": {"template_id": "application", "file_name": "申请表A"},
        },
        tmp_path,
    )
    assert output["success"] is True
    assert output["data"]["mode"] == "template"
    assert Path(output["filepath"]).name.startswith("申请表A")


def test_generate_from_custom_html(tmp_path):
    """组合模式：模型按协议拼装的自定义 HTML。"""
    html = (
        '<!DOCTYPE html><html lang="zh-CN" data-theme="tech"><head>'
        '<meta charset="UTF-8"><title>入场登记表</title>'
        '<link rel="stylesheet" href="forms.css"></head><body>'
        '<div class="page-a4"><form class="pdf-form">'
        '<h1 class="form-title">入场登记表</h1>'
        '<div class="field col-6" data-field="visitor" data-type="text" '
        'data-label="来访人" data-required="true">'
        '<div class="field-label">来访人</div>'
        '<input class="ctrl ctrl--underline" type="text"></div>'
        '<div class="field col-6" data-field="company" data-type="text" data-label="单位">'
        '<div class="field-label">单位</div>'
        '<input class="ctrl ctrl--underline" type="text"></div>'
        "</form></div></body></html>"
    )
    output = _run_script(
        {
            "workspace": str(tmp_path),
            "output_dir": str(tmp_path),
            "params": {"html": html, "values": {"visitor": "张三"}, "file_name": "入场登记"},
        },
        tmp_path,
    )
    assert output["success"] is True
    assert output["data"]["mode"] == "html"
    widgets = _widgets(Path(output["filepath"]))
    assert widgets["visitor"][0].field_value == "张三"


def test_generate_from_sections_legacy(tmp_path):
    """sections 声明式（v1 兼容）：编译为协议 HTML 后走同一管线。"""
    spec = {
        "title": "设备领用单",
        "sections": [
            {
                "heading": "领用信息",
                "fields": [
                    {"name": "device", "label": "设备名称", "type": "text", "default": " MacBook Pro"},
                    {"name": "kind", "label": "类型", "type": "radio", "options": ["长期", "临时"]},
                ],
            }
        ],
    }
    output = _run_script(
        {"workspace": str(tmp_path), "output_dir": str(tmp_path), "params": spec},
        tmp_path,
    )
    assert output["success"] is True
    assert output["data"]["mode"] == "sections"
    widgets = _widgets(Path(output["filepath"]))
    assert widgets["device"][0].field_value == " MacBook Pro"
    assert {"kind::长期", "kind::临时"} <= set(widgets)  # 分组单选展开
    assert all(w.field_value == "Off" for w in widgets["kind::长期"])  # 无默认全不选


def test_contract_errors(tmp_path):
    """未知模板 / 无字段标记 / 字段名重复 → 明确失败。"""
    base = {"workspace": str(tmp_path), "output_dir": str(tmp_path)}

    out = _run_script({**base, "params": {"template_id": "nope"}}, tmp_path)
    assert out["success"] is False and "nope" in out["message"]

    out = _run_script({**base, "params": {"template_id": "application", "html": "<html></html>"}}, tmp_path)
    assert out["success"] is True  # template 优先于 html（约定）

    no_field = {"title": "空表单", "html": "<html><body><p>没有字段</p></body></html>"}
    out = _run_script({**base, "params": no_field}, tmp_path)
    assert out["success"] is False and "data-field" in out["message"]


def test_closed_loop_generate_then_fill(tmp_path):
    """闭环：模板生成 → pdf_form_fields 读取 → pdf_form_fill 填写 → 校验。"""
    output = _run_script(
        {
            "workspace": str(tmp_path),
            "output_dir": str(tmp_path),
            "params": dict(APPLICATION_SPEC),
        },
        tmp_path,
    )
    generated = Path(output["filepath"])

    from app.docgen.pdf.form import fill_fields, list_fields

    listing = list_fields(generated)
    listing_names = {f["name"] for f in listing["fields"]}
    assert "applicant_name" in listing_names
    assert "matter_type" in listing_names  # 分组单选聚合为一个逻辑字段

    doc, report = fill_fields(
        generated, {"applicant_name": "王小明", "matter_type": "用车申请"}
    )
    data = doc.tobytes()
    doc.close()
    filled_path = tmp_path / "filled.pdf"
    filled_path.write_bytes(data)

    assert verify_filled(filled_path, {"applicant_name": "王小明", "matter_type": "用车申请"}) == []
    widgets = _widgets(filled_path)
    assert widgets["applicant_name"][0].field_value == "王小明"
    matter_checked = {
        name.split("::", 1)[1]
        for name, ws in widgets.items()
        if name.startswith("matter_type::") for w in ws if w.field_value == "Yes"
    }
    assert matter_checked == {"用车申请"}


from app.docgen.pdf.form import verify_filled  # noqa: E402


def test_generate_all_templates(tmp_path):
    """期二：4 个内置模板全部可生成，控件覆盖各自 data-field。"""
    from app.docgen.pdf.form_html import load_template, prepare_html

    for tid in ("application", "registration", "survey", "expense"):
        output = _run_script(
            {
                "workspace": str(tmp_path),
                "output_dir": str(tmp_path),
                "params": {"template_id": tid, "file_name": f"表单_{tid}"},
            },
            tmp_path,
        )
        assert output["success"] is True, (tid, output.get("message"))
        tpl_html = load_template(tid)
        _, meta = prepare_html(tpl_html)
        expected = {
            (f"{m['field']}::{m['option']}" if m.get("option") else m["field"])
            for m in meta.values()
        }
        widgets = _widgets(Path(output["filepath"]))
        actual = set(widgets)
        assert expected <= actual, f"{tid} 缺少控件: {sorted(expected - actual)[:5]}"


def test_custom_theme_color_injection(tmp_path):
    """自定义主题色：黑色 → 主题色覆盖块注入 + 控件正常。"""
    output = _run_script(
        {
            "workspace": str(tmp_path),
            "output_dir": str(tmp_path),
            "params": {
                "template_id": "application",
                "color_scheme": "黑色",
                "file_name": "黑色主题",
            },
        },
        tmp_path,
    )
    assert output["success"] is True
    import pymupdf

    doc = pymupdf.open(output["filepath"])
    assert any(p.widgets() for p in doc)
    doc.close()


def test_theme_color_css_derivation():
    """色词/#hex → token 覆盖块单测（无彩色系灰阶派生）。"""
    from app.docgen.pdf.form_html import theme_override_css

    css = theme_override_css("黑色", None)
    assert "--primary:#222222" in css.replace(" ", "")
    assert "--accent:" in css.replace(" ", "")

    css2 = theme_override_css(None, {"--color-primary": "#1A1A1A", "--color-accent": "#C9A227"})
    flat = css2.replace(" ", "")
    assert "#1A1A1A" in flat and "#C9A227" in flat

    assert theme_override_css(None, None) == ""
