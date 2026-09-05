"""PPT 文本编辑引擎（edit_pptx，期三）。

边界（docs/design/017-office-edit-closed-loop-20260906.md §2 非目标）：
只做文本替换——不动母版、不动版式、不动图表/图片对象。
替换哲学与 Word 引擎一致：run 级操作保格式，跨 run 合并并如实上报。
"""

from __future__ import annotations

import difflib
from typing import Any

from pptx.enum.shapes import MSO_SHAPE_TYPE


class PptxOpError(ValueError):
    """操作定位失败。candidates 为最相近候选。"""

    def __init__(self, message: str, candidates: list[str] | None = None) -> None:
        super().__init__(message)
        self.candidates = candidates or []


def _iter_text_frames(slide):
    """遍历一页内所有文本框（含组合形状与表格单元格）。"""

    def walk(shapes):
        for shape in shapes:
            if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                yield from walk(shape.shapes)
                continue
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        yield cell.text_frame
                continue
            if shape.has_text_frame:
                yield shape.text_frame

    yield from walk(slide.shapes)


def _replace_in_paragraph(paragraph, find: str, replace: str, all_matches: bool) -> int:
    """run 级查找替换；跨 run 命中时清空 span 内其余 run（保首 run 格式）。"""
    text = "".join(run.text for run in paragraph.runs)
    lowered = text.lower()
    needle = find.lower()
    if not needle:
        return 0
    spans: list[tuple[int, int]] = []
    pos = 0
    limit = len(text) if all_matches else 1
    while len(spans) < limit:
        idx = lowered.find(needle, pos)
        if idx < 0:
            break
        spans.append((idx, idx + len(needle)))
        pos = idx + len(needle)
    if not spans:
        return 0

    hits = 0
    for start, end in reversed(spans):
        runs = paragraph.runs
        offsets: list[tuple[Any, int, int]] = []
        cursor = 0
        for run in runs:
            offsets.append((run, cursor, cursor + len(run.text)))
            cursor += len(run.text)
        overlapping = [(r, s, e) for r, s, e in offsets if s < end and e > start]
        if not overlapping:
            continue
        hits += 1
        if len(overlapping) == 1:
            run, s, _ = overlapping[0]
            run.text = run.text[: start - s] + replace + run.text[end - s :]
            continue
        first_run, first_start, _ = overlapping[0]
        last_run, last_start, _ = overlapping[-1]
        first_run.text = first_run.text[: start - first_start] + replace
        for run, _, _ in overlapping[1:-1]:
            run.text = ""
        last_run.text = last_run.text[end - last_start :]
    return hits


def _replace_in_text_frame(text_frame, find: str, replace: str, all_matches: bool) -> int:
    return sum(
        _replace_in_paragraph(paragraph, find, replace, all_matches)
        for paragraph in text_frame.paragraphs
    )


def _resolve_slide(prs, slide: int | None):
    count = len(prs.slides)
    if not count:
        raise PptxOpError("演示文稿没有任何页面")
    if slide is None:
        return None  # 全部页面
    if not isinstance(slide, int) or slide < 1 or slide > count:
        raise PptxOpError(f"slide 序号无效: {slide}，有效范围 1-{count}")
    return prs.slides[slide - 1]


def _slide_candidates(prs) -> list[str]:
    return [
        " ".join(tf.text.split())[:40]
        for slide in prs.slides
        for tf in _iter_text_frames(slide)
        if tf.text.strip()
    ]


def apply_ops(prs, ops: list[dict]) -> dict:
    """顺序应用 ops；任一步定位失败抛 PptxOpError（内存态未保存=事务中止）。"""
    report: dict[str, Any] = {
        "ops_applied": [],
        "hits": 0,
        "cross_run": 0,
        "warnings": [],
    }
    for index, raw in enumerate(ops or [], 1):
        if not isinstance(raw, dict):
            raise PptxOpError(f"第 {index} 个操作不是对象: {raw!r}")
        kind = str(raw.get("op") or "").strip()
        try:
            if kind == "replace_text":
                _op_replace_text(prs, raw, report)
            elif kind == "set_title":
                _op_set_title(prs, raw, report)
            else:
                raise PptxOpError(f"未知操作类型: {kind!r}")
        except PptxOpError as exc:
            report["missed"] = [
                {"op_index": index, "op": kind, "reason": str(exc)}
            ]
            exc.op_index = index  # type: ignore[attr-defined]
            raise
        report["ops_applied"].append(kind)
    return report


def _op_replace_text(prs, op: dict, report: dict) -> None:
    find = str(op.get("find") or "")
    if not find:
        raise PptxOpError("replace_text 缺少 find")
    replace = str(op.get("replace") or "")
    all_matches = bool(op.get("all"))
    scope = _resolve_slide(prs, op.get("slide"))
    slides = [scope] if scope is not None else list(prs.slides)
    hits = 0
    for slide in slides:
        for text_frame in _iter_text_frames(slide):
            hits += _replace_in_text_frame(text_frame, find, replace, all_matches)
    if hits == 0:
        close = difflib.get_close_matches(find, _slide_candidates(prs), n=3, cutoff=0.4)
        hint = f"，最相近：{close}" if close else ""
        raise PptxOpError(f"未找到文本 {find!r}{hint}")
    report["hits"] += hits


def _op_set_title(prs, op: dict, report: dict) -> None:
    slide_index = op.get("slide")
    slide = _resolve_slide(prs, slide_index if isinstance(slide_index, int) else None)
    if slide is None:
        raise PptxOpError("set_title 需要用 slide 序号指定页面")
    text = str(op.get("text") or "")
    title = slide.shapes.title
    if title is None:
        raise PptxOpError(f"第 {slide_index} 页没有标题占位符")
    paragraphs = title.text_frame.paragraphs
    if paragraphs and paragraphs[0].runs:
        paragraphs[0].runs[0].text = text
        for run in paragraphs[0].runs[1:]:
            run.text = ""
        for paragraph in paragraphs[1:]:
            for run in paragraph.runs:
                run.text = ""
    else:
        title.text_frame.text = text
    report["hits"] += 1
