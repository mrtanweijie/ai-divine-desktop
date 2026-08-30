"""Tests for project skeleton auto-injection (agent/project_context.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agent.middleware import (
    build_project_context,
    clear_project_context_cache,
    _looks_like_project,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_project_context_cache()
    yield
    clear_project_context_cache()


def _make_project(root: Path) -> None:
    (root / "README.md").write_text(
        "# MyProject\n\nA demo project for tests.\n", encoding="utf-8"
    )
    (root / "package.json").write_text(
        json.dumps(
            {
                "name": "my-project",
                "version": "1.2.3",
                "scripts": {"dev": "vite", "build": "tsc && vite build"},
                "dependencies": {"react": "^19"},
            }
        ),
        encoding="utf-8",
    )
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "index.ts").write_text("export const x = 1;\n", encoding="utf-8")
    (src / "generated.ts").write_text("// generated\n", encoding="utf-8")
    (root / ".gitignore").write_text("src/generated.ts\nnode_modules/\n", encoding="utf-8")


def test_looks_like_project_with_manifest(tmp_path: Path):
    assert _looks_like_project(tmp_path) is False
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    assert _looks_like_project(tmp_path) is True


def test_looks_like_project_with_git_dir(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    assert _looks_like_project(tmp_path) is True


def test_build_project_context(tmp_path: Path):
    _make_project(tmp_path)
    block = build_project_context(tmp_path, "s1")
    assert block is not None
    assert "MyProject" in block
    assert "my-project" in block
    assert "version=1.2.3" in block
    assert "scripts=[dev, build]" in block
    assert "src/index.ts" in block
    # gitignored and heavy dirs are excluded from the tree
    assert "src/generated.ts" not in block
    assert "node_modules/" not in block  # as a tree entry (header text mentions it)


def test_non_project_returns_none(tmp_path: Path):
    assert build_project_context(tmp_path, "s1") is None


def test_cache_reused(tmp_path: Path):
    _make_project(tmp_path)
    first = build_project_context(tmp_path, "s2")
    second = build_project_context(tmp_path, "s2")
    assert first is second  # cached object


def test_cache_invalidated_on_change(tmp_path: Path):
    _make_project(tmp_path)
    first = build_project_context(tmp_path, "s3")
    assert "version=9.9.9" not in (first or "")
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "my-project", "version": "9.9.9"}), encoding="utf-8"
    )
    second = build_project_context(tmp_path, "s3")
    assert second is not None
    assert "version=9.9.9" in second


def test_pyproject_summary(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = ["fastapi"]\n',
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    block = build_project_context(tmp_path, "s4")
    assert block is not None
    assert "pyproject.toml" in block
    assert "name=demo" in block


def test_requirements_summary(tmp_path: Path):
    (tmp_path / "requirements.txt").write_text(
        "fastapi>=0.111\nuvicorn\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("# R\n", encoding="utf-8")
    block = build_project_context(tmp_path, "s5")
    assert block is not None
    assert "fastapi>=0.111" in block
