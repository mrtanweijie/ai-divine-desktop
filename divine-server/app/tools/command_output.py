"""Parsers turning raw test/lint CLI output into structured summaries.

Each parser returns {"parsed": bool, "items": [...], "summary": str,
"counts": {...}}. `items` entries are small dicts (file/line/test/message)
so they survive context truncation and render compactly in the UI.
"""

from __future__ import annotations

import re
from typing import Any

_MAX_ITEMS = 100

# "5 failed, 12 passed, 1 error in 0.32s" / "12 passed in 0.01s"
# 兼容带 ==== 装饰与 -q 模式下的裸汇总行，捕获组从首个计数开始。
_PYTEST_SUMMARY_RE = re.compile(
    r"^[ \t=]*(\d+ (?:failed|passed)[^\n]*)$", re.M
)
# "FAILED tests/test_x.py::test_y - AssertionError: ..."
_PYTEST_ITEM_RE = re.compile(r"^(FAILED|ERROR)\s+(\S+?)(?:\s+-\s+(.*))?$", re.M)
# "Tests: 1 failed, 5 passed, 6 total" (jest / vitest)
_JEST_SUMMARY_RE = re.compile(r"^\s*Tests:\s*(.+)$", re.M)
_JEST_FAIL_FILE_RE = re.compile(r"^FAIL\s+(\S+)", re.M)
_JEST_FAIL_TEST_RE = re.compile(r"^\s*[✕×]\s+(.+)$", re.M)

# "app.py:10:5: E501 line too long"
_RUFF_LINE_RE = re.compile(
    r"^([^:\n]+):(\d+):(?:\d+)?: ([A-Z]+[0-9]+) (.*)$", re.M
)
# "src/a.ts(10,5): error TS2345: ..." and "src/a.ts:10:5 - error TS2345: ..."
_TSC_LINE_RE = re.compile(
    r"^([^(\n]+?)\((\d+),(\d+)\): (error|warning) (\S+): (.*)$", re.M
)
_TSC_ALT_LINE_RE = re.compile(
    r"^([^:\n]+):(\d+):\d+ - (error|warning) (\S+): (.*)$", re.M
)

# mypy: "file.py:10: error: Message [code]"
_MYPY_LINE_RE = re.compile(
    r"^([^:\n]+):(\d+): (error|warning|note): (.*)$", re.M
)


def _counts_from_summary(summary: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for label, key in (
        ("failed", "failed"),
        ("passed", "passed"),
        ("error", "errors"),
        ("errors", "errors"),
        ("skipped", "skipped"),
        ("warning", "warnings"),
        ("warnings", "warnings"),
    ):
        match = re.search(rf"(\d+)\s+{label}\b", summary)
        if match:
            counts[key] = counts.get(key, 0) + int(match.group(1))
    return counts


def _empty() -> dict[str, Any]:
    return {"parsed": False, "items": [], "summary": "", "counts": {}}


def parse_pytest_output(text: str) -> dict[str, Any]:
    items = [
        {
            "kind": match.group(1).lower(),
            "test": match.group(2),
            "message": (match.group(3) or "")[:300],
        }
        for match in _PYTEST_ITEM_RE.finditer(text)
    ]
    summaries = _PYTEST_SUMMARY_RE.findall(text)
    summary = summaries[-1] if summaries else ""
    if not items and not summary:
        return _empty()
    return {
        "parsed": True,
        "items": items[:_MAX_ITEMS],
        "summary": summary,
        "counts": _counts_from_summary(summary),
    }


def parse_jest_output(text: str) -> dict[str, Any]:
    files = _JEST_FAIL_FILE_RE.findall(text)
    tests = [
        {"kind": "failed", "test": match.group(1).strip()[:300]}
        for match in _JEST_FAIL_TEST_RE.finditer(text)
    ]
    summaries = _JEST_SUMMARY_RE.findall(text)
    summary = summaries[-1].strip() if summaries else ""
    if not files and not tests and not summary:
        return _empty()
    for item in tests:
        if files:
            item["file"] = files[0]
    failed_files = [{"kind": "failed_file", "file": f} for f in files[:20]]
    return {
        "parsed": True,
        "items": (failed_files + tests)[:_MAX_ITEMS],
        "summary": summary,
        "counts": _counts_from_summary(summary),
    }


def parse_ruff_output(text: str) -> dict[str, Any]:
    items = [
        {
            "file": m.group(1),
            "line": int(m.group(2)),
            "code": m.group(3),
            "message": m.group(4)[:300],
        }
        for m in _RUFF_LINE_RE.finditer(text)
    ]
    found = re.search(r"Found (\d+) error", text)
    if not items and found is None:
        return _empty()
    errors = int(found.group(1)) if found else len(items)
    return {
        "parsed": True,
        "items": items[:_MAX_ITEMS],
        "summary": f"{errors} errors",
        "counts": {"errors": errors},
    }


def parse_tsc_output(text: str) -> dict[str, Any]:
    items = [
        {
            "file": m.group(1),
            "line": int(m.group(2)),
            "severity": m.group(4),
            "code": m.group(5),
            "message": m.group(6)[:300],
        }
        for m in _TSC_LINE_RE.finditer(text)
    ]
    items += [
        {
            "file": m.group(1),
            "line": int(m.group(2)),
            "severity": m.group(3),
            "code": m.group(4),
            "message": m.group(5)[:300],
        }
        for m in _TSC_ALT_LINE_RE.finditer(text)
    ]
    if not items:
        return _empty()
    errors = sum(1 for item in items if item["severity"] == "error")
    warnings = len(items) - errors
    return {
        "parsed": True,
        "items": items[:_MAX_ITEMS],
        "summary": f"{errors} errors, {warnings} warnings",
        "counts": {"errors": errors, "warnings": warnings},
    }


def parse_mypy_output(text: str) -> dict[str, Any]:
    items = [
        {
            "file": m.group(1),
            "line": int(m.group(2)),
            "severity": m.group(3),
            "message": m.group(4)[:300],
        }
        for m in _MYPY_LINE_RE.finditer(text)
    ]
    if not items:
        return _empty()
    errors = sum(1 for item in items if item["severity"] == "error")
    return {
        "parsed": True,
        "items": items[:_MAX_ITEMS],
        "summary": f"{errors} errors",
        "counts": {"errors": errors},
    }


def parse_test_output(text: str, runner: str) -> dict[str, Any]:
    result = (
        parse_pytest_output(text)
        if runner == "pytest"
        else parse_jest_output(text)
    )
    if result["parsed"]:
        return result
    # 未知输出格式时按 pytest → jest 顺序兜底尝试。
    for fallback in (parse_pytest_output, parse_jest_output):
        result = fallback(text)
        if result["parsed"]:
            return result
    return _empty()


def parse_lint_output(text: str, linter: str) -> dict[str, Any]:
    parsers = {
        "ruff": (parse_ruff_output,),
        "mypy": (parse_mypy_output,),
        "tsc": (parse_tsc_output,),
        "eslint": (parse_tsc_output,),
    }
    for parser in parsers.get(linter, (parse_ruff_output,)):
        result = parser(text)
        if result["parsed"]:
            return result
    # 兜底：ruff/mypy 输出格式相近，交叉尝试一次。
    for parser in (parse_ruff_output, parse_mypy_output, parse_tsc_output):
        result = parser(text)
        if result["parsed"]:
            return result
    return _empty()
