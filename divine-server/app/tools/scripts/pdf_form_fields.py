"""pdf_form_fields 脚本：读取 PDF 的 AcroForm 表单字段清单。

只读工具（对偶于 document_outline）：输出字段名/类型/当前值/可选状态/页码，
供模型在 pdf_form_fill 前定位。字段清单为空 = 该 PDF 无交互表单
（扫描件不在能力范围）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.docgen.pdf.form import list_fields  # noqa: E402
from app.tools.office_files import OfficePathError, resolve_office_path  # noqa: E402


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"])
    params = data.get("params") or {}
    try:
        path = resolve_office_path(workspace, str(params.get("path") or ""), kind="pdf")
    except OfficePathError as exc:
        print(json.dumps({"success": False, "message": str(exc)}, ensure_ascii=False))
        return

    result = list_fields(path)
    lines: list[str] = []
    if not result["fields"]:
        lines.append(
            "该 PDF 没有交互表单（AcroForm）字段——可能是扫描件或纯文本排版，无法程序化填写"
        )
    for field in result["fields"][:60]:
        states = f" 可选: {'/'.join(field['states'])}" if field.get("states") else ""
        choices = f" 选项: {'/'.join(field['choices'])}" if field.get("choices") else ""
        value = f" 当前值: {field['value']!r}" if field["value"] not in (None, "") else ""
        lines.append(
            f"  [页{field['page']}] {field['name']} ({field['type']}){value}{states}{choices}"
        )
    print(
        json.dumps(
            {
                "success": True,
                "message": f"表单字段 {result['field_count']} 个" if result["fields"] else "未找到交互表单字段",
                "content": "\n".join(lines),
                "data": result,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
