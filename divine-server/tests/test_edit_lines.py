"""Tests for edit_lines: line-range editing with original numbering."""

from __future__ import annotations

import pytest

from app.tools.adapters.edit_lines import (
    EditLinesAdapter,
    _conflicts,
    apply_line_edits,
)
from app.tools.base import ToolExecutionError
from app.tools.registry import get_tool


def _adapter() -> EditLinesAdapter:
    adapter = get_tool("edit_lines")
    assert isinstance(adapter, EditLinesAdapter)
    return adapter


def _run(tmp_path: Path, arguments: dict):
    import asyncio

    return asyncio.run(_adapter().run(tmp_path, arguments))


def _make_file(root: Path, text: str, name: str = "f.py") -> Path:
    path = root / name
    path.write_text(text, encoding="utf-8")
    return path


FIVE = "a\nb\nc\nd\ne\n"


# --- pure algorithm ----------------------------------------------------------


def test_apply_replace_range():
    new, applied = apply_line_edits(
        ["a", "b", "c", "d", "e"], [(2, 3, "B1\nB2")]
    )
    assert new == ["a", "B1", "B2", "d", "e"]
    assert applied[0][0] == (2, 3)
    assert applied[0][1] == (2, 3)


def test_apply_delete_and_insert_mixed():
    new, applied = apply_line_edits(
        ["a", "b", "c", "d", "e"],
        [(2, 3, "B1\nB2"), (5, 4, "inserted"), (1, 1, "")],
    )
    assert new == ["B1", "B2", "d", "inserted", "e"]


def test_conflict_detection():
    assert _conflicts((2, 4), (3, 5)) is True
    assert _conflicts((2, 3), (4, 6)) is False
    # 插入点在替换范围内部 → 冲突
    assert _conflicts((3, 2), (2, 5)) is True
    # 两个同位置插入 → 冲突
    assert _conflicts((3, 2), (3, 2)) is True
    # 插入在替换范围边界外 → 允许
    assert _conflicts((1, 0), (2, 5)) is False
    with pytest.raises(ToolExecutionError):
        apply_line_edits(["a"], [(1, 1, "x"), (1, 1, "y")])


# --- end-to-end --------------------------------------------------------------


def test_replace_lines_end_to_end(tmp_path):
    _make_file(tmp_path, FIVE)
    out = _run(tmp_path, {"path": "f.py", "edits": [{"start_line": 2, "end_line": 3, "content": "B"}]})
    assert out.success is True
    text = (tmp_path / "f.py").read_text(encoding="utf-8")
    assert text == "a\nB\nd\ne\n"
    assert "+B" in out.content and "-b" in out.content
    assert out.data["total_lines_after"] == 4


def test_delete_via_empty_content(tmp_path):
    _make_file(tmp_path, FIVE)
    _run(tmp_path, {"path": "f.py", "edits": [{"start_line": 2, "end_line": 4, "content": ""}]})
    assert (tmp_path / "f.py").read_text(encoding="utf-8") == "a\ne\n"


def test_insert_before_line(tmp_path):
    _make_file(tmp_path, FIVE)
    _run(tmp_path, {"path": "f.py", "edits": [{"start_line": 1, "end_line": 0, "content": "# header"}]})
    assert (tmp_path / "f.py").read_text(encoding="utf-8") == "# header\na\nb\nc\nd\ne\n"


def test_multi_edit_uses_original_numbering(tmp_path):
    """多个区间同时提交，行号全部按原始文件计算。"""
    _make_file(tmp_path, FIVE)
    out = _run(
        tmp_path,
        {
            "path": "f.py",
            "edits": [
                {"start_line": 5, "end_line": 5, "content": "E2"},
                {"start_line": 1, "end_line": 1, "content": "A2"},
            ],
        },
    )
    assert out.success is True
    assert (tmp_path / "f.py").read_text(encoding="utf-8") == "A2\nb\nc\nd\nE2\n"
    originals = {item["original"] for item in out.data["applied"]}
    assert originals == {"1-1", "5-5"}


def test_edge_newlines_stripped(tmp_path):
    _make_file(tmp_path, FIVE)
    _run(
        tmp_path,
        {"path": "f.py", "edits": [{"start_line": 2, "content": "\nB\n"}]},
    )
    assert (tmp_path / "f.py").read_text(encoding="utf-8") == "a\nB\nc\nd\ne\n"


def test_out_of_range_rejected(tmp_path):
    _make_file(tmp_path, FIVE)
    with pytest.raises(ToolExecutionError) as exc:
        _run(tmp_path, {"path": "f.py", "edits": [{"start_line": 9, "content": "x"}]})
    assert "超出文件范围" in str(exc.value)


def test_overlap_rejected(tmp_path):
    _make_file(tmp_path, FIVE)
    with pytest.raises(ToolExecutionError) as exc:
        _run(
            tmp_path,
            {
                "path": "f.py",
                "edits": [
                    {"start_line": 1, "end_line": 3, "content": "x"},
                    {"start_line": 2, "end_line": 4, "content": "y"},
                ],
            },
        )
    assert "冲突" in str(exc.value)


def test_crlf_preserved(tmp_path):
    path = tmp_path / "crlf.py"
    path.write_bytes(b"a\r\nb\r\nc\r\n")
    _run(tmp_path, {"path": "crlf.py", "edits": [{"start_line": 2, "content": "B2"}]})
    raw = path.read_bytes()
    assert raw.count(b"\r\n") == 3
    assert b"B2" in raw


def test_missing_file_rejected(tmp_path):
    with pytest.raises(ToolExecutionError) as exc:
        _run(tmp_path, {"path": "nope.py", "edits": [{"start_line": 1, "content": "x"}]})
    assert "不存在" in str(exc.value)
