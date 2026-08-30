"""项目指令文件注入：.divine.md / AGENTS.md / CLAUDE.md（P3-2c）。

用户在仓库根写指令文件（构建命令、代码规范、已知坑），agent 每轮自动
读取并注入 prompt。按优先级取第一个存在的文件；编辑后指纹变化立即生效。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.middleware.project_context import (  # noqa: E402
    _INSTRUCTION_MAX_CHARS,
    clear_project_context_cache,
    build_project_context,
)


def _make_project(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / ".git").mkdir()  # _looks_like_project 识别为项目
    return ws


def teardown_function():
    clear_project_context_cache()


def test_divine_md_injected(tmp_path):
    ws = _make_project(tmp_path)
    (ws / ".divine.md").write_text("构建：make build\n测试：make test", encoding="utf-8")
    block = build_project_context(ws, "sess-instr-1")
    assert block is not None
    assert "make build" in block
    assert "项目指令" in block


def test_priority_divine_md_wins(tmp_path):
    ws = _make_project(tmp_path)
    (ws / ".divine.md").write_text("divine rules", encoding="utf-8")
    (ws / "AGENTS.md").write_text("agents rules", encoding="utf-8")
    block = build_project_context(ws, "sess-instr-2")
    assert "divine rules" in block
    assert "agents rules" not in block


def test_agents_md_and_claude_md_fallback(tmp_path):
    ws = _make_project(tmp_path)
    (ws / "AGENTS.md").write_text("agents rules", encoding="utf-8")
    block = build_project_context(ws, "sess-instr-3")
    assert "agents rules" in block

    clear_project_context_cache()
    ws2 = tmp_path / "ws2"
    ws2.mkdir()
    (ws2 / ".git").mkdir()
    (ws2 / "CLAUDE.md").write_text("claude rules", encoding="utf-8")
    block2 = build_project_context(ws2, "sess-instr-4")
    assert "claude rules" in block2


def test_edit_invalidates_cache(tmp_path):
    ws = _make_project(tmp_path)
    (ws / ".divine.md").write_text("v1 rules", encoding="utf-8")
    assert "v1 rules" in build_project_context(ws, "sess-instr-5")
    time.sleep(0.02)  # 确保 mtime 变化
    (ws / ".divine.md").write_text("v2 rules", encoding="utf-8")
    assert "v2 rules" in build_project_context(ws, "sess-instr-5")


def test_oversized_instruction_truncated(tmp_path):
    ws = _make_project(tmp_path)
    (ws / ".divine.md").write_text("x" * (_INSTRUCTION_MAX_CHARS + 500), encoding="utf-8")
    block = build_project_context(ws, "sess-instr-6")
    assert block is not None
    assert "已截断" in block
    assert len(block) < _INSTRUCTION_MAX_CHARS + 500


def test_no_instruction_file_no_block(tmp_path):
    ws = _make_project(tmp_path)
    block = build_project_context(ws, "sess-instr-7")
    # 没有指令/manifest/树时返回 None，不注入空块
    assert block is None or "项目指令" not in block
