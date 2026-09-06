"""PDF 交互表单工具回归（pdf_form_fields / pdf_form_fill）：

- 字段清单（名称/类型/复选框状态）；
- 填写：文本/中文值/复选框勾选与取消/未命中事务中止；
- 重开校验 + 外部文件副本 + 备份恢复。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pymupdf
import pytest
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.docgen.pdf.form import (
    PdfFormError,
    fill_fields,
    list_fields,
    verify_filled,
)


def _make_form_pdf(path: Path) -> None:
    c = canvas.Canvas(str(path))
    c.acroForm.textfield(name="company", x=80, y=700, width=300, height=20, borderWidth=0)
    c.acroForm.textfield(name="amount", x=80, y=660, width=200, height=20, borderWidth=0)
    c.acroForm.checkbox(name="agree", x=80, y=620, size=16, buttonStyle="check")
    c.showPage()
    c.save()


def test_list_fields_reports_names_types_and_states(tmp_path):
    path = tmp_path / "form.pdf"
    _make_form_pdf(path)
    result = list_fields(path)
    assert result["kind"] == "pdf_form" and result["field_count"] == 3
    by_name = {f["name"]: f for f in result["fields"]}
    assert by_name["company"]["type"] == "Text"
    assert by_name["agree"]["type"] == "CheckBox"
    assert "Off" in by_name["agree"]["states"]
    assert by_name["company"]["page"] == 1


def test_list_fields_empty_for_plain_pdf(tmp_path):
    """扫描件/无表单信号：字段清单为空。"""
    path = tmp_path / "plain.pdf"
    c = canvas.Canvas(str(path))
    c.drawString(100, 700, "纯文本，无表单")
    c.showPage()
    c.save()
    result = list_fields(path)
    assert result["field_count"] == 0


def test_fill_fields_text_checkbox_and_chinese(tmp_path):
    path = tmp_path / "form.pdf"
    _make_form_pdf(path)
    doc, report = fill_fields(
        path, {"company": "某某科技", "amount": "12,000", "agree": "true"}
    )
    data = doc.tobytes()
    doc.close()
    doc2 = pymupdf.open(stream=data, filetype="pdf")
    values = {w.field_name: w.field_value for p in doc2 for w in p.widgets()}
    assert values["company"] == "某某科技"
    assert values["amount"] == "12,000"
    assert values["agree"] == "Yes"  # 勾选语义
    assert report["filled"] == [
        {"key": "agree", "count": 1},
        {"key": "amount", "count": 1},
        {"key": "company", "count": 1},
    ]


def test_fill_fields_uncheck_sets_off(tmp_path):
    path = tmp_path / "form.pdf"
    _make_form_pdf(path)
    doc, _ = fill_fields(path, {"agree": "false"})
    data = doc.tobytes()
    doc.close()
    doc2 = pymupdf.open(stream=data, filetype="pdf")
    values = {w.field_name: w.field_value for p in doc2 for w in p.widgets()}
    assert values["agree"] in ("Off", "", None)


def test_fill_fields_unknown_names_abort(tmp_path):
    """事务性：任一字段未命中即抛错，候选含现有字段名。"""
    path = tmp_path / "form.pdf"
    _make_form_pdf(path)
    with pytest.raises(PdfFormError) as exc_info:
        fill_fields(path, {"company": "x", "nope": "y"})
    assert "nope" in str(exc_info.value)
    assert "company" in exc_info.value.candidates


def test_verify_filled_detects_missing_values(tmp_path):
    path = tmp_path / "form.pdf"
    _make_form_pdf(path)
    doc, _ = fill_fields(path, {"company": "某某科技"})
    data = doc.tobytes()
    doc.close()
    filled_path = tmp_path / "filled.pdf"
    filled_path.write_bytes(data)
    assert verify_filled(filled_path, {"company": "某某科技"}) == []
    problems = verify_filled(filled_path, {"company": "另一家"})
    assert problems and "company" in problems[0]


def _run_script(name: str, payload: dict, tmp_path: Path | None = None) -> dict:
    script = Path(__file__).resolve().parents[1] / "app" / "tools" / "scripts" / name
    env = None
    if tmp_path is not None:
        import os

        env = {
            **os.environ,
            "DIVINE_DATA_DIR": str(tmp_path / "data"),
            "DB_PATH": str(tmp_path / "eval-form.db"),
        }
    completed = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    return json.loads(completed.stdout)


def test_pdf_form_fill_script_external_copy_and_backup(tmp_path):
    """外部 PDF → 副本编辑（原文件不动）；workspace 内 → 备份可撤销。"""
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    external = tmp_path / "Desktop"
    external.mkdir()
    form = external / "合同.pdf"
    _make_form_pdf(form)
    original_bytes = form.read_bytes()

    output = _run_script(
        "pdf_form_fill.py",
        {
            "workspace": str(ws_dir),
            "output_dir": str(ws_dir),
            "params": {
                "path": str(form),
                "session_id": "s-form",
                "values": {"company": "某某科技"},
            },
        },
    )
    assert output["success"] is True
    assert form.read_bytes() == original_bytes  # 原文件未动
    copy_path = Path(output["filepath"])
    assert copy_path.parent == ws_dir / "documents" / "edited"
    assert list_fields(copy_path)["fields"][0]["value"] == "某某科技"

    # workspace 内原地填写：先备份
    inner = ws_dir / "表单.pdf"
    _make_form_pdf(inner)
    inner_before = inner.read_bytes()
    output = _run_script(
        "pdf_form_fill.py",
        {
            "workspace": str(ws_dir),
            "output_dir": str(ws_dir),
            "params": {
                "path": str(inner),
                "session_id": "s-form",
                "values": {"company": "原地填写"},
            },
        },
        tmp_path,
    )
    assert output["success"] is True
    assert output["data"]["backup_path"] is not None
    assert Path(output["data"]["backup_path"]).is_file()
    assert inner.read_bytes() != inner_before


def test_pdf_form_fill_script_abort_keeps_file(tmp_path):
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    form = ws_dir / "form.pdf"
    _make_form_pdf(form)
    before = form.read_bytes()
    output = _run_script(
        "pdf_form_fill.py",
        {
            "workspace": str(ws_dir),
            "output_dir": str(ws_dir),
            "params": {
                "path": str(form),
                "session_id": "s-form",
                "values": {"不存在的字段": "x"},
            },
        },
    )
    assert output["success"] is False
    assert form.read_bytes() == before


def test_pdf_form_fields_script_lists(tmp_path):
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    form = ws_dir / "form.pdf"
    _make_form_pdf(form)
    output = _run_script(
        "pdf_form_fields.py",
        {"workspace": str(ws_dir), "output_dir": str(ws_dir), "params": {"path": str(form)}},
    )
    assert output["success"] is True
    assert output["data"]["field_count"] == 3
    assert "agree" in output["content"]
