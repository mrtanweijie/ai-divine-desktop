"""编辑后自动语法检查（P3-3a）：路径提取 + 各类型检查行为。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tools.syntax_check import (  # noqa: E402
    edited_paths,
    syntax_check_paths,
)


def test_edited_paths_edit_files_relative_resolved(tmp_path):
    args = {
        "files": [
            {"path": "src/a.py", "search": "x", "replace": "y"},
            {"path": "src/a.py", "search": "z", "replace": "w"},  # 去重
            {"path": str(tmp_path / "abs.py"), "search": "", "replace": "n"},
        ]
    }
    paths = edited_paths("edit_files", args, tmp_path)
    assert paths == [
        str(tmp_path / "src" / "a.py"),
        str(tmp_path / "abs.py"),
    ]


def test_edited_paths_write_and_edit_lines(tmp_path):
    assert edited_paths("write_file", {"path": "b.py"}, tmp_path) == [
        str(tmp_path / "b.py")
    ]
    assert edited_paths("edit_lines", {"path": "c.py", "edits": []}, tmp_path) == [
        str(tmp_path / "c.py")
    ]


def test_edited_paths_apply_patch_targets(tmp_path):
    patch = (
        "--- a/mod.py\n"
        "+++ b/mod.py\n"
        "@@ -1 +1 @@\n"
        "--- /dev/null\n"
        "+++ b/new.py\n"
    )
    assert edited_paths("apply_patch", {"patch": patch}, tmp_path) == [
        str(tmp_path / "mod.py"),
        str(tmp_path / "new.py"),
    ]


def test_good_python_passes(tmp_path):
    good = tmp_path / "good.py"
    good.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    assert syntax_check_paths([str(good)]) == []


def test_broken_python_reported(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("def f(:\n    pass\n", encoding="utf-8")
    problems = syntax_check_paths([str(bad)])
    assert len(problems) == 1
    assert "bad.py" in problems[0]


def test_broken_json_reported_good_json_passes(tmp_path):
    good = tmp_path / "good.json"
    good.write_text('{"a": 1}', encoding="utf-8")
    assert syntax_check_paths([str(good)]) == []
    bad = tmp_path / "bad.json"
    bad.write_text('{"a": ', encoding="utf-8")
    problems = syntax_check_paths([str(bad)])
    assert len(problems) == 1
    assert "JSON" in problems[0]


def test_yaml_checked_when_available(tmp_path):
    good = tmp_path / "good.yaml"
    good.write_text("a: 1\n", encoding="utf-8")
    bad = tmp_path / "bad.yaml"
    bad.write_text("a: [1,\n", encoding="utf-8")
    problems = syntax_check_paths([str(good), str(bad)])
    try:
        import yaml  # noqa: F401

        assert len(problems) == 1
        assert "YAML" in problems[0]
    except ImportError:
        assert problems == []


def test_missing_and_exotic_files_skipped(tmp_path):
    problems = syntax_check_paths(
        [str(tmp_path / "nope.py"), str(tmp_path / "pic.png")]
    )
    assert problems == []
