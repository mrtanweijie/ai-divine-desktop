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
    with pytest.raises(ToolExecutionError) as exc:
        _run(
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
    assert "未在" in str(exc.value)


def test_fuzzy_multiple_candidates_rejected(ws: Path):
    text = "def dup():\n    return 1\n\ndef dup():\n    return 1\n"
    _write(ws, "multi.py", text)
    with pytest.raises(ToolExecutionError) as exc:
        _run(
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
    message = str(exc.value)
    assert "模糊匹配" in message


def test_no_match_clear_error(ws: Path):
    with pytest.raises(ToolExecutionError) as exc:
        _run(
            ws,
            {
                "files": [
                    {
                        "path": "app.py",
                        "search": "def nonexistent():",
                        "replace": "pass",
                    }
                ]
            },
        )
    assert "未在" in str(exc.value)


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
    with pytest.raises(ToolExecutionError) as exc:
        _run(
            ws,
            {"files": [{"path": "app.py", "search": "", "replace": "x"}]},
        )
    assert "已存在" in str(exc.value)
