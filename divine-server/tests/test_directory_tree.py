"""Tests for directory_tree: gitignore filtering, show_sizes, limits."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "app" / "tools" / "scripts" / "directory_tree.py"


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


def _write(root: Path, rel: str, text: str = "x\n") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _paths(out: dict) -> list[str]:
    # entry["path"] is already relative to the scan base
    tree = json.loads(out["content"])["tree"]
    result: list[str] = []

    def walk(entries: list[dict]) -> None:
        for entry in entries:
            result.append(entry["path"])
            if entry["type"] == "dir" and entry.get("children"):
                walk(entry["children"])

    walk(tree)
    return result


@pytest.fixture()
def ws(tmp_path: Path) -> Path:
    _write(tmp_path, "src/app.py")
    _write(tmp_path, "src/util.py")
    _write(tmp_path, "README.md")
    _write(tmp_path, "ignored.txt")
    _write(tmp_path, "build/out.py")
    _write(tmp_path, "node_modules/pkg/index.js")
    _write(tmp_path, ".gitignore", "ignored.txt\nbuild/\n")
    return tmp_path


def test_basic_tree(ws: Path):
    out = _run(ws, {"depth": 3})
    assert out["success"] is True
    paths = _paths(out)
    assert "src/app.py" in paths
    assert "README.md" in paths


def test_gitignore_respected(ws: Path):
    out = _run(ws, {"depth": 3})
    paths = _paths(out)
    assert "ignored.txt" not in paths
    assert "build/out.py" not in paths


def test_heavy_dirs_skipped(ws: Path):
    out = _run(ws, {"depth": 3})
    paths = _paths(out)
    assert "node_modules" not in paths


def test_show_sizes_off_by_default(ws: Path):
    out = _run(ws, {})
    tree = json.loads(out["content"])["tree"]
    sizes = [entry.get("size") for entry in tree if entry["type"] == "file"]
    assert all(size is None for size in sizes)


def test_show_sizes_on(ws: Path):
    out = _run(ws, {"show_sizes": True})
    tree = json.loads(out["content"])["tree"]
    file_entries = [entry for entry in tree if entry["type"] == "file"]
    assert len(file_entries) >= 1
    assert all(isinstance(entry["size"], int) for entry in file_entries)


def test_depth_limits_recursion(ws: Path):
    _write(ws, "a/b/c/d/e/f.py")
    out = _run(ws, {"depth": 2})
    paths = _paths(out)
    assert "a/b" in paths
    assert "a/b/c/d" not in paths


def test_hidden_skipped(ws: Path):
    _write(ws, ".secret.py")
    out = _run(ws, {})
    paths = _paths(out)
    assert ".secret.py" not in paths
    out2 = _run(ws, {"show_hidden": True})
    assert ".secret.py" in _paths(out2)


def test_missing_directory(ws: Path):
    out = _run(ws, {"path": "nope"})
    assert out["success"] is False
