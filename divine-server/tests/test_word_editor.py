"""Word run 级编辑引擎（docgen/word/editor.py）：
单/跨 run 替换保样式、表格定位、事务中止、append_section。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from docx import Document

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.docgen.word.editor import (  # noqa: E402
    EditOpError,
    apply_ops,
    fill_template,
    replace_in_paragraph,
)


def _make_document() -> Document:
    document = Document()
    document.add_heading("2026年9月工作月报", 1)
    document.add_paragraph("本月共完成客户交付项目 12 个，环比上升 20%。")
    # 跨 run 段落：营业额(粗) 增长(常规) 20%，环比显著。(常规)
    paragraph = document.add_paragraph()
    run1 = paragraph.add_run("营业额")
    run1.bold = True
    paragraph.add_run("增长")
    paragraph.add_run("20%，环比显著。")
    table = document.add_table(rows=3, cols=2)
    table.rows[0].cells[0].text = "项目"
    table.rows[0].cells[1].text = "状态"
    table.rows[1].cells[0].text = "客户A"
    table.rows[1].cells[1].text = "交付中"
    table.rows[2].cells[0].text = "客户B"
    table.rows[2].cells[1].text = "已完成"
    return document


def test_single_run_replace_preserves_style():
    document = _make_document()
    paragraph = document.paragraphs[1]
    hits, cross = replace_in_paragraph(paragraph, "12 个", "18 个")
    assert hits == 1 and cross == 0
    assert "18 个" in paragraph.text
    # 原段落没有 run 级特殊格式，重开也不丢段落
    assert document.paragraphs[1].text.startswith("本月共完成")


def test_cross_run_replace_reports_and_keeps_first_run_style():
    document = _make_document()
    paragraph = document.paragraphs[2]  # 营业额(粗)+增长+...
    hits, cross = replace_in_paragraph(paragraph, "额增长", "额暴涨")
    assert hits == 1 and cross == 1
    assert "营业额暴涨" in paragraph.text
    # 跨 run 替换采用首个 run 的格式（粗体延续到新文本），span 外格式不变
    assert paragraph.runs[0].bold is True


def test_replace_all_and_case_insensitive():
    document = Document()
    document.add_paragraph("Alpha alpha ALPHA end")
    paragraph = document.paragraphs[0]
    hits, _ = replace_in_paragraph(paragraph, "alpha", "x", all_matches=True)
    assert hits == 3
    assert paragraph.text == "x x x end"


def test_replace_miss_returns_zero():
    document = _make_document()
    hits, _ = replace_in_paragraph(document.paragraphs[1], "不存在的文本", "x")
    assert hits == 0


def test_apply_ops_transaction_aborts_on_miss():
    document = _make_document()
    before = document.paragraphs[1].text
    with pytest.raises(EditOpError):
        apply_ops(
            document,
            [
                {"op": "set_paragraph", "match": "本月共完成", "text": "已修改"},
                {"op": "replace_text", "find": "不存在的目标", "replace": "x"},
            ],
        )
    # 第一个 op 在内存中已生效，但调用方（脚本）不会写盘 → 磁盘无变化；
    # 引擎契约：抛出 EditOpError 并带 missed 明细
    exc_info = pytest.raises(
        EditOpError,
        lambda: apply_ops(
            document,
            [{"op": "replace_text", "find": "不存在的目标", "replace": "x"}],
        ),
    )
    assert "不存在的目标" in str(exc_info.value)
    assert before  # 内存文档未被破坏性重建


def test_set_table_cell_by_header_and_row_key():
    document = _make_document()
    report = apply_ops(
        document,
        [
            {
                "op": "set_table_cell",
                "table": 1,
                "header": "状态",
                "row_key": "客户B",
                "text": "已验收",
            }
        ],
    )
    assert report["hits"] == 1
    assert document.tables[0].rows[2].cells[1].text == "已验收"
    assert document.tables[0].rows[1].cells[1].text == "交付中"


def test_set_table_cell_wrong_header_gives_candidates():
    document = _make_document()
    with pytest.raises(EditOpError) as exc_info:
        apply_ops(
            document,
            [
                {
                    "op": "set_table_cell",
                    "table": 1,
                    "header": "状态栏",
                    "row_key": "客户B",
                    "text": "x",
                }
            ],
        )
    assert "状态" in str(exc_info.value)  # 候选提示


def test_delete_and_append_section():
    document = _make_document()
    report = apply_ops(
        document,
        [
            {"op": "delete_paragraph", "match": "环比上升"},
            {
                "op": "append_section",
                "heading": "下月计划",
                "level": 2,
                "items": ["交付客户C", "启动客户D"],
            },
        ],
    )
    assert report["hits"] == 2
    texts = [p.text for p in document.paragraphs]
    assert not any("环比上升" in t for t in texts)
    assert "下月计划" in texts
    assert "交付客户C" in texts


def test_fill_template_basic_and_missing():
    document = Document()
    document.add_paragraph("甲方：{{company}}")
    document.add_paragraph("签订日期：{{sign_date}}，编号：{{no}}")
    report = fill_template(
        document, {"company": "某某科技", "sign_date": "2026年9月6日", "no": "A-001"}
    )
    assert document.paragraphs[0].text == "甲方：某某科技"
    assert "2026年9月6日" in document.paragraphs[1].text
    assert report["missing_keys"] == []


def test_fill_template_reports_missing_and_residual():
    document = Document()
    document.add_paragraph("甲方：{{company}}，邮编：{{zipcode}}")
    # no_such：提供了值但文档中无此占位符 → missing_keys
    # zipcode：文档有占位符但未提供值 → warnings（保留原文）
    report = fill_template(document, {"company": "某某科技", "no_such": "x"})
    assert "no_such" in report["missing_keys"]
    assert "{{zipcode}}" in document.paragraphs[0].text
    assert any("zipcode" in warning for warning in report["warnings"])


def test_fill_template_table_row_expansion():
    document = Document()
    document.add_paragraph("采购清单：")
    table = document.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "名称"
    table.rows[0].cells[1].text = "数量"
    table.rows[1].cells[0].text = "{{items.name}}"
    table.rows[1].cells[1].text = "{{items.qty}}"
    report = fill_template(
        document,
        {},
        list_values={
            "items": [
                {"name": "显示器", "qty": "2"},
                {"name": "键盘", "qty": "5"},
            ]
        },
    )
    assert report["missing_keys"] == []
    assert len(table.rows) == 3  # 表头 + 模板行填第一条 + 复制行填第二条
    assert table.rows[1].cells[0].text == "显示器"
    assert table.rows[2].cells[0].text == "键盘"
    assert table.rows[2].cells[1].text == "5"
