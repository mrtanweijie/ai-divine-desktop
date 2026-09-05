"""edit_pptx 引擎与脚本回归（docs/design/017-office-edit-closed-loop-20260906.md 期三）：

- 文本替换 run 级保格式（含组合形状、表格内文本、跨 run 合并）；
- 页范围限定（slide 序号）、set_title、未命中给候选；
- 事务失败零修改；外部文件副本；母版/版式不被触碰（页数与形状数不变）。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest  # noqa: E402
from pptx import Presentation  # noqa: E402
from pptx.enum.shapes import MSO_SHAPE_TYPE  # noqa: E402
from pptx.util import Inches, Pt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.docgen.ppt.editor import PptxOpError, apply_ops  # noqa: E402


def _iter_texts(prs):
    """扁平化全部文本（含组合形状与表格），供断言用。"""
    for slide in prs.slides:
        for shape in slide.shapes:
            yield from _shape_texts(shape)


def _shape_texts(shape):
    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
        for inner in shape.shapes:
            yield from _shape_texts(inner)
        return
    if getattr(shape, "has_table", False) and shape.has_table:
        for row in shape.table.rows:
            for cell in row.cells:
                yield cell.text_frame.text
        return
    if shape.has_text_frame:
        yield shape.text_frame.text


def _make_deck(path: Path) -> None:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    # 页 1：标题版式（有标题占位符）+ 内容（跨 run 格式）
    slide1 = prs.slides.add_slide(prs.slide_layouts[5])  # Title Only
    slide1.shapes.title.text_frame.text = "封面标题"
    box = slide1.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(1.5))
    paragraph = box.text_frame.paragraphs[0]
    run1 = paragraph.add_run()
    run1.text = "霸王茶姬"
    run1.font.bold = True
    run1.font.size = Pt(20)
    run1_2 = paragraph.add_run()
    run1_2.text = "商业模式"
    # 页 2：跨 run 段落 + 组合形状
    slide2 = prs.slides.add_slide(prs.slide_layouts[6])
    box2 = slide2.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(1.5))
    paragraph2 = box2.text_frame.paragraphs[0]
    run2 = paragraph2.add_run()
    run2.text = "营业额"
    run2.font.bold = True
    run2.font.size = Pt(20)
    run2_2 = paragraph2.add_run()
    run2_2.text = "增长20%"
    group = slide2.shapes.add_group_shape()
    inner = group.shapes.add_textbox(Inches(2), Inches(3), Inches(4), Inches(1))
    inner.text_frame.text = "组合形状里的目标文本"
    prs.save(str(path))


def test_replace_text_across_slides_and_groups(tmp_path):
    path = tmp_path / "deck.pptx"
    _make_deck(path)
    prs = Presentation(str(path))
    report = apply_ops(
        prs, [{"op": "replace_text", "find": "目标文本", "replace": "已更新"}]
    )
    assert report["hits"] == 1
    assert any("已更新" in text for text in _iter_texts(prs))


def test_replace_cross_run_keeps_first_run_format(tmp_path):
    path = tmp_path / "deck.pptx"
    _make_deck(path)
    prs = Presentation(str(path))
    apply_ops(prs, [{"op": "replace_text", "find": "额增长", "replace": "额暴涨"}])
    texts = list(_iter_texts(prs))
    assert any("营业额暴涨" in t for t in texts)
    # 找到该段落验证首 run 格式延续
    box2 = next(
        s
        for s in prs.slides[1].shapes
        if s.has_text_frame and "暴涨" in s.text_frame.text
    )
    runs = box2.text_frame.paragraphs[0].runs
    assert runs[0].text == "营业额暴涨"
    assert runs[0].font.bold is True
    assert runs[0].font.size == Pt(20)


def test_replace_scope_single_slide(tmp_path):
    path = tmp_path / "deck.pptx"
    _make_deck(path)
    prs = Presentation(str(path))
    apply_ops(
        prs,
        [{"op": "replace_text", "find": "商业模式", "replace": "拆解", "slide": 1}],
    )
    all_texts = list(_iter_texts(prs))
    assert any("拆解" in t for t in all_texts)
    # 页 2 的文本不受影响（仅页 1 一处命中）
    assert sum("拆解" in t for t in all_texts) == 1


def test_replace_miss_gives_candidates(tmp_path):
    path = tmp_path / "deck.pptx"
    _make_deck(path)
    prs = Presentation(str(path))
    with pytest.raises(PptxOpError) as exc_info:
        apply_ops(prs, [{"op": "replace_text", "find": "商业模型", "replace": "x"}])
    assert "商业模式" in str(exc_info.value)  # 相近候选


def test_set_title_and_invalid_slide(tmp_path):
    path = tmp_path / "deck.pptx"
    _make_deck(path)
    prs = Presentation(str(path))
    report = apply_ops(prs, [{"op": "set_title", "slide": 1, "text": "新封面"}])
    assert report["hits"] == 1
    assert prs.slides[0].shapes.title.text_frame.text == "新封面"
    with pytest.raises(PptxOpError):
        apply_ops(prs, [{"op": "replace_text", "find": "x", "replace": "y", "slide": 99}])


def test_master_and_slide_count_untouched(tmp_path):
    path = tmp_path / "deck.pptx"
    _make_deck(path)
    before = Presentation(str(path))
    shape_counts = [len(s.shapes) for s in before.slides]
    prs = Presentation(str(path))
    apply_ops(prs, [{"op": "replace_text", "find": "商业模式", "replace": "拆解"}])
    prs.save(str(path))
    after = Presentation(str(path))
    assert len(after.slides) == len(before.slides)
    assert [len(s.shapes) for s in after.slides] == shape_counts


def _run_script(payload: dict) -> dict:
    script = Path(__file__).resolve().parents[1] / "app" / "tools" / "scripts" / "edit_pptx.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    return json.loads(completed.stdout)


def test_edit_pptx_script_external_file_creates_copy(tmp_path):
    ws = tmp_path / "ws"
    (ws / "documents").mkdir(parents=True)
    external = tmp_path / "Desktop"
    external.mkdir()
    deck = external / "deck.pptx"
    _make_deck(deck)
    original_bytes = deck.read_bytes()

    output = _run_script(
        {
            "workspace": str(ws),
            "output_dir": str(ws),
            "params": {
                "path": str(deck),
                "session_id": "s-ppt",
                "ops": [{"op": "replace_text", "find": "商业模式", "replace": "拆解"}],
            },
        }
    )
    assert output["success"] is True
    assert deck.read_bytes() == original_bytes  # 原文件未动
    copy_path = Path(output["filepath"])
    assert copy_path.parent == ws / "documents" / "edited"
    reopened = Presentation(str(copy_path))
    assert any("拆解" in text for text in _iter_texts(reopened))


def test_edit_pptx_script_failure_untouched(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    deck = ws / "deck.pptx"
    _make_deck(deck)
    before = deck.read_bytes()
    output = _run_script(
        {
            "workspace": str(ws),
            "output_dir": str(ws),
            "params": {
                "path": str(deck),
                "session_id": "s-ppt",
                "ops": [{"op": "replace_text", "find": "不存在的文本", "replace": "x"}],
            },
        }
    )
    assert output["success"] is False
    assert deck.read_bytes() == before
