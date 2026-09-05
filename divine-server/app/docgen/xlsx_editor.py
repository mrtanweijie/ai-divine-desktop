"""Excel 编辑引擎（edit_xlsx）：openpyxl 封装。

设计要点（docs/design/017-office-edit-closed-loop-20260906.md §4.4）：
- load_workbook 不传 data_only（默认保留公式）；openpyxl 3.1.5 已实测
  图表与公式往返无损（方案文档 §10）；
- 合并单元格只允许写左上角锚点，写非锚点坐标记 warning 并改写锚点；
- append_rows 自动探测现有数据区末行（逐列扫描真实值，不覆盖已有数据）；
- add_sheet 复用 spreadsheet 生成器的表头/数据样式，观感与生成链路一致。

定位采用 A1 坐标 + 表头文字辅助（内容匹配优先与 edit_docx 一致）。
"""

from __future__ import annotations

import difflib
import re
from typing import Any

from openpyxl.utils import column_index_from_string, get_column_letter

_A1_RE = re.compile(r"^([A-Za-z]{1,3})([1-9][0-9]*)$")


class XlsxOpError(ValueError):
    """操作定位/参数失败。candidates 为最相近候选。"""

    def __init__(self, message: str, candidates: list[str] | None = None) -> None:
        super().__init__(message)
        self.candidates = candidates or []


def _resolve_sheet(workbook, name: str | None):
    if not name or not str(name).strip():
        if len(workbook.sheetnames) == 1:
            return workbook[workbook.sheetnames[0]]
        raise XlsxOpError(
            f"工作簿有 {len(workbook.sheetnames)} 个工作表，请指定 sheet 名：{workbook.sheetnames}"
        )
    target = str(name).strip()
    if target in workbook.sheetnames:
        return workbook[target]
    lowered = {n.lower(): n for n in workbook.sheetnames}
    hit = lowered.get(target.lower())
    if hit:
        return workbook[hit]
    close = difflib.get_close_matches(target, workbook.sheetnames, n=3, cutoff=0.4)
    hint = f"，最相近：{close}" if close else f"，现有：{workbook.sheetnames}"
    raise XlsxOpError(f"未找到工作表 {target!r}{hint}")


def _parse_a1(cell: Any) -> tuple[int, int]:
    """A1 坐标 → (row, col)，1 基。"""
    match = _A1_RE.match(str(cell or "").strip().replace("$", ""))
    if not match:
        raise XlsxOpError(f"无效的单元格坐标: {cell!r}（需 A1 形式）")
    return int(match.group(2)), column_index_from_string(match.group(1).upper())


def _merged_anchor(ws, row: int, col: int) -> tuple[int, int] | None:
    """坐标落在合并区内时返回锚点 (row, col)；否则 None。"""
    for rng in ws.merged_cells.ranges:
        if rng.min_row <= row <= rng.max_row and rng.min_col <= col <= rng.max_col:
            return rng.min_row, rng.min_col
    return None


def _set_value(ws, row: int, col: int, value: Any, number_format: str | None, warnings: list[str]) -> None:
    anchor = _merged_anchor(ws, row, col)
    if anchor and anchor != (row, col):
        warnings.append(
            f"{get_column_letter(col)}{row} 位于合并区内，已写入锚点 "
            f"{get_column_letter(anchor[1])}{anchor[0]}"
        )
        row, col = anchor
    cell = ws.cell(row=row, column=col)
    cell.value = value
    if number_format:
        cell.number_format = str(number_format)


def _column_by_header(ws, header: str) -> int:
    """按表头文字解析列号：扫描前 3 行精确匹配，失败给相近候选。"""
    target = str(header or "").strip()
    if not target:
        raise XlsxOpError("header 为空")
    pool: dict[str, int] = {}
    for row in ws.iter_rows(min_row=1, max_row=3):
        for cell in row:
            text = "" if cell.value is None else str(cell.value).strip()
            if not text:
                continue
            if text == target:
                return cell.column
            pool.setdefault(text, cell.column)
    close = difflib.get_close_matches(target, list(pool), n=3, cutoff=0.4)
    hint = f"，最相近：{close}" if close else ""
    raise XlsxOpError(f"未找到表头 {target!r}{hint}")


def _last_data_row(ws) -> int:
    """逐列扫描真实值探测数据区末行（openpyxl 的 max_row 含格式化空单元格误差）。"""
    last = 0
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is not None and str(cell.value).strip() != "":
                last = max(last, cell.row)
    return last


def _apply_one(workbook, op: dict, report: dict) -> None:
    kind = str(op.get("op") or "").strip()

    if kind == "set_cells":
        default_sheet = op.get("sheet")
        cells = op.get("cells") or []
        if not isinstance(cells, list) or not cells:
            raise XlsxOpError("set_cells 缺少 cells 数组")
        for item in cells:
            if not isinstance(item, dict):
                raise XlsxOpError(f"cells 条目不是对象: {item!r}")
            ws = _resolve_sheet(workbook, item.get("sheet") or default_sheet)
            row, col = _parse_a1(item.get("cell"))
            if item.get("header"):
                col = _column_by_header(ws, str(item["header"]))
            _set_value(
                ws, row, col, item.get("value"), item.get("number_format"), report["warnings"]
            )
            report["hits"] += 1
        return

    if kind == "append_rows":
        ws = _resolve_sheet(workbook, op.get("sheet"))
        rows = op.get("rows") or []
        if not isinstance(rows, list) or not rows:
            raise XlsxOpError("append_rows 缺少 rows 数组")
        start = _last_data_row(ws) + 1
        for r_offset, record in enumerate(rows):
            values = record if isinstance(record, list) else [record]
            for c_offset, value in enumerate(values, 1):
                ws.cell(row=start + r_offset, column=c_offset, value=value)
        report["hits"] += len(rows)
        report["warnings"].append(f"已从第 {start} 行追加 {len(rows)} 行")
        return

    if kind == "add_sheet":
        _add_sheet(workbook, op, report)
        report["hits"] += 1
        return

    if kind == "set_formula":
        ws = _resolve_sheet(workbook, op.get("sheet"))
        formula = str(op.get("formula") or "").strip()
        if not formula:
            raise XlsxOpError("set_formula 缺少 formula")
        if not formula.startswith("="):
            formula = "=" + formula
        row, col = _parse_a1(op.get("cell"))
        _set_value(ws, row, col, formula, None, report["warnings"])
        report["hits"] += 1
        return

    raise XlsxOpError(f"未知操作类型: {kind!r}")


def _add_sheet(workbook, op: dict, report: dict) -> None:
    # 局部导入：样式函数属生成链路（tools/scripts），编辑引擎保持独立可测
    from app.tools.scripts.spreadsheet import (
        THEMES,
        _coerce_cell,
        _style_data_cell,
        _style_header_cell,
    )

    raw_name = str(op.get("name") or "").strip() or "Sheet"
    name = re.sub(r"[\\/*?:\[\]]", "_", raw_name)[:31] or "Sheet"
    base = name
    counter = 1
    while name in workbook.sheetnames:
        suffix = str(counter)
        name = f"{base[: 31 - len(suffix)]}{suffix}"
        counter += 1
    worksheet = workbook.create_sheet(title=name)

    headers = [str(h) for h in (op.get("headers") or [])]
    rows = op.get("rows") or []
    theme = THEMES.get(str(op.get("theme") or "blue"), THEMES["blue"])
    if headers:
        for col, header in enumerate(headers, 1):
            cell = worksheet.cell(row=1, column=col, value=header)
            _style_header_cell(cell, theme)
        worksheet.freeze_panes = "A2"
    for r_offset, record in enumerate(rows):
        values = record if isinstance(record, list) else [record]
        for c_offset, value in enumerate(values, 1):
            coerced, number_format, cell_kind = _coerce_cell(value, False)
            cell = worksheet.cell(row=(2 if headers else 1) + r_offset, column=c_offset)
            cell.value = coerced
            if number_format:
                cell.number_format = number_format
            _style_data_cell(
                cell, theme, banded=(r_offset % 2 == 1), kind=cell_kind or "text"
            )
    if headers and rows:
        worksheet.auto_filter.ref = worksheet.dimensions
    report["warnings"].append(f"已新增工作表 {name}")


def apply_ops(workbook, ops: list[dict]) -> dict:
    """顺序应用 ops；任一步失败抛 XlsxOpError（内存态未保存=事务中止）。"""
    report: dict[str, Any] = {"ops_applied": [], "hits": 0, "warnings": []}
    for index, raw in enumerate(ops or [], 1):
        if not isinstance(raw, dict):
            raise XlsxOpError(f"第 {index} 个操作不是对象: {raw!r}")
        try:
            _apply_one(workbook, raw, report)
        except XlsxOpError as exc:
            report["missed"] = [
                {"op_index": index, "op": str(raw.get("op")), "reason": str(exc)}
            ]
            exc.op_index = index  # type: ignore[attr-defined]
            raise
        report["ops_applied"].append(str(raw.get("op")))
    return report
