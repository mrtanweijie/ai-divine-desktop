"""Excel 编辑引擎（edit_xlsx / fill_template 的 xlsx 分支）：openpyxl 封装。

设计要点（docs/design/017-office-edit-closed-loop-20260906.md §4.4）：
- load_workbook 不传 data_only（默认保留公式）；openpyxl 3.1.5 已实测
  图表与公式往返无损（方案文档 §10）；
- 合并单元格只允许写左上角锚点，写非锚点坐标记 warning 并改写锚点；
- append_rows 自动探测现有数据区末行（逐列扫描真实值，不覆盖已有数据）；
- add_sheet 复用 spreadsheet 生成器的表头/数据样式，观感与生成链路一致；
- fill_template 填充所有 sheet 的字符串单元格 {{key}}，公式单元格不触碰
  （设计 §4.1 的 xlsx 分支）。

定位采用 A1 坐标 + 表头文字辅助（内容匹配优先与 edit_docx 一致）。
"""

from __future__ import annotations

import difflib
import re
from copy import copy
from pathlib import Path
from typing import Any

from openpyxl.utils import column_index_from_string, get_column_letter, range_boundaries

_A1_RE = re.compile(r"^([A-Za-z]{1,3})([1-9][0-9]*)$")
# 与 docgen/word/editor.py 的占位符正则保持一致（xlsx 单元格是单字符串，
# 无 run 结构，直接字符串替换即可）
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.\-\u4e00-\u9fff]+)\s*\}\}")


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


def _apply_one(workbook, op: dict, report: dict, workspace=None) -> None:
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

    if kind == "delete_rows":
        ws = _resolve_sheet(workbook, op.get("sheet"))
        start = op.get("start")
        if not isinstance(start, int) or start < 1:
            raise XlsxOpError(f"delete_rows 需要有效的 start 行号（1 基），收到: {start!r}")
        count = op.get("count") if isinstance(op.get("count"), int) and op["count"] > 0 else 1
        if start > _last_data_row(ws):
            raise XlsxOpError(
                f"起始行 {start} 超出数据区（末行 {_last_data_row(ws)}）"
            )
        ws.delete_rows(start, count)
        report["hits"] += 1
        report["warnings"].append(f"已删除第 {start} 行起的 {count} 行")
        return

    if kind == "delete_sheet":
        name = str(op.get("name") or "").strip()
        ws = _resolve_sheet(workbook, name)
        if len(workbook.sheetnames) <= 1:
            raise XlsxOpError("工作簿至少要保留一个工作表，无法删除")
        workbook.remove(ws)
        report["hits"] += 1
        report["warnings"].append(f"已删除工作表 {ws.title}")
        return

    if kind == "style_cells":
        _style_cells(workbook, op, report)
        report["hits"] += 1
        return

    if kind == "add_chart":
        _add_chart(workbook, op, report)
        report["hits"] += 1
        return

    if kind == "insert_image":
        _insert_image(workbook, op, report, workspace)
        report["hits"] += 1
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


_CHART_TYPES = {
    "bar": ("BarChart", "bar"),
    "column": ("BarChart", "col"),
    "line": ("LineChart", None),
    "area": ("AreaChart", None),
    "pie": ("PieChart", None),
    "doughnut": ("DoughnutChart", None),
    "scatter": ("ScatterChart", None),
}


def _add_chart(workbook, op: dict, report: dict) -> None:
    """在指定锚点插入原生图表（PowerPoint/Excel 内可二次编辑）。"""
    from openpyxl.chart import (
        AreaChart,
        BarChart,
        DoughnutChart,
        LineChart,
        PieChart,
        ScatterChart,
    )

    ws = _resolve_sheet(workbook, op.get("sheet"))
    chart_type = str(op.get("type") or "column").strip().lower()
    if chart_type not in _CHART_TYPES:
        raise XlsxOpError(
            f"图表类型无效: {chart_type!r}，可选 {sorted(_CHART_TYPES)}"
        )
    anchor = str(op.get("anchor") or "").strip()
    if not anchor:
        raise XlsxOpError("add_chart 缺少 anchor（图表左上角单元格，如 E2）")
    _parse_a1(anchor)  # 校验坐标形态

    cls_name, bar_kind = _CHART_TYPES[chart_type]
    cls = {"BarChart": BarChart, "LineChart": LineChart, "AreaChart": AreaChart,
           "PieChart": PieChart, "DoughnutChart": DoughnutChart,
           "ScatterChart": ScatterChart}[cls_name]
    chart = cls()
    if bar_kind:
        chart.type = bar_kind
    if str(op.get("title") or "").strip():
        chart.title = str(op["title"])

    series = op.get("series") or []
    if not isinstance(series, list) or not series:
        raise XlsxOpError("add_chart 缺少 series（数据引用列表）")
    for entry in series:
        if not isinstance(entry, dict) or not entry.get("ref"):
            raise XlsxOpError(f"series 条目缺少 ref: {entry!r}")
        data = _reference(ws, str(entry["ref"]), single_column=True)
        chart.add_data(data, titles_from_data=False)
        if entry.get("name") and chart.series:
            from openpyxl.chart.series import SeriesLabel  # noqa: PLC0415

            # 名称用字面字符串而非引用，避免依赖辅助单元格
            chart.series[-1].tx = SeriesLabel(v=str(entry["name"]))
    if op.get("categories_ref") and chart.series:
        chart.set_categories(_reference(ws, str(op["categories_ref"]), single_column=True))
    ws.add_chart(chart, anchor)
    report["warnings"].append(f"已插入 {chart_type} 图表至 {anchor}")


def _reference(ws, ref: str, *, single_column: bool):
    """把 "B2:B13" 形式的纯范围解析为当前 sheet 的 Reference。

    openpyxl 的 range_string 形式要求带 "sheetname!" 前缀，这里统一在
    调用侧绑定 sheet，允许模型只写范围；single_column 校验单列引用。
    """
    text = str(ref or "").strip()
    if "!" in text:  # 容错：模型可能带 sheet 前缀，剥离后仍绑定当前 sheet
        text = text.split("!")[-1]
    from openpyxl.chart import Reference  # noqa: PLC0415 — 与其余图表导入同策略

    try:
        min_col, min_row, max_col, max_row = range_boundaries(text)
    except Exception as exc:  # noqa: BLE001 — 转成面向模型的报错
        raise XlsxOpError(f"范围无效: {ref!r}（需 A1:B13 形式）") from exc
    if single_column and min_col != max_col:
        raise XlsxOpError(
            f"范围 {ref!r} 跨多列——每个系列（或分类轴）只允许一列，多列请拆成多个 series"
        )
    return Reference(ws, min_col=min_col, min_row=min_row, max_col=max_col, max_row=max_row)


def _insert_image(workbook, op: dict, report: dict, workspace=None) -> None:
    """在指定锚点嵌入图片（嵌入后图片数据随文件保存，不依赖原路径）。"""
    from openpyxl.drawing.image import Image as XLImage

    ws = _resolve_sheet(workbook, op.get("sheet"))
    raw = str(op.get("image_path") or "").strip()
    if not raw:
        raise XlsxOpError("insert_image 缺少 image_path")
    image_path = Path(raw)
    if not image_path.is_absolute() and workspace is not None:
        image_path = Path(workspace) / image_path
    image_path = image_path.resolve()
    if not image_path.is_file():
        raise XlsxOpError(f"图片不存在: {image_path}")
    if image_path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".gif", ".bmp"):
        raise XlsxOpError(f"图片格式不支持: {image_path.suffix}（支持 png/jpg/jpeg/gif/bmp）")
    anchor = str(op.get("anchor") or "A1").strip()
    _parse_a1(anchor)
    image = XLImage(str(image_path))
    if isinstance(op.get("width"), (int, float)):
        image.width = int(op["width"])
    if isinstance(op.get("height"), (int, float)):
        image.height = int(op["height"])
    ws.add_image(image, anchor)
    report["warnings"].append(f"已嵌入图片 {image_path.name} 至 {anchor}")


_STYLE_MAX_CELLS = 20000
_ALIGN_VALUES = ("left", "center", "right")
_HEX_COLOR_RE = re.compile(r"^#?([0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$")


def _normalize_hex(color: str, what: str) -> str:
    cleaned = str(color or "").strip().lstrip("#").upper()
    if not _HEX_COLOR_RE.match("#" + cleaned):
        raise XlsxOpError(f"{what} 颜色格式无效: {color!r}（需 6/8 位十六进制，如 FF0000）")
    return cleaned


def _style_cells(workbook, op: dict, report: dict) -> None:
    """对范围（或单格）应用字符/填充/对齐/数字格式样式。

    样式通过 copy 现有对象后局部修改，不清掉单元格已有的其他格式。
    """
    from openpyxl.styles import PatternFill

    ws = _resolve_sheet(workbook, op.get("sheet"))
    rng = str(op.get("range") or "").strip()
    if "!" in rng:
        rng = rng.split("!")[-1]
    provided = {
        key: op[key]
        for key in ("bold", "italic", "underline", "font_size", "font_color",
                    "fill_color", "align", "number_format")
        if op.get(key) is not None
    }
    if not provided:
        raise XlsxOpError(
            "style_cells 未提供任何样式参数（bold/italic/underline/font_size/"
            "font_color/fill_color/align/number_format）"
        )
    if "align" in provided and str(provided["align"]).lower() not in _ALIGN_VALUES:
        raise XlsxOpError(
            f"align 无效: {provided['align']!r}，可选 {'/'.join(_ALIGN_VALUES)}"
        )
    for color_key in ("font_color", "fill_color"):
        if color_key in provided:
            provided[color_key] = _normalize_hex(provided[color_key], color_key)
    try:
        min_col, min_row, max_col, max_row = range_boundaries(rng)
    except Exception as exc:  # noqa: BLE001 — 转成面向模型的报错
        raise XlsxOpError(f"范围无效: {rng!r}（需 A1:C10 或 B2 形式）") from exc
    if min_row is None or max_row is None:
        raise XlsxOpError(
            f"范围 {rng!r} 是整列/整行写法——请给出明确行范围，如 A1:A200"
        )
    total = (max_col - min_col + 1) * (max_row - min_row + 1)
    if total > _STYLE_MAX_CELLS:
        raise XlsxOpError(
            f"范围过大（{total} 个单元格，上限 {_STYLE_MAX_CELLS}）——整列样式请给出明确行范围，如 A1:A200"
        )
    count = 0
    for row in ws.iter_rows(min_row=min_row, max_row=max_row, min_col=min_col, max_col=max_col):
        for cell in row:
            font = copy(cell.font)
            if "bold" in provided:
                font.bold = bool(provided["bold"])
            if "italic" in provided:
                font.italic = bool(provided["italic"])
            if "underline" in provided:
                font.underline = "single" if provided["underline"] else None
            if "font_size" in provided:
                font.size = provided["font_size"]
            if "font_color" in provided:
                font.color = provided["font_color"]
            cell.font = font
            if "fill_color" in provided:
                cell.fill = PatternFill("solid", fgColor=provided["fill_color"])
            if "align" in provided:
                alignment = copy(cell.alignment)
                alignment.horizontal = str(provided["align"]).lower()
                cell.alignment = alignment
            if "number_format" in provided:
                cell.number_format = str(provided["number_format"])
            count += 1
    report["warnings"].append(f"已为 {count} 个单元格应用样式")


def apply_ops(workbook, ops: list[dict], *, workspace=None) -> dict:
    """顺序应用 ops；任一步失败抛 XlsxOpError（内存态未保存=事务中止）。"""
    report: dict[str, Any] = {"ops_applied": [], "hits": 0, "warnings": []}
    for index, raw in enumerate(ops or [], 1):
        if not isinstance(raw, dict):
            raise XlsxOpError(f"第 {index} 个操作不是对象: {raw!r}")
        try:
            _apply_one(workbook, raw, report, workspace)
        except XlsxOpError as exc:
            report["missed"] = [
                {"op_index": index, "op": str(raw.get("op")), "reason": str(exc)}
            ]
            exc.op_index = index  # type: ignore[attr-defined]
            raise
        report["ops_applied"].append(str(raw.get("op")))
    return report


# ---------------------------------------------------------------------------
# fill_template 的 xlsx 分支：所有 sheet 字符串单元格 {{key}} 替换
# ---------------------------------------------------------------------------


def fill_template(workbook, values: dict[str, str]) -> dict:
    """填充所有 sheet 字符串单元格中的 {{key}}；公式单元格不触碰。

    （设计 §4.1 xlsx 分支：仅做值替换；list_values 行展开仅支持 docx，
    传入时记 warning。）
    """
    values = {k: str(v) for k, v in (values or {}).items()}
    report: dict[str, Any] = {"filled": [], "missing_keys": [], "warnings": []}
    hit_counter: dict[str, int] = {}

    for worksheet in workbook.worksheets:
        for row in worksheet.iter_rows():
            for cell in row:
                value = cell.value
                if not isinstance(value, str) or not value or value.startswith("="):
                    continue
                new_value = value
                for key, val in values.items():
                    pattern = re.compile(r"\{\{\s*" + re.escape(key) + r"\s*\}\}")
                    new_value, hits = pattern.subn(val, new_value)
                    if hits:
                        hit_counter[key] = hit_counter.get(key, 0) + hits
                if new_value != value:
                    cell.value = new_value

    filled_keys = set(hit_counter)
    missing = [k for k in values if k not in filled_keys]

    # 残留占位符（文档里存在但 values 未提供值）——提示模型向用户澄清
    residual = sorted(
        {
            match.group(1)
            for worksheet in workbook.worksheets
            for row in worksheet.iter_rows()
            for cell in row
            if isinstance(cell.value, str)
            for match in _PLACEHOLDER_RE.finditer(cell.value)
        }
        - filled_keys
    )
    for key in residual:
        report["warnings"].append(f"占位符 {key} 未提供值，已保留原文")

    report["filled"] = [
        {"key": key, "count": count} for key, count in sorted(hit_counter.items())
    ]
    report["missing_keys"] = missing
    return report
