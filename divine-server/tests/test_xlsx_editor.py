"""edit_xlsx 引擎与脚本回归（docs/design/017-office-edit-closed-loop-20260906.md §4.4）：

- set_cells（A1/表头定位/数字格式）、append_rows 末行探测、add_sheet 样式、
  set_formula；
- 公式与图表编辑后无损（§10 已实测，测试固化）；
- 图片往返冒烟断言（期二补充项）；
- 脚本端到端：外部副本、事务失败零修改。
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest  # noqa: E402
from openpyxl import Workbook, load_workbook  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.docgen.xlsx_editor import XlsxOpError, apply_ops  # noqa: E402


def _make_workbook(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "9月"
    ws.append(["日期", "客户", "金额"])
    ws.append(["2026-09-01", "客户A", 100])
    ws.append(["2026-09-02", "客户B", 200])
    ws["B5"] = "=SUM(C2:C3)"  # 故意放一个公式单元格
    ws2 = wb.create_sheet("汇总")
    ws2["A1"] = "合计"
    wb.save(str(path))


def test_set_cells_basic_and_number_format(tmp_path):
    path = tmp_path / "wb.xlsx"
    _make_workbook(path)
    wb = load_workbook(str(path))
    report = apply_ops(
        wb,
        [
            {
                "op": "set_cells",
                "sheet": "9月",
                "cells": [
                    {"cell": "C4", "value": 300, "number_format": "#,##0.00"},
                    {"cell": "A4", "value": "2026-09-03"},
                ],
            }
        ],
    )
    assert report["hits"] == 2
    ws = wb["9月"]
    assert ws["C4"].value == 300
    assert ws["C4"].number_format == "#,##0.00"
    assert ws["A4"].value == "2026-09-03"


def test_set_cells_header_column_resolution(tmp_path):
    path = tmp_path / "wb.xlsx"
    _make_workbook(path)
    wb = load_workbook(str(path))
    apply_ops(
        wb,
        [{"op": "set_cells", "sheet": "9月", "cells": [{"cell": "A4", "header": "金额", "value": 999}]}],
    )
    # header="金额" 覆盖列字母 → 写入 C4（第 4 行来自 A4 的行号）
    assert wb["9月"]["C4"].value == 999


def test_set_cells_wrong_header_gives_candidates(tmp_path):
    path = tmp_path / "wb.xlsx"
    _make_workbook(path)
    wb = load_workbook(str(path))
    with pytest.raises(XlsxOpError) as exc_info:
        apply_ops(
            wb,
            [{"op": "set_cells", "sheet": "9月", "cells": [{"cell": "A4", "header": "金额栏", "value": 1}]}],
        )
    assert "金额" in str(exc_info.value)


def test_merged_cell_redirects_to_anchor(tmp_path):
    path = tmp_path / "merged.xlsx"
    wb = Workbook()
    ws = wb.active
    ws["B2"] = "标题"
    ws.merge_cells("B2:C3")
    wb.save(str(path))

    wb = load_workbook(str(path))
    report = apply_ops(
        wb,
        [{"op": "set_cells", "cells": [{"cell": "C3", "value": "新标题"}]}],
    )
    assert any("锚点" in w for w in report["warnings"])
    assert wb.active["B2"].value == "新标题"


def test_append_rows_detects_last_data_row(tmp_path):
    path = tmp_path / "wb.xlsx"
    _make_workbook(path)
    wb = load_workbook(str(path))
    report = apply_ops(
        wb,
        [
            {
                "op": "append_rows",
                "sheet": "9月",
                "rows": [["2026-09-03", "客户C", 300]],
            }
        ],
    )
    assert report["hits"] == 1
    ws = wb["9月"]
    # B5 有公式（末行=5），新数据从第 6 行开始，不覆盖公式
    assert ws["A6"].value == "2026-09-03"
    assert ws["B5"].value == "=SUM(C2:C3)"
    assert any("第 6 行" in w for w in report["warnings"])


def test_set_formula_and_preservation(tmp_path):
    path = tmp_path / "wb.xlsx"
    _make_workbook(path)
    wb = load_workbook(str(path))
    apply_ops(
        wb,
        [{"op": "set_formula", "sheet": "9月", "cell": "C5", "formula": "SUM(C2:C4)"}],
    )
    assert wb["9月"]["C5"].value == "=SUM(C2:C4)"


def test_add_sheet_with_theme_and_collision(tmp_path):
    path = tmp_path / "wb.xlsx"
    _make_workbook(path)
    wb = load_workbook(str(path))
    report = apply_ops(
        wb,
        [
            {
                "op": "add_sheet",
                "name": "10月",
                "headers": ["日期", "金额"],
                "rows": [["2026-10-01", 500], ["2026-10-02", 600]],
            },
            {"op": "add_sheet", "name": "10月", "headers": ["日期"], "rows": []},
        ],
    )
    assert report["hits"] == 2
    assert "10月" in wb.sheetnames and "10月1" in wb.sheetnames  # 撞名加后缀
    ws = wb["10月"]
    assert ws["A1"].value == "日期"
    # _coerce_cell 把日期字符串转成 Excel 原生 date（生成器既有行为）
    assert "2026-10-01" in str(ws["A2"].value)
    assert ws.freeze_panes == "A2"
    assert ws["B2"].font.bold is False  # 数据行非粗体（样式已套用）
    assert ws.auto_filter.ref  # 自动筛选


def test_transaction_aborts_on_bad_sheet(tmp_path):
    path = tmp_path / "wb.xlsx"
    _make_workbook(path)
    wb = load_workbook(str(path))
    with pytest.raises(XlsxOpError):
        apply_ops(
            wb,
            [
                {"op": "set_cells", "sheet": "9月", "cells": [{"cell": "C2", "value": 1}]},
                {"op": "set_cells", "sheet": "不存在", "cells": [{"cell": "A1", "value": 1}]},
            ],
        )


def test_formula_and_chart_survive_round_trip(tmp_path):
    """§10 固化：编辑保存后重开，公式与图表部件完整。"""
    path = tmp_path / "rich.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["月份", "销量"])
    for row in [("1月", 10), ("2月", 20), ("3月", 30)]:
        ws.append(row)
    ws["B5"] = "=SUM(B2:B4)"
    from openpyxl.chart import BarChart, Reference

    chart = BarChart()
    chart.add_data(Reference(ws, min_col=2, min_row=1, max_row=4), titles_from_data=True)
    ws.add_chart(chart, "D2")
    wb.save(str(path))

    wb = load_workbook(str(path))
    apply_ops(
        wb, [{"op": "set_cells", "cells": [{"cell": "A2", "value": "一月"}]}]
    )
    wb.save(str(path))

    reloaded = load_workbook(str(path))
    assert reloaded.active["B5"].value == "=SUM(B2:B4)"
    assert reloaded.active["A2"].value == "一月"
    import zipfile

    names = zipfile.ZipFile(str(path)).namelist()
    assert any("chart" in name for name in names)


def test_image_round_trip_smoke(tmp_path):
    """期二补充项：嵌入图片经编辑往返后部件仍存在。"""
    path = tmp_path / "img.xlsx"
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "带图"
    # 1x1 红色 PNG
    from PIL import Image as PILImage

    buffer = io.BytesIO()
    PILImage.new("RGB", (4, 4), (200, 30, 30)).save(buffer, format="PNG")
    png_path = tmp_path / "dot.png"
    png_path.write_bytes(buffer.getvalue())

    from openpyxl.drawing.image import Image as XLImage

    ws.add_image(XLImage(str(png_path)), "B2")
    wb.save(str(path))

    wb = load_workbook(str(path))
    apply_ops(wb, [{"op": "set_cells", "cells": [{"cell": "A2", "value": "改动"}]}])
    wb.save(str(path))

    names = zipfile_names(path)
    assert any("media" in name for name in names)


def zipfile_names(path: Path) -> list[str]:
    import zipfile

    return zipfile.ZipFile(str(path)).namelist()


def _run_script(payload: dict) -> dict:
    script = Path(__file__).resolve().parents[1] / "app" / "tools" / "scripts" / "edit_xlsx.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    return json.loads(completed.stdout)


def test_edit_xlsx_script_external_file_creates_copy(tmp_path):
    ws = tmp_path / "ws"
    (ws / "documents").mkdir(parents=True)
    external = tmp_path / "Desktop"
    external.mkdir()
    xlsx = external / "账目.xlsx"
    _make_workbook(xlsx)
    original_bytes = xlsx.read_bytes()

    output = _run_script(
        {
            "workspace": str(ws),
            "output_dir": str(ws),
            "params": {
                "path": str(xlsx),
                "session_id": "s-x",
                "ops": [
                    {
                        "op": "set_cells",
                        "sheet": "9月",
                        "cells": [{"cell": "C2", "value": 666}],
                    }
                ],
            },
        }
    )
    assert output["success"] is True
    assert xlsx.read_bytes() == original_bytes  # 原文件未动
    copy_path = Path(output["filepath"])
    assert copy_path.parent == ws / "documents" / "edited"
    reloaded = load_workbook(str(copy_path))
    assert reloaded["9月"]["C2"].value == 666


def test_edit_xlsx_script_transaction_failure_untouched(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    xlsx = ws / "账目.xlsx"
    _make_workbook(xlsx)
    before = xlsx.read_bytes()
    output = _run_script(
        {
            "workspace": str(ws),
            "output_dir": str(ws),
            "params": {
                "path": str(xlsx),
                "session_id": "s-x",
                "ops": [{"op": "set_cells", "sheet": "不存在", "cells": [{"cell": "A1", "value": 1}]}],
            },
        }
    )
    assert output["success"] is False
    assert xlsx.read_bytes() == before
