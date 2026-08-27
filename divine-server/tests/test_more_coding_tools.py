"""Tests for list_definitions, apply_patch, move_file."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.tools.adapters.apply_patch import (
    ApplyPatchAdapter,
    parse_patch,
)
from app.tools.base import ToolExecutionError
from app.tools.registry import get_tool


def _run(adapter_name: str, workspace: Path, arguments: dict):
    adapter = get_tool(adapter_name)
    assert adapter is not None
    return asyncio.run(adapter.run(workspace, arguments))


# --- list_definitions --------------------------------------------------------


def test_list_definitions_python(tmp_path: Path):
    (tmp_path / "m.py").write_text(
        "class Foo(Base):\n"
        "    def __init__(self):\n"
        "        pass\n\n"
        "async def run(x: int) -> str:\n"
        "    return ''\n",
        encoding="utf-8",
    )
    out = _run("list_definitions", tmp_path, {"path": "m.py"})
    assert out.success is True
    assert out.data["count"] == 3
    kinds = {item["kind"] for item in out.data["items"]}
    assert kinds == {"class", "method", "function"}
    assert any("async def run" in item["name"] for item in out.data["items"])
    # 大纲行号与 read_file 一致（1-based）
    lines = [item["line"] for item in out.data["items"]]
    assert lines == [1, 2, 5]


def test_list_definitions_typescript(tmp_path: Path):
    (tmp_path / "a.ts").write_text(
        "export class App {}\n"
        "const handler = async (e) => {}\n"
        "export interface Props { x: number }\n",
        encoding="utf-8",
    )
    out = _run("list_definitions", tmp_path, {"path": "a.ts"})
    names = [item["name"] for item in out.data["items"]]
    assert names == ["App", "handler", "Props"]


def test_list_definitions_unsupported_ext(tmp_path: Path):
    (tmp_path / "x.txt").write_text("hello\n")
    with pytest.raises(ToolExecutionError) as exc:
        _run("list_definitions", tmp_path, {"path": "x.txt"})
    assert "不支持" in str(exc.value)


# --- apply_patch -------------------------------------------------------------


def test_parse_and_apply_simple_patch(tmp_path: Path):
    path = tmp_path / "code.py"
    path.write_text("line1\nline2\nline3\n", encoding="utf-8")
    patch = """--- a/code.py
+++ b/code.py
@@ -1,3 +1,3 @@
 line1
-line2
+LINE2
 line3
"""
    out = _run("apply_patch", tmp_path, {"patch": patch})
    assert out.success is True
    assert path.read_text(encoding="utf-8") == "line1\nLINE2\nline3\n"


def test_apply_patch_offset_drift(tmp_path: Path):
    """hunk 声明行号不准时靠上下文搜索定位。"""
    path = tmp_path / "drift.py"
    path.write_text("".join(f"filler{i}\n" for i in range(50)) + "target\ntail\n")
    patch = """--- a/drift.py
+++ b/drift.py
@@ -5,2 +5,2 @@
-target
-tail
+TARGET
+tail
"""
    out = _run("apply_patch", tmp_path, {"patch": patch})
    assert out.success is True
    text = path.read_text(encoding="utf-8")
    assert "TARGET\ntail\n" in text
    assert "-target" not in text


def test_apply_patch_multi_file_and_creation(tmp_path: Path):
    (tmp_path / "a.txt").write_text("hello\n", encoding="utf-8")
    patch = """--- a/a.txt
+++ b/a.txt
@@ -1 +1 @@
-hello
+world
--- /dev/null
+++ b/new.txt
@@ -0,0 +1 @@
+created content
"""
    out = _run("apply_patch", tmp_path, {"patch": patch})
    assert out.success is True
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "world\n"
    assert (tmp_path / "new.txt").read_text(encoding="utf-8") == "created content\n"


def test_apply_patch_bad_context_fails_atomically(tmp_path: Path):
    path = tmp_path / "b.py"
    original = "keep me\nand me\n"
    path.write_text(original)
    patch = """--- a/b.py
+++ b/b.py
@@ -1,2 +1,2 @@
-nonexistent context
-and me
+changed
+and me
"""
    out = _run("apply_patch", tmp_path, {"patch": patch})
    assert out.success is False
    assert path.read_text(encoding="utf-8") == original  # 原子性：未写入
    assert out.data["errors"]


def test_apply_patch_whitespace_fallback(tmp_path: Path):
    """缩进用 tab、补丁用 4 空格：空白折叠后应命中（与 git apply 同语义）。"""
    path = tmp_path / "w.py"
    path.write_text("def f(x):\n\treturn 1\n")
    patch = """--- a/w.py
+++ b/w.py
@@ -1,2 +1,2 @@
-def f(x):
-    return 1
+def f(x):
+    return 2
"""
    out = _run("apply_patch", tmp_path, {"patch": patch})
    assert out.success is True
    assert out.data["files"][0]["fuzzy"] is True
    assert "return 2" in path.read_text(encoding="utf-8")


def test_apply_patch_rejects_outside_workspace(tmp_path: Path):
    patch = "--- /etc/hosts\n+++ /etc/hosts\n@@ -1 +1 @@\n-x\n+y\n"
    with pytest.raises(ToolExecutionError) as exc:
        _run("apply_patch", tmp_path, {"patch": patch})
    assert "越界" in str(exc.value)


def test_parse_patch_ignores_garbage():
    assert parse_patch("not a diff at all") == []


# --- move_file ---------------------------------------------------------------


def test_move_file_rename(tmp_path: Path):
    src = tmp_path / "old.txt"
    src.write_text("data\n")
    out = _run(
        "move_file",
        tmp_path,
        {"path": "old.txt", "new_path": "renamed.txt"},
    )
    assert out.success is True
    assert not src.exists()
    assert (tmp_path / "renamed.txt").read_text(encoding="utf-8") == "data\n"


def test_move_file_into_new_subdir(tmp_path: Path):
    (tmp_path / "f.js").write_text("x\n")
    _run("move_file", tmp_path, {"path": "f.js", "new_path": "src/lib/f.js"})
    assert (tmp_path / "src/lib/f.js").exists()


def test_move_file_overwrite_guard(tmp_path: Path):
    (tmp_path / "a.txt").write_text("A\n")
    (tmp_path / "b.txt").write_text("B\n")
    with pytest.raises(ToolExecutionError) as exc:
        _run("move_file", tmp_path, {"path": "a.txt", "new_path": "b.txt"})
    assert "已存在" in str(exc.value)
    out = _run(
        "move_file",
        tmp_path,
        {"path": "a.txt", "new_path": "b.txt", "overwrite": True},
    )
    assert out.success is True
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "A\n"


def test_move_file_outside_rejected(tmp_path: Path):
    (tmp_path / "x").write_text("x")
    with pytest.raises(ToolExecutionError) as exc:
        _run("move_file", tmp_path, {"path": "x", "new_path": "../escape"})
    assert "工作区内" in str(exc.value)


def test_move_dir_into_itself_rejected(tmp_path: Path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "inner.txt").write_text("i")
    with pytest.raises(ToolExecutionError) as exc:
        _run("move_file", tmp_path, {"path": "pkg", "new_path": "pkg/pkg"})
    assert "子目录" in str(exc.value)
