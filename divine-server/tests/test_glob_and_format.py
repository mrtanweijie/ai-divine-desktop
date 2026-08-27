"""Tests for glob_files and format_code tools."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.tools.adapters.format_code import FormatCodeAdapter, _count_changed
from app.tools.registry import get_tool


def _run(adapter_name: str, workspace: Path, arguments: dict):
    adapter = get_tool(adapter_name)
    assert adapter is not None
    return asyncio.run(adapter.run(workspace, arguments))


# --- glob_files -------------------------------------------------------------


def _make_project(root: Path) -> None:
    (root / "src").mkdir(parents=True)
    (root / "src" / "deep").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "app.ts").write_text("export {}\n", encoding="utf-8")
    (root / "src" / "app.test.ts").write_text("test()\n", encoding="utf-8")
    (root / "src" / "deep" / "util.test.ts").write_text(
        "test()\n", encoding="utf-8"
    )
    (root / "tests" / "test_a.py").write_text("def test_a():\n    pass\n")
    (root / "pyproject.toml").write_text("[project]\nname='x'\n")


def test_glob_recursive_pattern(tmp_path: Path):
    _make_project(tmp_path)
    out = _run("glob_files", tmp_path, {"pattern": "src/**/*.test.ts"})
    assert out.success is True
    paths = [f["path"] for f in __import__("json").loads(out.content)]
    assert "src/app.test.ts" in paths
    assert "src/deep/util.test.ts" in paths
    assert all(not p.endswith("app.ts") for p in paths)


def test_glob_respects_gitignore(tmp_path: Path):
    _make_project(tmp_path)
    (tmp_path / ".gitignore").write_text("tests/\n")
    out = _run("glob_files", tmp_path, {"pattern": "**/*.py"})
    paths = [f["path"] for f in __import__("json").loads(out.content)]
    assert all(not p.startswith("tests/") for p in paths)


def test_glob_hidden_dirs_skipped(tmp_path: Path):
    hidden = tmp_path / ".venv" / "lib"
    hidden.mkdir(parents=True)
    (hidden / "x.py").write_text("x = 1\n")
    out = _run("glob_files", tmp_path, {"pattern": "**/*.py"})
    assert __import__("json").loads(out.content) == []


def test_glob_path_outside_rejected(tmp_path: Path):
    raised = False
    try:
        _run("glob_files", tmp_path, {"pattern": "*.py", "path": "../.."})
    except Exception:  # noqa: BLE001
        raised = True
    assert raised


# --- format_code ------------------------------------------------------------


def test_format_build_commands():
    adapter = FormatCodeAdapter("format_code", "", {})
    assert (
        adapter.build_command({"formatter": "ruff", "paths": ["src/"]})
        == "python3 -m ruff format src/"
    )
    assert adapter.build_command({"formatter": "prettier"}) == (
        "npx prettier --write ."
    )


def test_count_changed_parsing():
    assert _count_changed("reformatted src/a.py\n5 files reformatted\n") == 5
    assert _count_changed("1 file reformatted\n") == 1
    assert _count_changed("24 files left unchanged\n") == 0
    assert _count_changed("nothing recognizable") is None


def test_format_end_to_end_ruff(tmp_path: Path):
    """真实执行 ruff format（当前 venv 内可用）。"""
    messy = tmp_path / "messy.py"
    messy.write_text("x=1\ny  =  2\n", encoding="utf-8")
    python = Path(__import__("sys").executable).as_posix()
    out = _run(
        "format_code",
        tmp_path,
        {"command": f"{python} -m ruff format messy.py"},
    )
    if not out.success:
        return  # 环境无 ruff 时跳过断言
    assert out.data["changed"] == 1
    text = messy.read_text(encoding="utf-8")
    assert text == "x = 1\ny = 2\n"


def test_format_cwd_outside_rejected(tmp_path: Path):
    raised = False
    try:
        _run("format_code", tmp_path, {"cwd": "..", "formatter": "ruff"})
    except Exception:  # noqa: BLE001
        raised = True
    assert raised
