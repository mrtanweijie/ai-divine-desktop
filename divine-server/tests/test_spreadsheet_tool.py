"""Tests for spreadsheet tool: themes, smart cell coercion, layout styling."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
from openpyxl import load_workbook

SCRIPT = Path(__file__).resolve().parents[1] / "app" / "tools" / "scripts" / "spreadsheet.py"


def _run(workspace: Path, params: dict) -> dict:
    payload = {
        "workspace": str(workspace.resolve()),
        "output_dir": str(workspace.resolve() / "out"),
        "params": params,
        "locale": "zh-CN",
    }
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _load(out: dict):
    return load_workbook(out["filepath"])


def test_styled_table_with_smart_coercion(tmp_path: Path) -> None:
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    out = _run(
        ws_dir,
        {
            "file_name": "项目进度表",
            "title": "2026 年 Q3 项目进度表",
            "headers": ["任务", "负责人", "进度", "截止日期", "金额"],
            "rows": [
                ["需求评审", "张三", "100%", "2026-08-30", "¥1,234.50"],
                ["接口开发", "李四", 0.75, "2026/9/15", 2000],
                ["联调测试", "王五", "12.34%", "2026年10月1日", "3,500.8"],
                ["上线部署", "赵六", True, "2026-11-30 09:30", 12000],
            ],
            "total_row": True,
            "sheet_name": "进度",
        },
    )
    assert out["success"] is True
    assert out["data"]["theme"] == "blue"  # 标题含"项目/进度"自动选商务蓝
    assert out["data"]["rows"] == 4

    book = _load(out)
    sheet = book["进度"]
    assert sheet.title == "进度"
    assert sheet.sheet_view.showGridLines is False

    # 标题栏 + 信息行 + 表头
    assert sheet["A1"].value == "2026 年 Q3 项目进度表"
    assert "共 4 行" in sheet["A2"].value
    assert sheet["A3"].value == "任务"
    assert sheet["A3"].font.bold is True
    assert sheet["A3"].fill.fgColor.rgb.endswith("2563EB")
    assert sheet.freeze_panes == "A4"
    assert sheet.auto_filter.ref == "A3:E8"  # 4 数据行 + 1 合计行

    # 斑马纹：第 2 条数据行（第 5 行）着色，第 1 条不着色
    assert sheet["A4"].fill.fill_type != "solid" or sheet["A4"].fill.fgColor.rgb in (None, "00000000")
    assert sheet["A5"].fill.fgColor.rgb.endswith("EFF4FE")

    # 智能类型识别（进度列多数为百分比 → 整列统一为 0.00%，含裸小数与合计）
    assert sheet["C4"].value == 1.0 and sheet["C4"].number_format == "0.00%"
    assert sheet["C5"].value == 0.75 and sheet["C5"].number_format == "0.00%"  # 百分比列裸小数
    assert sheet["C6"].value == 0.1234 and sheet["C6"].number_format == "0.00%"
    assert sheet["C8"].number_format == "0.00%"  # 合计行同列格式一致
    assert sheet["C7"].value == "是"
    assert isinstance(sheet["D4"].value, datetime) and sheet["D4"].number_format == "yyyy-mm-dd"
    assert isinstance(sheet["D7"].value, datetime) and sheet["D7"].number_format == "yyyy-mm-dd hh:mm"
    assert sheet["E4"].value == 1234.5 and sheet["E4"].number_format == "¥#,##0.00"
    assert sheet["E5"].value == 2000 and sheet["E5"].number_format == "¥#,##0"
    assert sheet["E6"].value == 3500.8

    # 合计行（金额列求和，进度列多数为百分比数值也求和）
    assert sheet["A8"].value == "合计"
    assert sheet["E8"].value == pytest.approx(1234.5 + 2000 + 3500.8 + 12000)
    assert sheet["E8"].number_format == "¥#,##0.00"
    assert sheet["A8"].font.bold is True


def test_style_alias_and_currency_by_header(tmp_path: Path) -> None:
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    out = _run(
        ws_dir,
        {
            "file_name": "月度账单",
            "style": "商务蓝",
            "headers": ["项目", "预算(元)"],
            "rows": [["服务器", "12,000"], ["域名", 600]],
        },
    )
    assert out["data"]["theme"] == "blue"
    book = _load(out)
    sheet = book.active
    # 文件名"账单"命中财务关键词 → 翡翠绿；但显式传 style 优先生效
    assert sheet["B3"].fill.fgColor.rgb.endswith("2563EB")
    # "12,000" 千分位 → 数字；列头含"预算" → 货币格式
    assert sheet["B4"].value == 12000 and sheet["B4"].number_format == "¥#,##0"
    assert sheet["B5"].value == 600
    # 未传 title：文件名自动成为标题（标题+信息行占两行，表头在第 3 行）
    assert sheet["A1"].value == "月度账单"
    assert sheet.freeze_panes == "A4"


def test_no_title_and_cjk_column_width(tmp_path: Path) -> None:
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    out = _run(
        ws_dir,
        {
            "file_name": "表格",
            "headers": ["名称", "备注"],
            "rows": [["短", "这是一段比较长的中文备注内容需要更宽的列"]],
        },
    )
    book = _load(out)
    sheet = book.active
    assert sheet["A1"].value == "名称"  # 无标题栏，首行即表头
    assert sheet.freeze_panes == "A2"
    assert sheet.auto_filter.ref == "A1:B2"
    width_b = sheet.column_dimensions["B"].width
    assert 9 <= width_b <= 46
    # 中文按 2 倍宽计算：20 个汉字 → 40 + 边距
    assert width_b > 40


def test_empty_input_rejected(tmp_path: Path) -> None:
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    out = _run(ws_dir, {"file_name": "空表", "headers": [], "rows": []})
    assert out["success"] is False
    assert "不能同时为空" in out["message"]


def test_path_outside_workspace_rejected(tmp_path: Path) -> None:
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    out = _run(ws_dir, {"file_name": "越界", "headers": ["a"], "rows": [[1]], "path": "../outside"})
    assert out["success"] is False
    assert "越界" in out["message"]
