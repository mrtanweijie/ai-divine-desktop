"""Office 工具注册与门控约定（docs/design/017-office-edit-closed-loop-20260906.md §5.6/§6）。

关键断言：
- 三个新工具已注册，document_outline 是只读工具（免 plan-first、可并行）；
- 编辑工具**不在** _READ_ONLY_TOOLS/_NO_PLAN_TOOLS（自动获得 plan-first 门控）；
- 编辑工具**不在** _CONTENT_TOOLS（常驻注入，防止意图漏判裁剪掉编辑能力）；
- execution 层 _OFFICE_EDIT_TOOLS 有意不含 document_outline 且不并入 _EDIT_TOOLS。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_office_tools_registered():
    from app.tools.registry import registry

    names = {meta["name"] for meta in registry.list()}
    assert {
        "document_outline",
        "fill_template",
        "edit_docx",
        "edit_xlsx",
        "edit_pptx",
        "pdf_form_fields",
        "pdf_form_fill",
        "pdf_to_word",
    } <= names


def test_document_outline_is_read_only_and_lock_free():
    from app.agent.core.constants import _READ_ONLY_TOOLS
    from app.agent.tools.tools import _LOCK_FREE_TOOLS

    assert "document_outline" in _READ_ONLY_TOOLS
    assert "document_outline" in _LOCK_FREE_TOOLS


def test_edit_tools_get_plan_first_and_are_not_content_gated():
    from app.agent.core.constants import _READ_ONLY_TOOLS
    from app.agent.tools.tools import _CONTENT_TOOLS

    for name in ("fill_template", "edit_docx"):
        assert name not in _READ_ONLY_TOOLS  # 非只读 → 自动 plan-first
        assert name not in _CONTENT_TOOLS  # 常驻注入，防意图漏判
        assert name not in _NO_PLAN_TOOLS_SET()
    assert "edit_xlsx" not in _READ_ONLY_TOOLS
    assert "edit_xlsx" not in _CONTENT_TOOLS
    assert "pdf_form_fields" in _READ_ONLY_TOOLS
    assert "pdf_form_fill" not in _READ_ONLY_TOOLS
    assert "pdf_form_fill" not in _CONTENT_TOOLS


def _NO_PLAN_TOOLS_SET():
    from app.agent.core.constants import _NO_PLAN_TOOLS

    return _NO_PLAN_TOOLS


def test_execution_layer_office_set_is_isolated_from_edit_tools():
    from app.agent.tools.execution import _EDIT_TOOLS, _OFFICE_EDIT_TOOLS

    assert _OFFICE_EDIT_TOOLS == {
        "fill_template",
        "edit_docx",
        "edit_xlsx",
        "edit_pptx",
        "pdf_form_fill",
    }
    assert _OFFICE_EDIT_TOOLS.isdisjoint(_EDIT_TOOLS)


def test_external_paths_declared_for_edit_tools(tmp_path):
    from app.tools.registry import registry

    workspace = tmp_path / "ws"
    workspace.mkdir()
    external = tmp_path / "Desktop" / "合同.docx"

    for name in ("fill_template", "edit_docx", "edit_xlsx", "edit_pptx", "pdf_form_fields", "pdf_form_fill", "pdf_to_word", "document_outline"):
        adapter = registry.get(name)
        assert adapter is not None
        assert adapter.allow_external_paths is True
        suffix = {"edit_xlsx": ".xlsx", "edit_pptx": ".pptx", "pdf_form_fields": ".pdf", "pdf_form_fill": ".pdf", "pdf_to_word": ".pdf"}.get(name, ".docx")
        path_arg = str(external).replace("合同.docx", "合同" + suffix)
        assert adapter.external_paths(workspace, {"path": path_arg}) == [path_arg]
        # workspace 内路径不触发外部确认
        inside = workspace / "report.docx"
        assert adapter.external_paths(workspace, {"path": str(inside)}) == []
