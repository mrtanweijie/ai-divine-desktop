"""Word 文档 run 级编辑引擎（edit_docx / fill_template 共用）。

设计原则（docs/design/017-office-edit-closed-loop-20260906.md §5.1）：
- run 级操作保样式，绝不整段重建（paragraph.text = ... 会把全段压成单 run）；
- 匹配串完整落在单个 run 内 → 只改 run.text，样式天然保留；
- 跨 run 命中 → 被覆盖 run 格式一致则合并替换；不一致则用首个 run 的格式
  承载新文本、清空 span 内其余 run（与 Word 自身查找替换行为一致），
  并在报告里如实上报 cross_run。

定位采用"内容匹配优先"（§5.2）：所有段落/表格定位都基于文本匹配，
未命中时给出最相近候选（编辑距离），供模型自行修正重试。
"""

from __future__ import annotations

import copy
import difflib
import re
from typing import Any

from docx.text.paragraph import Paragraph
from docx.text.run import Run


class EditOpError(ValueError):
    """操作定位失败。candidates 为最相近候选，供模型修正。"""

    def __init__(self, message: str, candidates: list[str] | None = None) -> None:
        super().__init__(message)
        self.candidates = candidates or []


# ---------------------------------------------------------------------------
# 段落偏移与 run span 工具
# ---------------------------------------------------------------------------


def _run_spans(paragraph: Paragraph) -> list[tuple[Run, int, int]]:
    """段落内每个 run 的全局文本偏移 [(run, start, end)]。"""
    spans: list[tuple[Run, int, int]] = []
    pos = 0
    for run in paragraph.runs:
        length = len(run.text)
        spans.append((run, pos, pos + length))
        pos += length
    return spans


def _find_matches(text: str, find: str, *, regex: bool, all_matches: bool) -> list[tuple[int, int]]:
    if regex:
        try:
            pattern = re.compile(find)
        except re.error as exc:
            raise EditOpError(f"正则表达式无效: {exc}") from exc
        matches = list(pattern.finditer(text))[:20]
        return [(m.start(), m.end()) for m in matches] if matches else []
    # 大小写不敏感匹配（lower() 保持长度，不破坏偏移映射）
    lowered = text.lower()
    needle = find.lower()
    if not needle:
        return []
    spans: list[tuple[int, int]] = []
    pos = 0
    limit = len(text) if all_matches else 1
    while len(spans) < limit:
        idx = lowered.find(needle, pos)
        if idx < 0:
            break
        spans.append((idx, idx + len(needle)))
        pos = idx + len(needle)
    return spans


def _run_format_key(run: Run) -> tuple:
    """用于跨 run 格式一致性比较的关键属性。"""
    font = run.font
    color = None
    try:
        if font.color and font.color.rgb is not None:
            color = str(font.color.rgb)
    except Exception:  # noqa: BLE001 — 颜色读取失败按 None 处理
        color = None
    return (
        font.name,
        font.size.pt if font.size else None,
        font.bold,
        font.italic,
        font.underline,
        color,
    )


def replace_in_paragraph(
    paragraph: Paragraph,
    find: str,
    replace: str,
    *,
    all_matches: bool = False,
    regex: bool = False,
) -> tuple[int, int]:
    """段落内查找替换，run 级保样式。返回 (hits, cross_run)。"""
    text = paragraph.text
    spans = _find_matches(text, find, regex=regex, all_matches=all_matches)
    if not spans:
        return 0, 0
    hits = 0
    cross_run = 0
    # 从后往前替换，前面的偏移不受影响
    for start, end in reversed(spans):
        overlapping = [
            (run, s, e)
            for run, s, e in _run_spans(paragraph)
            if s < end and e > start
        ]
        if not overlapping:
            continue
        hits += 1
        if len(overlapping) == 1:
            run, s, _ = overlapping[0]
            local_start = start - s
            local_end = end - s
            run.text = run.text[:local_start] + replace + run.text[local_end:]
            continue
        # 跨 run：格式一致则透明合并；不一致则用首个 run 的格式承载新文本
        formats = {_run_format_key(run) for run, _, _ in overlapping}
        if len(formats) > 1:
            cross_run += 1
        first_run, first_start, _ = overlapping[0]
        last_run, last_start, _ = overlapping[-1]
        first_run.text = (
            first_run.text[: start - first_start] + replace
        )
        for run, _, run_end in overlapping[1:-1]:
            run.text = ""
        last_run.text = last_run.text[end - last_start :]
    return hits, cross_run


def set_paragraph_text(paragraph: Paragraph, text: str) -> None:
    """整段替换文字，样式取段首 run（不重建段落，保段落级样式）。"""
    runs = paragraph.runs
    if not runs:
        paragraph.add_run(text)
        return
    runs[0].text = text
    for run in runs[1:]:
        run.text = ""


def delete_paragraph(paragraph: Paragraph) -> None:
    element = paragraph._element
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


# ---------------------------------------------------------------------------
# 定位：段落 / 表格（内容匹配优先 + 最相近候选）
# ---------------------------------------------------------------------------


def _closest(target: str, pool: list[str], limit: int = 3) -> list[str]:
    if not pool:
        return []
    return difflib.get_close_matches(target, pool, n=limit, cutoff=0.4)


def iter_document_paragraphs(document) -> list[Paragraph]:
    """正文段落（不含表格内段落）。"""
    return list(document.paragraphs)


def locate_paragraph(
    document,
    needle: str,
    *,
    what: str = "段落",
) -> Paragraph:
    """按包含匹配定位第一个命中的正文段落。"""
    needle = (needle or "").strip()
    if not needle:
        raise EditOpError(f"{what}定位文本为空")
    candidates: list[str] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        if needle in text or needle.lower() in text.lower():
            return paragraph
        candidates.append(text)
    close = _closest(needle, candidates)
    hint = f"，最相近：{close}" if close else ""
    raise EditOpError(f"未找到包含 {needle!r} 的{what}{hint}")


def locate_table(document, table: int | None) -> Any:
    tables = document.tables
    if not tables:
        raise EditOpError("文档中没有表格")
    if table is None:
        if len(tables) == 1:
            return tables[0]
        raise EditOpError(
            f"文档有 {len(tables)} 个表格，请用 table 序号指明（document_outline 可查看）"
        )
    if not isinstance(table, int) or table < 1 or table > len(tables):
        raise EditOpError(f"table 序号无效: {table}，有效范围 1-{len(tables)}")
    return tables[table - 1]


def locate_column(table, header: str | None) -> int:
    """按表头文字定位列号；失败时给出相近表头候选。"""
    if not table.rows:
        raise EditOpError("表格没有数据行")
    headers = [cell.text.strip() for cell in table.rows[0].cells]
    header_clean = (header or "").strip()
    if header_clean:
        lowered = [h.lower() for h in headers]
        if header_clean.lower() in lowered:
            return lowered.index(header_clean.lower())
        close = _closest(header_clean, [h for h in headers if h])
        hint = f"，现有表头：{close or headers}" if headers else ""
        raise EditOpError(f"未找到表头 {header_clean!r}{hint}")
    raise EditOpError(f"需要 header 或 col 定位列，表头有：{headers}")


def locate_row(table, row_key: str | None, row: int | None, col: int) -> int:
    """按首列（或指定列）文本定位行号（返回 table.rows 下标，含表头行）。"""
    if row_key:
        key_clean = row_key.strip()
        pool: list[str] = []
        for r_index, table_row in enumerate(table.rows):
            try:
                cell_text = table_row.cells[col].text.strip()
            except IndexError:
                continue
            if not cell_text:
                continue
            if key_clean == cell_text or key_clean.lower() == cell_text.lower():
                return r_index
            pool.append(cell_text)
        close = _closest(key_clean, pool)
        hint = f"，最相近：{close}" if close else ""
        raise EditOpError(f"未找到首列为 {key_clean!r} 的行{hint}")
    if row is not None:
        if row < 1 or row > len(table.rows):
            raise EditOpError(f"row 序号无效: {row}，有效范围 1-{len(table.rows)}")
        return row - 1
    raise EditOpError("需要 row_key 或 row 定位行")


def set_cell_text(cell, text: str) -> None:
    """单元格替换文字，样式取原首 run；空单元格用默认格式。"""
    paragraphs = cell.paragraphs
    if paragraphs and paragraphs[0].runs:
        set_paragraph_text(paragraphs[0], text)
        # 清掉单元格内其余段落的多余 run，保留段落结构
        for extra in paragraphs[1:]:
            for run in extra.runs:
                run.text = ""
        return
    cell.text = text


# ---------------------------------------------------------------------------
# 操作执行（顺序应用；任一步失败抛 EditOpError，调用方不写盘即整体中止）
# ---------------------------------------------------------------------------


def _apply_one(document, op: dict, report: dict, workspace, theme_id: str) -> None:
    kind = str(op.get("op") or "").strip()
    if kind == "replace_text":
        find = str(op.get("find") or "")
        if not find:
            raise EditOpError("replace_text 缺少 find")
        paragraph = locate_paragraph(document, str(op.get("match") or find))
        hits, cross = replace_in_paragraph(
            paragraph,
            find,
            str(op.get("replace") or ""),
            all_matches=bool(op.get("all")),
            regex=bool(op.get("regex")),
        )
        if hits == 0:
            raise EditOpError(
                f"段落 {paragraph.text.strip()[:30]!r} 内未找到 {find!r}"
            )
        report["hits"] += hits
        report["cross_run"] += cross
        return
    if kind == "set_paragraph":
        paragraph = locate_paragraph(document, str(op.get("match") or ""))
        set_paragraph_text(paragraph, str(op.get("text") or ""))
        report["hits"] += 1
        return
    if kind == "set_table_cell":
        table = locate_table(document, op.get("table"))
        col = op.get("col") if isinstance(op.get("col"), int) else None
        if col is not None and (col < 1 or col > len(table.columns)):
            raise EditOpError(f"col 序号无效: {col}")
        col_index = (
            col - 1 if col is not None else locate_column(table, op.get("header"))
        )
        row_index = locate_row(table, op.get("row_key"), op.get("row"), 0)
        set_cell_text(table.rows[row_index].cells[col_index], str(op.get("text") or ""))
        report["hits"] += 1
        return
    if kind == "append_section":
        _append_section(document, op, workspace, theme_id)
        report["hits"] += 1
        return
    if kind == "delete_paragraph":
        paragraph = locate_paragraph(document, str(op.get("match") or op.get("find") or ""))
        text = paragraph.text.strip()
        delete_paragraph(paragraph)
        report["hits"] += 1
        report["warnings"].append(f"已删除段落：{text[:30]}")
        return
    raise EditOpError(f"未知操作类型: {kind!r}")


def _append_section(document, op: dict, workspace, theme_id: str) -> None:
    # 局部导入：elements/themes 属于生成链路，编辑引擎保持独立可测
    from .elements import add_body_text
    from .themes import add_styled_table

    heading = str(op.get("heading") or "").strip()
    level = op.get("level") if isinstance(op.get("level"), int) else 2
    if heading:
        document.add_heading(heading, level=min(max(level, 1), 3))
    body = str(op.get("body") or "").strip()
    items = [str(i) for i in (op.get("items") or []) if str(i).strip()]
    headers = [str(h) for h in (op.get("headers") or []) if str(h).strip()]
    rows = op.get("rows") or []
    if headers and rows:
        add_styled_table(document, headers, rows, theme_id or "universal")
    if items:
        style = "List Bullet"
        for item in items:
            document.add_paragraph(item, style=style)
    if body:
        add_body_text(document, body, workspace, theme_id or "universal")
    if not (heading or body or items or (headers and rows)):
        raise EditOpError("append_section 缺少 heading/body/items/headers+rows")


def apply_ops(
    document,
    ops: list[dict],
    *,
    workspace=None,
    theme_id: str | None = None,
) -> dict:
    """顺序应用 ops；任一步定位失败抛 EditOpError（内存态未保存=事务中止）。"""
    report: dict[str, Any] = {
        "ops_applied": [],
        "hits": 0,
        "cross_run": 0,
        "warnings": [],
    }
    for index, raw in enumerate(ops or [], 1):
        if not isinstance(raw, dict):
            raise EditOpError(f"第 {index} 个操作不是对象: {raw!r}")
        try:
            _apply_one(document, raw, report, workspace, theme_id)
        except EditOpError as exc:
            report["missed"] = [
                {"op_index": index, "op": str(raw.get("op")), "reason": str(exc)}
            ]
            exc.op_index = index  # type: ignore[attr-defined]
            raise
        report["ops_applied"].append(str(raw.get("op")))
    return report


# ---------------------------------------------------------------------------
# fill_template：{{占位符}} 填充
# ---------------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.\-\u4e00-\u9fff]+)\s*\}\}")


def _iter_fill_paragraphs(document):
    """正文 + 表格 + 页眉页脚的全部段落。"""
    for paragraph in document.paragraphs:
        yield paragraph
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    yield paragraph
    for section in document.sections:
        for container in (section.header, section.footer):
            for paragraph in container.paragraphs:
                yield paragraph
            for table in container.tables:
                for row in table.rows:
                    for cell in row.cells:
                        for paragraph in cell.paragraphs:
                            yield paragraph


def _fill_paragraph(paragraph: Paragraph, values: dict[str, str]) -> dict[str, int]:
    """填充段落内所有可填充占位符，返回 {key: 命中次数}。"""
    counts: dict[str, int] = {}
    for _ in range(20):  # 防御极端嵌套
        text = paragraph.text
        match = _PLACEHOLDER_RE.search(text)
        if not match:
            break
        key = match.group(1)
        value = values.get(key)
        if value is None:
            break  # 未命中（可能属于 list_values），留在原文由上层报告
        hit, _cross = replace_in_paragraph(
            paragraph, match.group(0), str(value), all_matches=True
        )
        if hit == 0:  # 占位符跨 run 且替换失败，兜底整段替换（保段首格式）
            set_paragraph_text(
                paragraph, text[: match.start()] + str(value) + text[match.end() :]
            )
            hit = 1
        counts[key] = counts.get(key, 0) + hit
    return counts


def fill_template(
    document,
    values: dict[str, str],
    list_values: dict[str, list[dict]] | None = None,
) -> dict:
    """填充 {{key}} 占位符；list_values 命中表格时按模板行展开。"""
    values = {k: str(v) for k, v in (values or {}).items()}
    report: dict[str, Any] = {"filled": [], "missing_keys": [], "warnings": []}
    hit_counter: dict[str, int] = {}

    for paragraph in _iter_fill_paragraphs(document):
        for key, count in _fill_paragraph(paragraph, values).items():
            hit_counter[key] = hit_counter.get(key, 0) + count

    filled_keys = set(hit_counter)
    missing = [k for k in values if k not in filled_keys]

    for key, records in (list_values or {}).items():
        if not _expand_table_rows(document, key, records, report):
            missing.append(key)

    # 残留占位符（文档里存在但 values 未提供值）——提示模型向用户澄清
    residual = sorted(
        {
            match.group(1)
            for paragraph in _iter_fill_paragraphs(document)
            for match in _PLACEHOLDER_RE.finditer(paragraph.text)
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


def _expand_table_rows(
    document, key: str, records: list[dict], report: dict
) -> bool:
    """在表格中找到含 {{key.field}} 的模板行，向下复制展开 records。"""
    if not isinstance(records, list) or not records:
        return False
    prefix = key + "."
    for table in document.tables:
        for r_index, row in enumerate(table.rows):
            row_text = " ".join(cell.text for cell in row.cells)
            if "{{" + prefix not in row_text and "{{" + key + "}}" not in row_text:
                continue
            template_tr = row._tr
            # 为 records[1:] 复制模板行（第一条直接填入模板行）
            for offset in range(len(records) - 1):
                new_tr = copy.deepcopy(template_tr)
                template_tr.addnext(new_tr)
                template_tr = new_tr
            # 重新抓取行（deepcopy 后 python-docx 对象需重建）
            for rec_offset, record in enumerate(records):
                table_row = table.rows[r_index + rec_offset]
                for cell in table_row.cells:
                    for paragraph in cell.paragraphs:
                        while True:
                            text = paragraph.text
                            match = _PLACEHOLDER_RE.search(text)
                            if not match:
                                break
                            token = match.group(1)
                            if token.startswith(prefix):
                                field = token[len(prefix) :]
                                value = str(record.get(field, ""))
                            elif token == key:
                                value = str(rec_offset + 1)
                            else:
                                break  # 其他占位符不在此处理
                            hit, _ = replace_in_paragraph(
                                paragraph, match.group(0), value, all_matches=False
                            )
                            if hit == 0:
                                set_paragraph_text(
                                    paragraph,
                                    text[: match.start()] + value + text[match.end() :],
                                )
            report["warnings"].append(
                f"表格行展开：{key} × {len(records)} 行"
            )
            return True
    return False
