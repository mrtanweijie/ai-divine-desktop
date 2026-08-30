"""Tests for the grep_files content-search tool (script + adapter wiring)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.agent.core import _READ_ONLY_TOOLS
from app.agent.tools.subagents import _SUBAGENT_READ_ONLY_TOOLS
from app.tools.adapters.grep_files import GrepFilesAdapter
from app.tools.registry import get_tool

SCRIPT = Path(__file__).resolve().parents[1] / "app" / "tools" / "scripts" / "grep_files.py"


def _run(workspace: Path, params: dict) -> dict:
    payload = {
        "workspace": str(workspace.resolve()),
        "output_dir": str(workspace.resolve() / "out"),
        "params": params,
        "locale": "zh-CN",
    }
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    _write(
        tmp_path,
        "src/app.py",
        "import os\n\n\ndef foo():\n    return 42\n\n\ndef bar():\n    return foo()\n",
    )
    _write(
        tmp_path,
        "src/util.py",
        "# helper\nFOO_CONST = 'abc'\n\ndef helper(x):\n    return x\n",
    )
    _write(tmp_path, "README.md", "# Demo\n\nfoo is documented here.\n")
    _write(tmp_path, "ignored.txt", "foo should not be found\n")
    _write(tmp_path, ".gitignore", "ignored.txt\nbuild/\n")
    _write(tmp_path, "build/out.py", "foo in build output\n")
    return tmp_path


# --- script behavior ---


def test_basic_match(workspace: Path):
    out = _run(workspace, {"pattern": r"def foo"})
    assert out["success"] is True
    assert "src/app.py:4:" in out["content"]
    assert out["data"]["total"] == 1


def test_matches_multiple_files(workspace: Path):
    out = _run(workspace, {"pattern": "foo"})
    assert out["success"] is True
    assert "src/app.py:" in out["content"]
    assert "README.md:" in out["content"]
    assert "ignored.txt" not in out["content"]
    assert "build/out.py" not in out["content"]


def test_case_insensitive_by_default(workspace: Path):
    out = _run(workspace, {"pattern": "FOO_CONST"})
    assert out["success"] is True
    assert "src/util.py:" in out["content"]
    assert out["data"]["total"] >= 1


def test_case_sensitive(workspace: Path):
    out = _run(workspace, {"pattern": "FOO_CONST", "case_sensitive": True})
    assert out["success"] is True
    assert "src/util.py:" in out["content"]
    out2 = _run(workspace, {"pattern": "foo_const", "case_sensitive": True})
    assert out2["data"]["total"] == 0


def test_glob_filter(workspace: Path):
    out = _run(workspace, {"pattern": "foo", "glob": "*.py"})
    assert out["success"] is True
    assert "src/app.py:" in out["content"]
    assert "README.md" not in out["content"]


def test_context_lines(workspace: Path):
    out = _run(workspace, {"pattern": r"return 42", "context": 1})
    assert out["success"] is True
    content = out["content"]
    # match line (line 5) plus one context line (4- or 6-)
    assert "5:     return 42" in content
    assert "4-" in content or "6-" in content


def test_subdirectory_search(workspace: Path):
    out = _run(workspace, {"pattern": "helper", "path": "src"})
    assert out["success"] is True
    assert "util.py:" in out["content"]
    assert "README" not in out["content"]


def test_max_results_truncation(workspace: Path):
    for i in range(5):
        _write(workspace, f"many/f{i}.py", f"x = {i}\n# needle\n")
    out = _run(workspace, {"pattern": "needle", "max_results": 2})
    assert out["success"] is True
    assert out["data"]["total"] == 2
    assert out["data"]["truncated"] is True


def test_invalid_regex(workspace: Path):
    out = _run(workspace, {"pattern": "("})
    assert out["success"] is False
    assert "正则" in out["message"]


def test_empty_pattern(workspace: Path):
    out = _run(workspace, {"pattern": ""})
    assert out["success"] is False


def test_missing_directory(workspace: Path):
    out = _run(workspace, {"pattern": "x", "path": "nope"})
    assert out["success"] is False
    assert "不存在" in out["message"]


def test_gitignore_dir_pruned(workspace: Path):
    _write(workspace, "build/sub.py", "needle inside build\n")
    out = _run(workspace, {"pattern": "needle"})
    assert "build/" not in out["content"]


def test_hidden_skipped_and_included(workspace: Path):
    _write(workspace, ".env", "SECRET=foo123\n")
    out = _run(workspace, {"pattern": "SECRET"})
    assert out["data"]["total"] == 0
    out2 = _run(workspace, {"pattern": "SECRET", "include_hidden": True})
    assert out2["data"]["total"] == 1
    assert ".env:" in out2["content"]


def test_binary_skipped(workspace: Path):
    (workspace / "blob.bin").write_bytes(b"\x00\x01\x02foo\x00")
    out = _run(workspace, {"pattern": "foo"})
    assert "blob.bin" not in out["content"]


def test_negation_in_gitignore(workspace: Path):
    _write(workspace, ".gitignore", "*.log\n!keep.log\n")
    _write(workspace, "a.log", "needle\n")
    _write(workspace, "keep.log", "needle\n")
    out = _run(workspace, {"pattern": "needle"})
    assert "a.log" not in out["content"]
    assert "keep.log" in out["content"]


# --- adapter wiring ---


def test_adapter_registered():
    adapter = get_tool("grep_files")
    assert adapter is not None
    assert isinstance(adapter, GrepFilesAdapter)
    assert adapter.script_name == "grep_files.py"


def test_in_read_only_sets():
    assert "grep_files" in _READ_ONLY_TOOLS
    assert "grep_files" in _SUBAGENT_READ_ONLY_TOOLS


def test_external_path_detected(tmp_path: Path, workspace: Path):
    outside = tmp_path.parent / "outside_grep"
    outside.mkdir(exist_ok=True)
    adapter = get_tool("grep_files")
    assert adapter is not None
    paths = adapter.external_paths(workspace, {"path": str(outside)})
    assert paths == [str(outside.resolve())]
    paths_in = adapter.external_paths(workspace, {"path": "src"})
    assert paths_in == []
