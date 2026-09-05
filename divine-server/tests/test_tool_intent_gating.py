"""意图工具裁剪回归：简历/网页意图轮次必须保留 pdf_generate 模板管线。

背景：曾因 _CONTENT_TOOLS 只把 pdf_generate 挂在 "pdf" 意图上，
用户追问轮（"换个主题色重新生成"，仅命中 html 意图）拿不到该工具，
模型被迫用 html_generate 手写简历。
"""

from app.agent.tools.tools import _content_tool_allowed


def test_pdf_generate_survives_resume_intent():
    """用户输入「简历」触发 resume 意图，pdf_generate 必须可用。"""
    assert _content_tool_allowed("pdf_generate", {"resume"})


def test_pdf_generate_survives_html_intent():
    """追问轮（换色/重生成）常只命中 html 意图，pdf_generate 必须可用。"""
    assert _content_tool_allowed("pdf_generate", {"html"})


def test_pdf_generate_survives_pdf_intent_and_unions():
    for intents in ({"pdf"}, {"resume", "html"}, {"pdf", "image"}):
        assert _content_tool_allowed("pdf_generate", intents)


def test_pdf_generate_pruned_for_unrelated_intent():
    assert not _content_tool_allowed("pdf_generate", {"image"})


def test_empty_intents_allow_all():
    assert _content_tool_allowed("pdf_generate", set())
    assert _content_tool_allowed("ux_html", set())


def test_single_intent_gates_unchanged():
    assert _content_tool_allowed("ux_html", {"ux"})
    assert not _content_tool_allowed("ux_html", {"html"})
    assert not _content_tool_allowed("presentation", {"resume"})
    assert _content_tool_allowed("generate_chart", {"chart"})
