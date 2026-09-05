"""html_generate 的简历护栏：简历类页面拒绝保存并重定向到 pdf_generate 模板管线。"""

import io
import json
import shutil
from pathlib import Path

from app.tools.registry import get_tool
from app.tools.scripts import html_generate as hg

_OUTPUT_DIR = "/tmp/divine_resume_guard_test"

_RESUME_HTML = """<!DOCTYPE html><html><head><title>陈一鸣 - 资深前端简历</title></head>
<body><h1>陈一鸣</h1>
<h2>工作经历</h2><p>某科技公司</p>
<h2>教育背景</h2><p>某大学</p>
<h2>专业技能</h2><p>React</p>
<h2>项目经历</h2><p>某平台</p>
</body></html>"""

_CLASS_HIT_HTML = """<!DOCTYPE html><html><head><title>我的个人页面</title></head>
<body><div class="resume-header">陈一鸣</div><div class="resume-body">内容</div></body></html>"""

_REPORT_HTML = """<!DOCTYPE html><html><head><title>2026 年度数据分析报告</title></head>
<body><h1>年度经营分析</h1><p>营收增长 23%，详见下表。</p>
<div class="chart">内联 SVG 图表</div>
</body></html>"""


def _run_script(params: dict, monkeypatch, capsys) -> dict:
    payload = {
        "workspace": "/tmp",
        "output_dir": _OUTPUT_DIR,
        "params": params,
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    hg.main()
    out = capsys.readouterr().out
    return json.loads(out)


def setup_function(_):
    shutil.rmtree(_OUTPUT_DIR, ignore_errors=True)


# ---------------------------------------------------------------------------
# detect_resume_page：三种命中路径 + 不误伤普通报告
# ---------------------------------------------------------------------------


def test_detect_by_title():
    reason = hg.detect_resume_page("陈一鸣 - 前端简历", _REPORT_HTML)
    assert reason and "简历" in reason


def test_detect_by_resume_class():
    reason = hg.detect_resume_page("我的个人页面", _CLASS_HIT_HTML)
    assert reason and "resume" in reason


def test_detect_by_section_markers():
    no_title = _RESUME_HTML.replace("陈一鸣 - 资深前端简历", "个人主页")
    reason = hg.detect_resume_page("个人主页", no_title)
    assert reason and "章节标题" in reason


def test_normal_report_not_flagged():
    assert hg.detect_resume_page("2026 年度数据分析报告", _REPORT_HTML) is None


# ---------------------------------------------------------------------------
# 脚本端到端：拦截、重定向文案、force_save 逃生
# ---------------------------------------------------------------------------


def test_script_rejects_resume_and_redirects(monkeypatch, capsys):
    result = _run_script({"content": _RESUME_HTML}, monkeypatch, capsys)
    assert result["success"] is False
    assert "pdf_generate" in result["message"]
    assert "force_save" in result["message"]
    # 不应落盘
    assert not list(Path(_OUTPUT_DIR).rglob("*.html"))


def test_script_rejects_resume_class_hit(monkeypatch, capsys):
    result = _run_script({"content": _CLASS_HIT_HTML}, monkeypatch, capsys)
    assert result["success"] is False
    assert "pdf_generate" in result["message"]


def test_script_force_save_escape(monkeypatch, capsys):
    result = _run_script(
        {"content": _RESUME_HTML, "force_save": True}, monkeypatch, capsys
    )
    assert result["success"] is True
    assert list(Path(_OUTPUT_DIR).rglob("*.html"))


def test_script_saves_normal_report(monkeypatch, capsys):
    result = _run_script({"content": _REPORT_HTML}, monkeypatch, capsys)
    assert result["success"] is True
    assert list(Path(_OUTPUT_DIR).rglob("*.html"))


# ---------------------------------------------------------------------------
# 工具描述与参数：LLM 看到的接口本身不再包含简历用例
# ---------------------------------------------------------------------------


def test_adapter_description_excludes_resume_usecase():
    tool = get_tool("html_generate")
    assert tool is not None
    assert "落地页" in tool.description  # 用例清单仍在
    assert "简历、文档网页版" not in tool.description  # 旧描述中的简历用例已移除
    assert "pdf_generate" in tool.description  # 重定向指引可见


def test_adapter_build_params_passes_force_save():
    tool = get_tool("html_generate")
    params = tool.build_params({"content": "<html></html>", "force_save": True})
    assert params["force_save"] is True
    default_params = tool.build_params({"content": "<html></html>"})
    assert default_params["force_save"] is False
