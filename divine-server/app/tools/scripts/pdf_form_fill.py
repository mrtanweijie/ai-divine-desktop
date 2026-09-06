"""pdf_form_fill 脚本：按字段名填写 PDF 的 AcroForm 表单。

事务性：未命中字段名整体中止不写盘。外部文件先复制进
workspace/documents/edited/ 再填写（原文件零风险）；workspace 内文件
原地填写，编辑前字节级备份到 data_dir/backups/<session>/。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.docgen.pdf.form import PdfFormError, fill_fields, verify_filled  # noqa: E402
from app.tools.office_files import (  # noqa: E402
    OfficePathError,
    prepare_edit_target,
    resolve_office_path,
)

_VALUES_TYPES = ("Text", "ComboBox", "ListBox")


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"])
    params = data.get("params") or {}
    session_id = str(params.get("session_id") or "")
    values = params.get("values") or {}
    flatten = bool(params.get("flatten"))
    if not isinstance(values, dict) or not values:
        print(
            json.dumps(
                {"success": False, "message": "缺少 values（字段名→值 映射）"},
                ensure_ascii=False,
            )
        )
        return

    try:
        source = resolve_office_path(workspace, str(params.get("path") or ""), kind="pdf")
    except OfficePathError as exc:
        print(json.dumps({"success": False, "message": str(exc)}, ensure_ascii=False))
        return

    prep = prepare_edit_target(workspace, session_id, source)
    target: Path = prep["target"]
    try:
        doc, report = fill_fields(target, values, flatten=flatten)
        target.write_bytes(doc.tobytes())
        doc.close()
    except PdfFormError as exc:
        candidates = getattr(exc, "candidates", None) or []
        message = str(exc)
        print(
            json.dumps(
                {
                    "success": False,
                    "message": message,
                    "content": message + "。文件未做任何修改；可先调用 pdf_form_fields 查看字段清单。",
                    "data": {"candidates": candidates},
                },
                ensure_ascii=False,
            )
        )
        return
    except Exception as exc:  # noqa: BLE001 — 保存失败需清理现场
        _cleanup(prep)
        print(
            json.dumps(
                {"success": False, "message": f"填写失败: {exc}"}, ensure_ascii=False
            )
        )
        return

    problems = verify_filled(target, values)
    if problems:
        _cleanup(prep)
        print(
            json.dumps(
                {"success": False, "message": "；".join(problems)}, ensure_ascii=False
            )
        )
        return

    prefix = "已创建编辑副本" if prep["is_copy"] else "已填写"
    total = sum(item["count"] for item in report["filled"])
    message = f"{prefix}：{total} 个表单字段"
    detail = "；".join(f"{item['key']}×{item['count']}" for item in report["filled"])
    print(
        json.dumps(
            {
                "success": True,
                "message": message,
                "file_name": target.name,
                "filepath": str(target),
                "content": message + ("：" + detail if detail else ""),
                "data": {
                    **report,
                    "source_path": str(prep["original"]) if prep["is_copy"] else None,
                    "backup_path": str(prep["backup"]) if prep["backup"] else None,
                    "edited_copy": prep["is_copy"],
                },
            },
            ensure_ascii=False,
        )
    )


def _cleanup(prep: dict) -> None:
    """失败现场清理：副本删除，原地填写用填写前备份覆盖回去。"""
    target: Path = prep["target"]
    backup = prep.get("backup")
    if prep["is_copy"]:
        if target.exists():
            target.unlink(missing_ok=True)
    elif backup and Path(backup).is_file():
        target.write_bytes(Path(backup).read_bytes())


if __name__ == "__main__":
    main()
