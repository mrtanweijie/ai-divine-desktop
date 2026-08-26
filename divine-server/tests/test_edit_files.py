"""Tests for edit_files: exact replace, fuzzy whitespace fallback, diffs."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.tools.adapters.edit_files import EditFilesAdapter
from app.tools.base import ToolExecutionError
from app.tools.registry import get_tool


def _adapter() -> EditFilesAdapter:
    adapter = get_tool("edit_files")
    assert adapter is not None
    return adapter


def _run(workspace: Path, arguments: dict):
    return asyncio.run(_adapter().run(workspace, arguments))


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture()
def ws(tmp_path: Path) -> Path:
    _write(
        tmp_path,
        "app.py",
        "def greet(name):\n    return f'hello {name}'\n\n\ndef main():\n    print(greet('world'))\n",
    )
    return tmp_path


def test_exact_replace(ws: Path):
    out = _run(
        ws,
        {
            "files": [
                {
                    "path": "app.py",
                    "search": "    return f'hello {name}'",
                    "replace": "    return f'hi {name}'",
                }
            ]
        },
    )
    assert out.success is True
    assert "hi" in (ws / "app.py").read_text(encoding="utf-8")
    files = out.data["files"]
    assert files[0]["action"] == "modified"
    assert files[0]["fuzzy"] is False


def test_fuzzy_replace_unique(ws: Path):
    """Whitespace mismatch (blank lines collapsed) but unique match → apply."""
    out = _run(
        ws,
        {
            "files": [
                {
                    "path": "app.py",
                    # search has an extra blank line vs actual file
                    "search": "def greet(name):\n\n\n    return f'hello {name}'",
                    "replace": "def greet(name: str):\n    return f'hello {name}'",
                }
            ]
        },
    )
    assert out.success is True
    assert out.data["fuzzy_used"] is True
    files = out.data["files"]
    assert files[0]["fuzzy"] is True
    text = (ws / "app.py").read_text(encoding="utf-8")
    assert "def greet(name: str):" in text


def test_fuzzy_ambiguous_rejected(ws: Path):
    text = "\n\n".join(
        ["def a():\n    return 1", "def b():\n    return 2"]
    )
    _write(ws, "dup.py", text)
    out = _run(
        ws,
        {
            "files": [
                {
                    "path": "dup.py",
                    "search": "def x():\n    return N",
                    "replace": "def y():\n    return 0",
                }
            ]
        },
    )
    # whitespace-collapsed search "def x(): return N" matches neither function
    assert out.success is False
    assert "未在" in out.data["failed"][0]["error"]
    assert (ws / "dup.py").read_text(encoding="utf-8") == text


def test_fuzzy_multiple_candidates_rejected(ws: Path):
    text = "def dup():\n    return 1\n\ndef dup():\n    return 1\n"
    _write(ws, "multi.py", text)
    out = _run(
        ws,
        {
            "files": [
                {
                    "path": "multi.py",
                    # exact search fails (missing indentation), but the
                    # whitespace-collapsed form matches BOTH blocks
                    "search": "def dup():\nreturn 1",
                    "replace": "def dup():\n    return 2",
                }
            ]
        },
    )
    assert out.success is False
    message = out.data["failed"][0]["error"]
    assert "模糊匹配" in message
    assert (ws / "multi.py").read_text(encoding="utf-8") == text


def test_no_match_clear_error(ws: Path):
    original = (ws / "app.py").read_text(encoding="utf-8")
    out = _run(
        ws,
        {
            "files": [
                {
                    # 与真实内容高度相似（greet 拼错），应触发片段提示
                    "path": "app.py",
                    "search": "def greet(nme):\n    return f'hello {name}'",
                    "replace": "pass",
                }
            ]
        },
    )
    assert out.success is False
    error = out.data["failed"][0]["error"]
    assert "未在" in error
    # 失败信息附带最接近的现有内容片段，帮助模型一次修正
    assert "最接近的现有内容" in error
    assert (ws / "app.py").read_text(encoding="utf-8") == original


def test_diff_output(ws: Path):
    out = _run(
        ws,
        {
            "files": [
                {
                    "path": "app.py",
                    "search": "def greet(name):",
                    "replace": "def greet(name: str):",
                }
            ]
        },
    )
    diff = out.data["diff"]
    assert diff is not None
    assert "--- app.py" in diff
    assert "+++ app.py" in diff
    assert "-def greet(name):" in diff
    assert "+def greet(name: str):" in diff
    # per-file diff also present
    assert out.data["files"][0]["diff"]


def test_created_file_diff(ws: Path):
    out = _run(
        ws,
        {
            "files": [
                {"path": "new.py", "search": "", "replace": "x = 1\n"}
            ]
        },
    )
    assert out.success is True
    assert out.data["files"][0]["action"] == "created"
    diff = out.data["diff"]
    assert "+x = 1" in diff


def test_batch_multiple_files(ws: Path):
    _write(ws, "b.py", "y = 1\n")
    out = _run(
        ws,
        {
            "files": [
                {
                    "path": "app.py",
                    "search": "print(greet('world'))",
                    "replace": "print(greet('world'))\n    print('done')",
                },
                {"path": "b.py", "search": "y = 1", "replace": "y = 2"},
            ]
        },
    )
    assert out.success is True
    assert len(out.data["files"]) == 2
    assert "y = 2" in (ws / "b.py").read_text(encoding="utf-8")


def test_replace_all_count(ws: Path):
    _write(ws, "c.py", "a = 1\na = 2\na = 3\n")
    out = _run(
        ws,
        {"files": [{"path": "c.py", "search": "a = ", "replace": "b = ", "count": -1}]},
    )
    assert out.success is True
    assert out.data["files"][0]["replacements"] == 3
    text = (ws / "c.py").read_text(encoding="utf-8")
    assert text.count("b = ") == 3


def test_create_existing_rejected(ws: Path):
    original = (ws / "app.py").read_text(encoding="utf-8")
    out = _run(
        ws,
        {"files": [{"path": "app.py", "search": "", "replace": "x"}]},
    )
    assert out.success is False
    assert "已存在" in out.data["failed"][0]["error"]
    assert (ws / "app.py").read_text(encoding="utf-8") == original


def test_partial_success_continues(ws: Path):
    """一个编辑项失败不再回滚整批：成功的照常落盘，失败项进 failed 列表。"""
    _write(ws, "b.py", "y = 1\n")
    out = _run(
        ws,
        {
            "files": [
                {"path": "b.py", "search": "y = 1", "replace": "y = 2"},
                {
                    "path": "app.py",
                    "search": "def nonexistent():",
                    "replace": "pass",
                },
            ]
        },
    )
    assert out.success is True
    assert len(out.data["files"]) == 1
    assert len(out.data["failed"]) == 1
    assert out.data["failed"][0]["index"] == 2
    assert "y = 2" in (ws / "b.py").read_text(encoding="utf-8")


def test_line_number_prefix_stripped(ws: Path):
    """SEARCH 复制了 read_file 的行号前缀时自动剥离重试。"""
    numbered_search = "     3\t    return f'hello {name}'"
    out = _run(
        ws,
        {
            "files": [
                {
                    "path": "app.py",
                    "search": numbered_search,
                    "replace": "     3\t    return f'hi {name}'".split("\t", 1)[1],
                }
            ]
        },
    )
    assert out.success is True
    assert "hi" in (ws / "app.py").read_text(encoding="utf-8")


def test_crlf_line_endings_preserved(ws: Path):
    """CRLF 文件：LF 形式的 SEARCH 能匹配，写回保持 CRLF 且不产生混合换行。"""
    _write(ws, "crlf.py", "x = 1\r\ny = 2\r\n")
    out = _run(
        ws,
        {
            "files": [
                {"path": "crlf.py", "search": "y = 2", "replace": "y = 3"}
            ]
        },
    )
    assert out.success is True
    raw = (ws / "crlf.py").read_bytes()
    assert b"y = 3" in raw
    assert raw.count(b"\r\n") == 2
    assert b"\r\r\n" not in raw


def test_bom_preserved(ws: Path):
    """带 BOM 的文件编辑后 BOM 保留。"""
    path = ws / "bom.py"
    path.write_bytes("\ufeffz = 1\n".encode("utf-8"))
    out = _run(
        ws,
        {"files": [{"path": "bom.py", "search": "z = 1", "replace": "z = 2"}]},
    )
    assert out.success is True
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert "z = 2" in path.read_text(encoding="utf-8")
