"""Tests for command-style tools (lint_check / run_tests).

Covers output parsers, runner/linter detection + command building, and
end-to-end delegation through the terminal tool with the same policy.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

from app.tools.adapters.lint_check import LintCheckAdapter
from app.tools.adapters.run_tests import RunTestsAdapter
from app.tools.command_output import (
    parse_jest_output,
    parse_lint_output,
    parse_pytest_output,
    parse_ruff_output,
    parse_tsc_output,
)
from app.tools.registry import get_tool
from app.tools.terminal_policy import terminal_command_policy


def _run(adapter_name: str, workspace: Path, arguments: dict):
    adapter = get_tool(adapter_name)
    assert adapter is not None
    return asyncio.run(adapter.run(workspace, arguments))


# --- parsers ---------------------------------------------------------------


def test_parse_pytest_output():
    text = (
        "============================= test session starts "
        "=============================\n"
        "collected 3 items\n\n"
        "tests/test_a.py ..F.\n"
        "FAILED tests/test_a.py::test_broken - AssertionError: nope\n"
        "ERROR tests/test_a.py::test_boom - ValueError: bad\n"
        "========== 1 failed, 1 error, 1 passed in 0.05s ==========\n"
    )
    parsed = parse_pytest_output(text)
    assert parsed["parsed"] is True
    kinds = {item["kind"] for item in parsed["items"]}
    assert kinds == {"failed", "error"}
    assert parsed["items"][0]["test"] == "tests/test_a.py::test_broken"
    assert parsed["counts"] == {"failed": 1, "errors": 1, "passed": 1}


def test_parse_jest_output():
    text = (
        "FAIL src/app.test.js\n"
        "  ✕ adds numbers (5 ms)\n"
        "  ✓ skips\n"
        "\n"
        "Tests: 1 failed, 1 passed, 2 total\n"
    )
    parsed = parse_jest_output(text)
    assert parsed["parsed"] is True
    assert parsed["items"][0]["file"] == "src/app.test.js"
    assert any(item["kind"] == "failed" for item in parsed["items"])
    assert parsed["counts"]["failed"] == 1


def test_parse_ruff_output():
    text = (
        "app.py:10:5: E501 line too long (120 > 88)\n"
        "src/x.py:3:1: F401 `os` imported but unused\n"
        "Found 2 errors.\n"
    )
    parsed = parse_ruff_output(text)
    assert parsed["parsed"] is True
    assert parsed["items"][0]["code"] == "E501"
    assert parsed["items"][0]["line"] == 10
    assert parsed["counts"]["errors"] == 2


def test_parse_tsc_output_both_formats():
    classic = "src/a.ts(12,5): error TS2345: Argument mismatch\n"
    alt = "src/b.ts:3:1 - error TS2304: Cannot find name 'x'\n"
    for text in (classic, alt):
        parsed = parse_tsc_output(text)
        assert parsed["parsed"] is True
        assert parsed["counts"]["errors"] == 1


def test_parse_lint_mypy():
    text = "app.py:4: error: Function is missing a return type [no-untyped-def]\n"
    parsed = parse_lint_output(text, "mypy")
    assert parsed["parsed"] is True
    assert parsed["items"][0]["severity"] == "error"


def test_parse_garbage_returns_unparsed():
    for parser, arg in ((parse_pytest_output, "pytest"), (parse_ruff_output, "ruff")):
        parsed = parser("total garbage output")
        assert parsed["parsed"] is False
    del parser, arg


# --- detection / command building ------------------------------------------


def test_detect_python_project(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    adapter = get_tool("run_tests")
    assert isinstance(adapter, RunTestsAdapter)
    command = adapter.build_command({"runner": "auto"})
    assert command.startswith("(") or "pytest" in command


def test_build_commands_explicit_runner(tmp_path: Path):
    adapter = get_tool("run_tests")
    assert isinstance(adapter, RunTestsAdapter)
    assert (
        adapter.build_command({"runner": "pytest", "paths": ["tests/"], "cwd": "."})
        == "python3 -m pytest tests/ --tb=short -q"
    )
    assert (
        adapter.build_command({"runner": "vitest"})
        == "npx vitest run"
    )


def test_build_lint_commands(tmp_path: Path):
    adapter = LintCheckAdapter("lint_check", "", {})
    assert adapter.build_command({"linter": "tsc"}) == "npx tsc --noEmit"
    assert (
        adapter.build_command({"linter": "eslint", "paths": ["src/"]})
        == "npx eslint src/"
    )


def test_policy_classifies_built_commands_safe():
    # 与 terminal 相同策略：这些构建命令属于 safe 级，无需用户确认。
    for command in (
        "python3 -m pytest --tb=short -q",
        "python3 -m ruff check src/",
        "npx tsc --noEmit",
        "npm test",
    ):
        assert terminal_command_policy(command) == "safe", command


# --- end-to-end delegation through terminal --------------------------------


def test_run_tests_end_to_end(tmp_path: Path):
    """真实执行：通过 terminal 管线跑一个临时 pytest 项目。"""
    if not shutil.which("git"):  # pragma: no cover - environment guard
        return
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_ok.py").write_text(
        "def test_ok():\n    assert 1 + 1 == 2\n"
        "def test_bad():\n    assert 1 + 1 == 3\n",
        encoding="utf-8",
    )
    python = Path(sys.executable).as_posix()
    out = _run(
        "run_tests",
        tmp_path,
        {"command": f"{python} -m pytest tests/ --tb=short -q"},
    )
    assert out.data["parsed"] is True
    assert out.data["exit_code"] != 0
    failures = out.data["failures"]
    assert len(failures) == 1
    assert "test_bad" in failures[0]["test"]
    assert out.success is False
    assert "失败" in out.message or "未通过" in out.message
    # 诊断双通道之一：data.failures[] 带 trace（frames + fingerprint），
    # 供前端渲染与程序化消费；模型看的是 execution.py 的 [诊断] 段。
    trace = failures[0]["trace"]
    assert trace["exception"] == "AssertionError"
    assert len(trace["fingerprint"]) == 12
    assert trace["frames"][0]["file"] == "tests/test_ok.py"
    assert trace["frames"][0]["code"] == "assert 1 + 1 == 3"


def test_run_tests_all_pass(tmp_path: Path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_ok.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    python = Path(sys.executable).as_posix()
    out = _run(
        "run_tests",
        tmp_path,
        {"command": f"{python} -m pytest tests/ -q"},
    )
    assert out.success is True
    assert out.data["counts"].get("passed") == 1


def test_lint_check_cwd_outside_rejected(tmp_path: Path):
    result_or_error = None
    try:
        _run(
            "lint_check",
            tmp_path,
            {"cwd": "../outside", "linter": "ruff"},
        )
    except Exception as exc:  # noqa: BLE001
        result_or_error = exc
    assert result_or_error is not None
