"""Pytest plugin that records per-test outcomes to a JSON file.

Loaded inside the grading subprocess via ``-p evals_pytest_plugin`` with
``EVALS_DIR`` on PYTHONPATH. The output path comes from the
``EVAL_PYTEST_JSON`` environment variable. This gives the harness exact
nodeids (``tests/test_x.py::test_y``) instead of fragile stdout parsing.
"""

from __future__ import annotations

import json
import os

_RESULTS: list[dict[str, str]] = []


def pytest_runtest_logreport(report) -> None:  # noqa: ANN001
    outcome = None
    if report.when == "call":
        outcome = report.outcome
    elif report.when == "setup" and report.outcome == "failed":
        # Collection/fixture error: the test never ran.
        outcome = "errored"
    if outcome is not None:
        _RESULTS.append({"nodeid": report.nodeid, "outcome": outcome})


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ANN001
    path = os.environ.get("EVAL_PYTEST_JSON")
    if not path:
        return
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(_RESULTS, handle, ensure_ascii=False)
