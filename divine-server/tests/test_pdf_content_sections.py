"""内容生成两段式（大纲→分章）与自检测试。"""

import asyncio

from app.docgen.pdf.base import PDFIntent
from app.docgen.pdf.content import generate_content
from app.docgen.pdf.recipes import ReportRecipe, ResumeRecipe


class FakeLLM:
    """按调用次序返回预设响应的最小 LLM 桩。"""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls = 0

    async def stream(self, messages):
        index = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        yield {"type": "message", "content": self._responses[index]}


def _intent(sections: list[dict]) -> PDFIntent:
    return PDFIntent(
        title="测试文档",
        topic="测试主题",
        style="universal",
        color_scheme="blue",
        sections=sections,
        meta={},
    )


def test_short_doc_single_shot():
    sections = [
        {"title": "背景", "key_points": ["a"]},
        {"title": "结论", "key_points": ["b"]},
    ]
    llm = FakeLLM(["## 背景\n\n内容A\n\n## 结论\n\n内容B"])
    intent = _intent(sections)
    markdown = asyncio.run(generate_content(intent, ReportRecipe(), llm))
    assert llm.calls == 1
    assert "## 背景" in markdown
    assert intent.meta["content_qa"]["mode"] == "single"


def test_long_doc_generated_by_sections():
    titles = ["章节一", "章节二", "章节三", "章节四"]
    sections = [{"title": t, "key_points": [f"{t}要点"]} for t in titles]
    llm = FakeLLM(
        [f"## {t}\n\n{body}部分内容" for t, body in zip(titles, "甲乙丙丁")]
    )
    intent = _intent(sections)
    markdown = asyncio.run(generate_content(intent, ReportRecipe(), llm))
    assert llm.calls == 4
    for token in ("## 章节一", "## 章节二", "## 章节三", "## 章节四", "甲", "丁"):
        assert token in markdown
    qa = intent.meta["content_qa"]
    assert qa["mode"] == "sections"
    assert qa["regenerated"] == []
    assert qa["unresolved_sections"] == []
    assert qa["placeholders_left"] == 0


def test_missing_section_title_regenerated_once():
    titles = ["章节一", "章节二", "章节三", "章节四"]
    sections = [{"title": t, "key_points": ["x"]} for t in titles]
    llm = FakeLLM(
        [
            "## 章节一\n\n甲",
            "跑题内容，没有输出任何标题",  # 章节二缺失 → strict 重试
            "## 章节三\n\n丙",
            "## 章节四\n\n丁",
            "## 章节二\n\n乙补写完成",
        ]
    )
    intent = _intent(sections)
    markdown = asyncio.run(generate_content(intent, ReportRecipe(), llm))
    assert llm.calls == 5
    assert "## 章节二" in markdown
    assert "乙补写完成" in markdown
    qa = intent.meta["content_qa"]
    assert qa["regenerated"] == ["章节二"]


def test_placeholder_section_regenerated():
    titles = ["章节一", "章节二", "章节三", "章节四"]
    sections = [{"title": t, "key_points": ["x"]} for t in titles]
    llm = FakeLLM(
        [
            "## 章节一\n\n甲",
            "## 章节二\n\n该指标数据待补充",
            "## 章节三\n\n丙",
            "## 章节四\n\n丁",
            "## 章节二\n\n乙含完整定性描述",
        ]
    )
    intent = _intent(sections)
    markdown = asyncio.run(generate_content(intent, ReportRecipe(), llm))
    assert llm.calls == 5
    assert "乙含完整定性描述" in markdown
    assert intent.meta["content_qa"]["placeholders_left"] == 0
    assert intent.meta["content_qa"]["regenerated"] == ["章节二"]


def test_section_text_mentioning_title_skips_retry():
    titles = ["章节一", "章节二", "章节三", "章节四"]
    sections = [{"title": t, "key_points": ["x"]} for t in titles]
    llm = FakeLLM(
        [
            "## 章节一\n\n甲",
            "本节围绕章节二展开的正文，未以标题行开头",  # 提及标题 → 不触发重试
            "## 章节三\n\n丙",
            "## 章节四\n\n丁",
        ]
    )
    markdown = asyncio.run(generate_content(_intent(sections), ReportRecipe(), llm))
    # 归一化时补上标题行即可，无需重试
    assert llm.calls == 4
    assert "## 章节二" in markdown


def test_empty_section_falls_back_to_key_points():
    titles = ["章节一", "章节二", "章节三", "章节四"]
    sections = [
        {"title": t, "key_points": [f"{t}要点A", f"{t}要点B"]} for t in titles
    ]
    llm = FakeLLM(
        [
            "## 章节一\n\n甲",
            "",  # 章节二生成失败，重试也为空 → 要点兜底
            "## 章节三\n\n丙",
            "## 章节四\n\n丁",
            "",  # 章节二的 strict 重试
        ]
    )
    intent = _intent(sections)
    markdown = asyncio.run(generate_content(intent, ReportRecipe(), llm))
    assert "## 章节二" in markdown
    assert "章节二要点A" in markdown
    qa = intent.meta["content_qa"]
    assert qa["unresolved_sections"] == ["章节二"]


def test_resume_recipe_stays_single_shot():
    sections = [{"title": f"区块{i}", "key_points": ["x"]} for i in range(5)]
    llm = FakeLLM(["# 张三\n\n<div class=\"resume-header\">简历</div>"])
    markdown = asyncio.run(generate_content(_intent(sections), ResumeRecipe(), llm))
    assert llm.calls == 1
    assert "resume-header" in markdown


def test_empty_generation_falls_back():
    sections = [{"title": "章节", "key_points": ["x"]}]
    llm = FakeLLM([""])
    markdown = asyncio.run(generate_content(_intent(sections), ReportRecipe(), llm))
    assert markdown.startswith("#")


# --- 旅行配方预算页 QA（页序固定 + max_tokens 截断兜底） -------------------


def _travel_intent() -> PDFIntent:
    return PDFIntent(
        title="新疆12天游",
        topic="新疆12天游",
        style="travel_aurora",
        color_scheme=None,
        sections=[],
        meta={"theme": "travel_aurora", "destination": "新疆", "days": "12天"},
    )


def _travel_pages() -> str:
    overview = '<div class="page"><h2 class="page-title">路线总览</h2></div>'
    days = "".join(
        f'<div class="page"><h2 class="day-title">D{i}</h2><p>行程</p></div>'
        for i in range(1, 13)
    )
    return overview + days


def test_budget_page_present_skips_patch():
    from app.docgen.pdf.content import ensure_travel_budget_page
    from app.docgen.pdf.recipes import TravelRecipe

    markdown = _travel_pages() + (
        '<div class="page"><div class="budget-big">'
        '<span class="bb-num">2.0万</span></div>'
        '<div class="budget-bars">预算</div></div>'
    )
    llm = FakeLLM([])
    result = asyncio.run(
        ensure_travel_budget_page(markdown, _travel_intent(), TravelRecipe(), llm)
    )
    assert llm.calls == 0
    assert result == markdown


def test_budget_page_missing_gets_patched():
    from app.docgen.pdf.content import ensure_travel_budget_page
    from app.docgen.pdf.recipes import TravelRecipe

    patch = (
        '<div class="page"><div class="budget-big">'
        '<span class="bb-num">2.0万</span></div>'
        '<div class="budget-bars">人均预算</div></div>'
    )
    llm = FakeLLM([patch])
    markdown = _travel_pages()
    result = asyncio.run(
        ensure_travel_budget_page(markdown, _travel_intent(), TravelRecipe(), llm)
    )
    assert llm.calls == 1
    assert 'class="budget-big"' in result
    assert result.count('<div class="page"') == 14
    # 追加页在末尾且结构完整
    assert result.rstrip().endswith("</div>")


def test_budget_patch_rejected_when_invalid():
    from app.docgen.pdf.content import ensure_travel_budget_page
    from app.docgen.pdf.recipes import TravelRecipe

    # 补页输出不含预算标记：放弃拼接，原文保留
    llm = FakeLLM(['<div class="page"><p>随便什么</p></div>'])
    markdown = _travel_pages()
    result = asyncio.run(
        ensure_travel_budget_page(markdown, _travel_intent(), TravelRecipe(), llm)
    )
    assert llm.calls == 1
    assert result == markdown


def test_budget_patch_after_truncated_tail_repairs():
    from app.docgen.pdf.content import ensure_travel_budget_page
    from app.docgen.pdf.recipes import TravelRecipe

    patch = (
        '<div class="page"><div class="budget-big">'
        '<span class="bb-num">2.0万</span>'
        '<span class="bb-cap">人均预算（经济型）</span></div></div>'
    )
    llm = FakeLLM([patch])
    truncated = _travel_pages() + '<div class="page"><h2 class="day-title">D13<'  # 截断残页
    result = asyncio.run(
        ensure_travel_budget_page(truncated, _travel_intent(), TravelRecipe(), llm)
    )
    assert llm.calls == 1
    # 残页被丢弃、预算页为顶层 page：div 数量守恒
    assert result.count("<div") == result.count("</div>")
    assert "D13" not in result
    assert 'class="budget-big"' in result


def test_budget_patch_failure_keeps_original():
    from app.docgen.pdf.content import ensure_travel_budget_page
    from app.docgen.pdf.recipes import TravelRecipe

    class BoomLLM:
        async def stream(self, messages):
            raise RuntimeError("llm down")
            yield  # pragma: no cover

    markdown = _travel_pages()
    result = asyncio.run(
        ensure_travel_budget_page(markdown, _travel_intent(), TravelRecipe(), BoomLLM())
    )
    assert result == markdown
