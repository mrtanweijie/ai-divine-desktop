"""document_outline 脚本：输出 docx/xlsx 可编辑结构大纲。

与代码侧 list_definitions 对偶（JSON in/out，见 docs/design/017-office-edit-closed-loop-20260906.md §4.3）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.docgen.outline import outline  # noqa: E402
from app.tools.office_files import OfficePathError, resolve_office_path  # noqa: E402


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"])
    params = data.get("params") or {}
    raw = str(params.get("path") or "")
    suffix = Path(raw.strip().strip('"').strip("'")).suffix.lower()
    try:
        if suffix in (".xlsx", ".xlsm"):
            path = resolve_office_path(workspace, raw, kind="sheet")
        elif suffix == ".pptx":
            path = resolve_office_path(workspace, raw, kind="slide")
        elif suffix == ".doc":
            raise OfficePathError(
                "暂不支持 .doc 老格式：请先另存为 .docx 再试"
            )
        else:
            path = resolve_office_path(workspace, raw)
        result = outline(path)
    except OfficePathError as exc:
        print(
            json.dumps({"success": False, "message": str(exc)}, ensure_ascii=False)
        )
        return
    lines: list[str] = []
    if result["kind"] == "docx":
        lines.append(f"段落 {len(result['paragraphs'])} 个、表格 {len(result['tables'])} 个")
        for paragraph in result["paragraphs"][:60]:
            lines.append(f"  #{paragraph['index']} [{paragraph['style']}] {paragraph['preview']}")
        for table in result["tables"]:
            headers = " | ".join(table["headers"][:6])
            lines.append(
                f"  表格{table['index']}：{table['rows']}行×{table['cols']}列，表头：{headers}"
            )
    elif result["kind"] == "pptx":
        lines.append(f"幻灯片 {len(result['slides'])} 页")
        for slide in result["slides"]:
            previews = " / ".join(slide["previews"][:2])
            lines.append(
                f"  第 {slide['index']} 页：{slide['title'] or '（无标题）'}"
                + (f" ｜ {previews}" if previews else "")
                + (" ｜ 有备注" if slide["has_note"] else "")
            )
    else:
        lines.append(f"工作表 {len(result['sheets'])} 个")
        for sheet in result["sheets"]:
            headers = " | ".join(h for h in sheet["headers"][:8] if h)
            lines.append(
                f"  [{sheet['name']}] 范围 {sheet['dims']}，"
                f"公式 {sheet['has_formulas']} 个，图表 {'有' if sheet['has_chart'] else '无'}"
                + (f"，表头：{headers}" if headers else "")
            )
    print(
        json.dumps(
            {
                "success": True,
                "message": "文档大纲读取完成",
                "content": "\n".join(lines),
                "data": result,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
