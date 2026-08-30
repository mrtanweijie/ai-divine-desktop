"""主题化表格渲染：表头强调色底白字 + 隔行斑马纹 + 数字右对齐。"""

from __future__ import annotations

from typing import Any

from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from .themes import rgb

MAX_COLS = 6
MAX_ROWS = 10  # 不含表头


def _is_number(text: str) -> bool:
    cleaned = str(text).replace(",", "").replace("%", "").replace("+", "") \
                        .replace("-", "").replace(".", "").strip()
    return cleaned.isdigit() if cleaned else False


def add_table(slide: Any, theme: dict[str, Any], spec: dict[str, Any],
              x: float, y: float, w: float, h: float) -> Any:
    columns = [str(c) for c in (spec.get("columns") or [])][:MAX_COLS]
    rows = [[str(cell) for cell in row] for row in (spec.get("rows") or [])][:MAX_ROWS]
    if not columns:
        raise ValueError("table 需要非空 columns")
    rows = [row[:len(columns)] + [""] * (len(columns) - len(row)) for row in rows]
    if not rows:
        rows = [[""] * len(columns)]

    n_rows = len(rows) + 1
    n_cols = len(columns)
    frame = slide.shapes.add_table(n_rows, n_cols, Inches(x), Inches(y),
                                   Inches(w), Inches(h))
    table = frame.table
    table.first_row = False
    table.horz_banding = False

    font_name = theme.get("font") or "PingFang SC"
    accent = theme.get("accent") or "2563EB"
    accent_light = theme.get("accent_light") or "EFF6FF"
    text_color = theme.get("text") or "1A1D24"

    row_h = min(0.5, max(0.34, h / n_rows))
    for row in table.rows:
        row.height = Inches(row_h)
    for col_index, width in enumerate(_column_widths(columns, rows, w)):
        table.columns[col_index].width = Inches(width)

    numeric_cols = {
        col_index for col_index in range(n_cols)
        if col_index > 0 and rows and all(_is_number(row[col_index]) for row in rows)
    }

    for col_index, label in enumerate(columns):
        cell = table.cell(0, col_index)
        cell.fill.solid()
        cell.fill.fore_color.rgb = rgb(accent)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        _write_cell(cell, label, 13, "FFFFFF", bold=True, font=font_name,
                    align=PP_ALIGN.RIGHT if col_index in numeric_cols else PP_ALIGN.LEFT)

    for row_index, row in enumerate(rows, start=1):
        for col_index, value in enumerate(row):
            cell = table.cell(row_index, col_index)
            cell.fill.solid()
            if row_index % 2 == 0:
                cell.fill.fore_color.rgb = rgb(accent_light)
            else:
                cell.fill.fore_color.rgb = rgb("FFFFFF")
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            _write_cell(cell, value, 12, text_color, font=font_name,
                        align=PP_ALIGN.RIGHT if col_index in numeric_cols else PP_ALIGN.LEFT)
    return frame


def _column_widths(columns: list[str], rows: list[list[str]],
                   total_w: float) -> list[float]:
    """首列（通常是维度名）稍宽，其余均分。"""
    if len(columns) <= 1:
        return [total_w] * len(columns)
    first = min(max(1.8, total_w * 0.22), total_w * 0.4)
    rest = (total_w - first) / (len(columns) - 1)
    return [first] + [rest] * (len(columns) - 1)


def _write_cell(cell: Any, text: str, size: float, color: str, *,
                bold: bool = False, font: str, align: PP_ALIGN) -> None:
    tf = cell.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = rgb(color)
    run.font.name = font
