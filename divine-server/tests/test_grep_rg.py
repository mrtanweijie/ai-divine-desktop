"""ripgrep 引擎改造测试：快速路径 + Python 兜底（P4）。

- 系统/打包目录存在 rg → 走 ripgrep 引擎（--no-require-git 使非 git 目录
  也尊重 .gitignore，与 Python 引擎行为一致）；
- rg 不支持 lookahead 语法 → 自动回退 Python 引擎；
- rg 不可用（monkeypatch）→ 纯 Python 引擎照常工作。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tools.scripts import grep_files  # noqa: E402


def test_engine_is_ripgrep_when_available(tmp_path: Path):
    if grep_files._rg_binary() is None:
        import pytest

        pytest.skip("rg 不可用")
    (tmp_path / "a.py").write_text("needle here\n", encoding="utf-8")
    out = grep_files.run_tool(tmp_path, {"pattern": "needle"})
    assert out["success"] is True
    assert out["data"]["engine"] == "ripgrep"
    assert out["data"]["total"] == 1


def test_lookahead_falls_back_to_python(tmp_path: Path):
    if grep_files._rg_binary() is None:
        import pytest

        pytest.skip("rg 不可用")
    (tmp_path / "a.py").write_text("price: 42\n", encoding="utf-8")
    # rust regex 不支持 lookahead，rg 会报错 → 自动回退 Python
    out = grep_files.run_tool(tmp_path, {"pattern": r"price: (?=\d+)"})
    assert out["success"] is True
    assert out["data"]["engine"] == "python"
    assert out["data"]["total"] == 1


def test_python_engine_when_rg_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(grep_files, "_rg_binary", lambda: None)
    (tmp_path / "a.py").write_text("needle here\n", encoding="utf-8")
    out = grep_files.run_tool(tmp_path, {"pattern": "needle"})
    assert out["success"] is True
    assert out["data"]["engine"] == "python"
    assert out["data"]["total"] == 1


def test_gitignore_respected_without_git_dir(tmp_path: Path):
    # --no-require-git：非 git 仓库也要尊重 .gitignore（与旧行为一致）
    (tmp_path / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("needle\n", encoding="utf-8")
    (tmp_path / "kept.txt").write_text("needle\n", encoding="utf-8")
    out = grep_files.run_tool(tmp_path, {"pattern": "needle"})
    assert "kept.txt" in out["content"]
    assert "ignored.txt" not in out["content"]


def test_heavy_dirs_pruned_by_rg(tmp_path: Path):
    if grep_files._rg_binary() is None:
        import pytest

        pytest.skip("rg 不可用")
    heavy = tmp_path / "node_modules" / "pkg"
    heavy.mkdir(parents=True)
    (heavy / "a.js").write_text("needle\n", encoding="utf-8")
    (tmp_path / "b.js").write_text("needle\n", encoding="utf-8")
    out = grep_files.run_tool(tmp_path, {"pattern": "needle"})
    assert "node_modules" not in out["content"]
    assert out["data"]["total"] == 1
