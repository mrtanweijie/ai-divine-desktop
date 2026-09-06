"""PDF 交互表单（AcroForm）读取与填写引擎（pdf_form_fields / pdf_form_fill）。

边界（诚实告知）：只支持 AcroForm 交互表单；扫描件"画出来的格子"没有
字段可填——字段清单为空时即为该信号。填写引擎基于 pymupdf（现有依赖），
中文值、复选框勾选均已在冒烟中验证。

事务性：填写阶段收集全部未命中字段名，存在未命中即抛 PdfFormError，
调用方不保存即整体中止。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_TRUTHY = {"true", "yes", "1", "on", "y", "是", "勾选", "✓"}


class PdfFormError(ValueError):
    """表单操作失败。candidates 为现有字段名，供模型修正。"""

    def __init__(self, message: str, candidates: list[str] | None = None) -> None:
        super().__init__(message)
        self.candidates = candidates or []


def list_fields(path: Path) -> dict[str, Any]:
    """枚举 PDF 的 AcroForm 字段：名称/类型/当前值/可选状态/页码。

    "name::选项" 分组命名的控件（表单单选组，见 pdf_form_generate）聚合为
    一个逻辑字段：name=组名，type=choice-list，choices=选项。
    """
    import pymupdf

    doc = pymupdf.open(str(path))
    fields: list[dict[str, Any]] = []
    index_by_name: dict[str, int] = {}
    try:
        for page_no, page in enumerate(doc, 1):
            for widget in page.widgets() or []:
                name = widget.field_name or ""
                if "::" in name:
                    base, option = name.split("::", 1)
                    if base in index_by_name:
                        entry = fields[index_by_name[base]]
                        if option not in entry["choices"]:
                            entry["choices"].append(option)
                    else:
                        index_by_name[base] = len(fields)
                        entry = {
                            "name": base,
                            "type": "choice-list",
                            "value": "",
                            "page": page_no,
                            "choices": [option],
                        }
                        fields.append(entry)
                    if str(widget.field_value) not in ("", "Off", "None"):
                        entry["value"] = option
                    continue
                entry: dict[str, Any] = {
                    "name": name,
                    "type": widget.field_type_string,
                    "value": widget.field_value,
                    "page": page_no,
                }
                if widget.field_type_string in ("CheckBox", "RadioButton"):
                    states = widget.button_states() or {}
                    entry["states"] = states.get("normal") or []
                if widget.field_type_string in ("ComboBox", "ListBox"):
                    choices = widget.choice_values
                    if choices:
                        entry["choices"] = [str(c) for c in choices]
                fields.append(entry)
    finally:
        doc.close()
    return {"kind": "pdf_form", "field_count": len(fields), "fields": fields}


def fill_fields(
    path: Path, values: dict[str, Any], *, flatten: bool = False
) -> tuple[Any, dict[str, Any]]:
    """按字段名填写表单；返回 (填写后的 pymupdf Document, report)。

    - 未命中字段名整体抛 PdfFormError（事务中止，调用方不保存）；
    - CheckBox/RadioButton：truthy 语义勾选（on_state），falsy 取消（Off）；
    - ComboBox/ListBox：值必须在 choices 内，否则视为未命中；
    - flatten=True 时把表单烧进页面文本（之后不可再编辑，需 pymupdf 支持 bake）。
    调用方负责保存（doc.tobytes() / doc.save）。
    """
    import pymupdf

    normalized = {
        str(k).strip(): "" if v is None else str(v)
        for k, v in (values or {}).items()
    }
    if not normalized:
        raise PdfFormError("缺少 values（字段名→值 映射）")

    doc = pymupdf.open(str(path))
    report: dict[str, Any] = {"filled": [], "missed": [], "warnings": []}
    hit_counter: dict[str, int] = {}
    missed: set[str] = set(normalized.keys())  # 以待填键为种子，填到即剔除

    for page in doc:
        for widget in page.widgets() or []:
            name = widget.field_name or ""
            # 分组单选（pdf_form_generate 生成的 "name::选项" 控件）：
            # 值等于选项时勾选该控件，同组其余控件取消（互斥）。
            base, group_sep, option = name.partition("::")
            if group_sep:
                target = normalized.get(base)
                if target is None:
                    continue
                checked = option == target
                widget.field_value = bool(checked)
                widget.update()
                if checked:
                    hit_counter[base] = hit_counter.get(base, 0) + 1
                    missed.discard(base)
                continue
            if name not in normalized:
                continue
            target = normalized[name]
            ftype = widget.field_type_string
            if ftype == "CheckBox" or ftype == "RadioButton":
                # RadioButton 是选项组：按选项值匹配（如 "男"/"女"）；
                # CheckBox 用 truthy 语义（true/1/是 → 勾选）。
                states = (widget.button_states() or {}).get("normal") or []
                on_states = [st for st in states if st and st != "Off"]
                truthy = target.strip().lower() in _TRUTHY
                if target in on_states:
                    widget.field_value = target
                elif on_states and truthy:
                    widget.field_value = widget.on_state()
                else:
                    widget.field_value = False
                widget.update()
                hit_counter[name] = hit_counter.get(name, 0) + 1
                missed.discard(name)
                continue
            if ftype in ("ComboBox", "ListBox") and widget.choice_values:
                choices = [str(c) for c in widget.choice_values]
                if target not in choices:
                    missed.add(name)
                    continue
            widget.field_value = target
            widget.update()
            hit_counter[name] = hit_counter.get(name, 0) + 1
            missed.discard(name)

    if missed:
        existing = sorted(
            {
                w.field_name
                for p in doc
                for w in (p.widgets() or [])
                if w.field_name
            }
        )
        doc.close()
        raise PdfFormError(
            f"未找到字段: {', '.join(sorted(missed))}", candidates=existing
        )

    if flatten:
        if hasattr(doc, "bake"):
            doc.bake()
            report["warnings"].append("已 flatten：表单值烧进页面，不可再编辑")
        else:
            report["warnings"].append("当前 pymupdf 不支持 flatten，已保留交互字段")

    report["filled"] = [
        {"key": key, "count": count} for key, count in sorted(hit_counter.items())
    ]
    return doc, report


def verify_filled(path: Path, values: dict[str, Any]) -> list[str]:
    """改后自检：重开 PDF，断言已填字段的值与预期一致。"""
    import pymupdf

    normalized = {str(k).strip(): "" if v is None else str(v) for k, v in (values or {}).items()}
    try:
        doc = pymupdf.open(str(path))
        actual: dict[str, str] = {}
        groups: dict[str, dict[str, str]] = {}
        for page in doc:
            for widget in page.widgets() or []:
                name = widget.field_name or ""
                value = str(widget.field_value)
                if "::" in name:
                    base, option = name.split("::", 1)
                    groups.setdefault(base, {})[option] = value
                else:
                    actual[name] = value
        doc.close()
    except Exception as exc:  # noqa: BLE001 — 重开失败即产物不可交付
        return [f"产物重开失败（可能已损坏）: {exc}"]
    problems = []
    for key, expected in normalized.items():
        if key in groups:
            checked = [opt for opt, v in groups[key].items() if v not in ("", "Off", None)]
            if expected not in checked:
                problems.append(
                    f"字段 {key} 未选中 {expected!r}（当前勾选: {'/'.join(checked) or '无'}）"
                )
            continue
        got = actual.get(key)
        if got is None:
            continue  # 该字段不属于本 PDF（由 missed 流程负责）
        if expected.strip().lower() in _TRUTHY and got not in ("", "Off"):
            continue  # 复选框勾选语义
        if got != expected:
            problems.append(f"字段 {key} 未写入（当前值 {got!r}）")
    return problems
