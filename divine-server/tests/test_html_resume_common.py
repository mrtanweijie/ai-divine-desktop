"""html_resume / html_common 工具回归：简历 HTML 专用管线与原样保存。"""

import io
import json
import shutil
from pathlib import Path

from app.docgen.resume.sample_data import SAMPLE_RESUME
from app.tools.registry import get_tool
from app.tools.scripts import html_common as html_common_script
from app.tools.scripts import html_resume as html_resume_script

_OUTPUT_DIR = "/tmp/divine_html_tools_test"


def _run(script_module, params: dict, monkeypatch, capsys) -> dict:
    payload = {
        "workspace": "/tmp",
        "output_dir": _OUTPUT_DIR,
        "params": params,
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    script_module.main()
    return json.loads(capsys.readouterr().out)


def setup_function(_):
    shutil.rmtree(_OUTPUT_DIR, ignore_errors=True)


# ---------------------------------------------------------------------------
# html_resume：简历 HTML 专用（无 PDF）
# ---------------------------------------------------------------------------


def test_html_resume_outputs_editable_and_clean(monkeypatch, capsys):
    result = _run(
        html_resume_script,
        {"resume_data": SAMPLE_RESUME, "template": "tpl_modern"},
        monkeypatch,
        capsys,
    )
    assert result["success"] is True
    assert "可编辑" in result["message"]
    editable = Path(result["filepath"])
    assert editable.suffix == ".html" and editable.exists()
    text = editable.read_text(encoding="utf-8")
    assert SAMPLE_RESUME["name"] in text
    assert ' contenteditable="true"' in text
    clean = Path(result["data"]["clean_filepath"])
    assert clean.exists()
    assert ' contenteditable="true"' not in clean.read_text(encoding="utf-8")


def test_html_resume_rejects_unknown_template(monkeypatch, capsys):
    result = _run(
        html_resume_script,
        {"resume_data": SAMPLE_RESUME, "template": "tpl_nonexistent"},
        monkeypatch,
        capsys,
    )
    assert result["success"] is False
    assert "tpl_professional" in result["message"]


def test_html_resume_requires_resume_data(monkeypatch, capsys):
    result = _run(html_resume_script, {}, monkeypatch, capsys)
    assert result["success"] is False
    assert "resume_data" in result["message"]


def test_html_resume_multi_layout(monkeypatch, capsys):
    result = _run(
        html_resume_script,
        {"resume_data": SAMPLE_RESUME, "template": "tpl_professional", "layout": "multi"},
        monkeypatch,
        capsys,
    )
    assert result["success"] is True
    assert result["data"]["layout"] == "multi"
    editable = Path(result["filepath"]).read_text(encoding="utf-8")
    assert "margin:10mm 0 11mm" in editable  # 多页打印 CSS 已注入


def test_html_resume_tool_description_pdf_free():
    tool = get_tool("html_resume")
    assert tool is not None
    assert "不产出 PDF" in tool.description
    assert "pdf_generate" in tool.description


# ---------------------------------------------------------------------------
# html_common：原样保存，不注入基座
# ---------------------------------------------------------------------------

_CUSTOM_HTML = """<!DOCTYPE html><html><head><title>木木的自定义简历模板</title>
<style>h1{color:teal}</style></head>
<body><h1>木木</h1><div class="my-own-layout">自定义版式</div></body></html>"""


def test_html_common_saves_verbatim_without_scaffold(monkeypatch, capsys):
    result = _run(html_common_script, {"content": _CUSTOM_HTML}, monkeypatch, capsys)
    assert result["success"] is True
    assert "原样保存" in result["message"]
    saved = Path(result["filepath"])
    assert saved.read_text(encoding="utf-8") == _CUSTOM_HTML
    assert 'id="divine-scaffold"' not in saved.read_text(encoding="utf-8")
    assert result["data"]["title"] == "木木的自定义简历模板"


def test_html_common_requires_complete_html(monkeypatch, capsys):
    result = _run(html_common_script, {"content": "<div>片段</div>"}, monkeypatch, capsys)
    assert result["success"] is False
    assert "DOCTYPE" in result["message"]


def test_html_common_tool_description():
    tool = get_tool("html_common")
    assert tool is not None
    assert "不注入" in tool.description
    assert "html_resume" in tool.description  # 指引简历默认路径


# ---------------------------------------------------------------------------
# 意图门槛：简历/网页意图轮次两个新工具都可用
# ---------------------------------------------------------------------------


def test_new_tools_gating():
    from app.agent.tools.tools import _content_tool_allowed

    for intents in ({"resume"}, {"html"}, {"pdf"}):
        assert _content_tool_allowed("html_resume", intents)
    for intents in ({"resume"}, {"html"}):
        assert _content_tool_allowed("html_common", intents)
    assert _content_tool_allowed("html_resume", set())
    assert _content_tool_allowed("html_common", set())
    assert not _content_tool_allowed("html_common", {"image"})
    assert not _content_tool_allowed("html_common", {"pdf"})
