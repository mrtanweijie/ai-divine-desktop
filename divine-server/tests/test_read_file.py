"""Tests for read_file script: truncation hint and line ranges."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "app" / "tools" / "scripts" / "read_file.py"


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


def test_truncation_hint_present(tmp_path: Path):
    path = tmp_path / "big.py"
    # ~16KB total, well beyond the 12K char cap
    path.write_text("".join(f"line {i}: " + "x" * 60 + "\n" for i in range(250)), encoding="utf-8")
    out = _run(tmp_path, {"file_path": "big.py"})
    assert out["success"] is True
    assert out["truncated"] is True
    assert "继续读取" in out["content"]
    assert "start_line=" in out["content"]


def test_small_file_no_hint(tmp_path: Path):
    (tmp_path / "small.py").write_text("print('hi')\n", encoding="utf-8")
    out = _run(tmp_path, {"file_path": "small.py"})
    assert out["success"] is True
    assert out["truncated"] is False
    assert "继续读取" not in out["content"]


def test_line_range(tmp_path: Path):
    path = tmp_path / "ranged.py"
    path.write_text("".join(f"line{i}\n" for i in range(1, 51)), encoding="utf-8")
    out = _run(tmp_path, {"file_path": "ranged.py", "start_line": 10, "end_line": 12})
    assert out["success"] is True
    content = out["content"]
    assert "line10" in content and "line12" in content
    assert "line9" not in content and "line13" not in content
    assert out["data"]["total_lines"] == 50


def test_missing_file(tmp_path: Path):
    out = _run(tmp_path, {"file_path": "nope.txt"})
    assert out["success"] is False
