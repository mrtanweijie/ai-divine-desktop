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
    """未知模板 / 无字段标记 / 字段名重复 / 协议违例 → 明确失败。"""
    base = {"workspace": str(tmp_path), "output_dir": str(tmp_path)}

    out = _run_script({**base, "params": {"template_id": "nope"}}, tmp_path)
    assert out["success"] is False and "nope" in out["message"]

    out = _run_script({**base, "params": {"template_id": "application", "html": "<html></html>"}}, tmp_path)
    assert out["success"] is True  # template 优先于 html（约定）

    no_field = {"title": "空表单", "html": "<html><body><p>没有字段</p></body></html>"}
    out = _run_script({**base, "params": no_field}, tmp_path)
    assert out["success"] is False and "data-field" in out["message"]


def test_schema_validation_duplicate_and_bare(tmp_path):
    """组合模式协议校验：字段名重复 / 容器外裸控件 → 明确报错（模型可自纠）。"""
    base = {"workspace": str(tmp_path), "output_dir": str(tmp_path)}

    # 字段名重复
    dup_html = (
        "<html><body><div class=\"field col-12\" data-field=\"x\" data-type=\"text\" "
        'data-label="一"><input></div>'
        '<div class="field col-12" data-field="x" data-type="text" data-label="二">'
        "<input></div></body></html>"
    )
    out = _run_script({**base, "params": {"title": "T", "html": dup_html}}, tmp_path)
    assert out["success"] is False and "字段名重复" in out["message"]

    # 容器外裸控件（漏标 data-field）
    bare_html = (
        "<html><body><div class=\"field col-12\" data-field=\"a\" data-type=\"text\" "
        'data-label="甲"><input></div>'
        '<div class="field col-12"><input placeholder="漏标控件"></div></body></html>'
    )
    out = _run_script({**base, "params": {"title": "T", "html": bare_html}}, tmp_path)
    assert out["success"] is False and "裸控件" in out["message"] or "data-field" in out["message"]

    # 非法 data-type
    bad_type = (
        '<div class="field col-12" data-field="b" data-type="slider" data-label="乙">'
        "<input></div>"
    )
    out = _run_script({**base, "params": {"title": "T", "html": bad_type}}, tmp_path)
    assert out["success"] is False and "白名单" in out["message"]


def test_schema_validation_container_bare_control(tmp_path):
    """group 容器内 div 布局裸控件必须拦截（渲染期会静默丢失，校验须先行）。

    回归：裸控件只要有一个 [data-field] 祖先（group）就放行，但 prepare_html 的
    容器分支只派生 tbody tr 里的裸控件 → div 行裸控件校验放行、渲染丢弃，契约断裂。
    """
    base = {"workspace": str(tmp_path), "output_dir": str(tmp_path)}

    # group 内 div 行裸控件（无 tbody）→ 拒绝
    group_div_html = (
        '<html><body><div data-field="contact" data-type="group">'
        '<div class="field-label">联系方式</div>'
        '<div class="kv-row"><label>电话</label>'
        '<input class="ctrl" placeholder="手机号"></div>'
        "</div></body></html>"
    )
    out = _run_script({**base, "params": {"title": "T", "html": group_div_html}}, tmp_path)
    assert out["success"] is False, "group div 裸控件应被拒绝"
    assert "表格行" in out["message"]

    # 同容器但裸控件在 tbody 行内（表格列派生）→ 放行，且派生字段真实落位
    group_table_html = (
        '<html><body><div data-field="edu" data-type="table">'
        "<table><thead><tr><th>序号</th><th>学校</th></tr></thead>"
        '<tbody><tr><td>1</td><td><input placeholder="大学"></td></tr></tbody>'
        "</table></div></body></html>"
    )
    out = _run_script({**base, "params": {"title": "T", "html": group_table_html}}, tmp_path)
    assert out["success"] is True, out.get("message")
    widgets = _widgets(Path(out["filepath"]))
    assert "edu.学校#1" in widgets, "表格行裸控件应派生 edu.学校#1 并落位"


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


def test_table_container_subfields(tmp_path):
    """表格容器：无 data-field 的列输入派生 '表名.列头#行号' 字段并替换为锚点。

    回归：曾只构造锚点不替换 input → 无 pdf-form:// 链接 → 控件缺失
    （education.1#1 序号列污染列名）；列名应来自 thead 列头、不含序号列。
    """
    from bs4 import BeautifulSoup

    from app.docgen.pdf.form_html import load_template, prepare_html, render_pdf, place_widgets, form_templates_dir

    tpl = load_template("registration")
    prepared, meta = prepare_html(tpl)
    # 表格派生字段集合 == 列头(除序号)×行数
    soup = BeautifulSoup(tpl, "html.parser")
    expect: set[str] = set()
    for el in soup.select('[data-field][data-type="table"]'):
        fname = el["data-field"]
        headers = [th.get_text(strip=True) for th in el.select("thead th")]
        rows = len(el.select("tbody tr"))
        for h in headers[1:]:  # 跳序号列
            for r in range(1, rows + 1):
                expect.add(f"{fname}.{h}#{r}")
    got = {m["field"] for m in meta.values()}
    assert expect <= got, f"表格派生字段缺失: {sorted(expect - got)[:8]}"
    # 序号列不得污染列名（历史 bug education.1#1）
    assert not any(m["field"].endswith("1#") or ".1#" in m["field"] for m in meta.values())

    # 全量控件落位（含表格字段）：registration 25 data-field + 派生字段
    pdf = render_pdf(prepared, form_templates_dir())
    doc, report = place_widgets(pdf, meta)
    filled = {f["key"] for f in report["filled"]}
    assert got <= filled
    doc.close()


def test_sections_extended_types_and_half(tmp_path):
    """sections 扩展类型：dropdown 别名→COMBOBOX 且默认值落位；date/money 编译；
    half 并排（同 y 两个半行控件）；required 标志。"""
    output = _run_script(
        {
            "workspace": str(tmp_path),
            "output_dir": str(tmp_path),
            "params": {
                "title": "扩展类型",
                "sections": [
                    {
                        "heading": "报销",
                        "fields": [
                            {"name": "staff", "label": "报销人", "type": "text", "half": True},
                            {"name": "date", "label": "日期", "type": "date", "half": True},
                            {"name": "kind", "label": "费用类型", "type": "dropdown",
                             "options": ["交通", "餐饮", "住宿"], "default": "餐饮"},
                            {"name": "amt", "label": "金额", "type": "money", "required": True},
                        ],
                    }
                ],
                "file_name": "扩展类型",
            },
        },
        tmp_path,
    )
    assert output["success"] is True, output.get("message")
    widgets = _widgets(Path(output["filepath"]))
    # dropdown 别名 → 下拉（type 3 = COMBOBOX）
    kind = [w for w in widgets["kind"]]
    assert kind and kind[0].field_type == pymupdf.PDF_WIDGET_TYPE_COMBOBOX
    assert kind[0].field_value == "餐饮"  # default 经 option[selected] 落位
    assert widgets["amt"][0].field_flags & 2  # required 位
    # half：staff 与 date 并排（同 y 顶、不同 x，各约半行宽）
    staff, date_ = widgets["staff"][0], widgets["date"][0]
    assert staff.rect.y0 == date_.rect.y0
    assert staff.rect.x0 != date_.rect.x0
    staff_w = staff.rect.x1 - staff.rect.x0
    assert staff_w < 400  # 非整行（整行约 527pt）
    assert abs((date_.rect.x1 - date_.rect.x0) - staff_w) < 10  # 两半行等宽
