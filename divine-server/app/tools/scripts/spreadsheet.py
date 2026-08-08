import json
import re
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


def safe_name(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "_", name).strip("._")
    if not cleaned:
        cleaned = fallback
    if not cleaned.endswith(".xlsx"):
        cleaned += ".xlsx"
    return cleaned


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"])
    params = data.get("params") or {}
    output_dir = workspace / "spreadsheets"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / safe_name(params.get("file_name") or "表格", "表格")

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "数据"
    headers = params.get("headers") or []
    rows = params.get("rows") or []
    if headers:
        sheet.append(headers)
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="0F766E")
    for row in rows:
        sheet.append(row)
    for column_cells in sheet.columns:
        width = max(len(str(cell.value or "")) for cell in column_cells) + 4
        sheet.column_dimensions[get_column_letter(column_cells[0].column)].width = min(
            width, 42
        )
    workbook.save(output_path)

    print(
        json.dumps(
            {
                "success": True,
                "message": "Excel 表格生成完成",
                "file_name": output_path.name,
                "filepath": str(output_path),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
