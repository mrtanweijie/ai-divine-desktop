"""商业分析报告配方（BusinessAnalysisRecipe）测试。"""

import asyncio
import json

from app.pdf_tool.content import generate_content
from app.pdf_tool.design_rules import resolve_design
from app.pdf_tool.intent import parse_intent
from app.pdf_tool.recipes import (
    BusinessAnalysisRecipe,
    detect_recipe,
    get_recipe,
)


class FakeLLM:
    """按调用次序返回预设响应的最小 LLM 桩。"""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls = 0

    async def stream(self, messages):
        index = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        yield {"type": "message", "content": self._responses[index]}


# ---------------------------------------------------------------------------
# 配方识别与注册
# ---------------------------------------------------------------------------

def test_detect_recipe_routes_business():
    for text in (
        "帮我写一份新茶饮品牌的商业分析报告",
        "做一个瑞幸的竞品对标分析 PDF",
        "分析一下这个品牌的私域联名增长策略",
        "写一份商业计划书风格的经营分析",
        "这个品牌有没有护城河，输出 PDF",
    ):
        assert detect_recipe(text) == "business", f"{text!r} 应命中 business"


def test_detect_recipe_keeps_other_recipes():
    assert detect_recipe("写一份本周工作周报") == "report"
    assert detect_recipe("生成一份新疆旅行攻略") == "travel"
    assert detect_recipe("帮我做一份求职简历") == "resume"
    assert detect_recipe("Python 学习路线") == "roadmap"
    assert detect_recipe("行业洞察深度长文") == "report"


def test_business_recipe_registered():
    recipe = get_recipe("business")
    assert isinstance(recipe, BusinessAnalysisRecipe)
    assert recipe.display_name == "商业分析报告"


# ---------------------------------------------------------------------------
# 内容生成 prompt：四大维度 + 推导逻辑 + 数据产物
# ---------------------------------------------------------------------------

def test_content_prompt_covers_four_dimensions_and_logic():
    recipe = BusinessAnalysisRecipe()
    from app.pdf_tool.base import PDFIntent

    intent = PDFIntent(
        title="测试报告",
        topic="品牌商业分析",
        style=recipe.css_template,
        color_scheme=recipe.color_scheme,
        sections=[],
        meta={
            "brand": "蜜雪冰城",
            "industry": "现制茶饮",
            "competitors": ["瑞幸", "古茗"],
        },
    )
    prompt = recipe.content_system_prompt(intent)
    # 四大维度
    for token in ("价值主张", "数字化成本结构", "私域联名增长策略", "品牌竞争壁垒"):
        assert token in prompt, token
    # 推导逻辑要求（不是信息堆砌）
    assert "推导链条" in prompt
    assert "信息堆砌" in prompt
    # 内容路径：痛点 → 降本 → 私域效果 → 护城河
    for token in ("用户痛点", "降本路径", "营销效果", "护城河"):
        assert token in prompt, token
    # 必出数据产物
    assert "行业对标表格" in prompt
    assert "品牌经营核心数据" in prompt
    # 分析对象注入
    assert "蜜雪冰城" in prompt
    assert "瑞幸" in prompt
    # 布局模块指南随 prompt 注入
    assert "hero-stat" in prompt


def test_content_prompt_without_subject_meta():
    recipe = BusinessAnalysisRecipe()
    from app.pdf_tool.base import PDFIntent

    intent = PDFIntent(
        title="测试报告",
        topic="某品牌商业分析",
        style=recipe.css_template,
        color_scheme=recipe.color_scheme,
        sections=[],
        meta={},
    )
    prompt = recipe.content_system_prompt(intent)
    assert "分析对象" not in prompt


def test_fallback_intent_covers_dimensions():
    recipe = BusinessAnalysisRecipe()
    intent = recipe.fallback_intent("新茶饮品牌商业分析报告")
    titles = [section["title"] for section in intent.sections]
    assert len(titles) >= 6
    joined = "".join(titles)
    for token in ("痛点", "价值主张", "成本结构", "私域联名", "壁垒"):
        assert token in joined, token
    # 行业对标与核心数据在框架中
    assert any("对标" in title or "经营" in title for title in titles)
    assert intent.meta["recipe"] == "business"


# ---------------------------------------------------------------------------
# 意图解析：brand / industry / competitors 透传
# ---------------------------------------------------------------------------

def test_parse_intent_passes_business_meta():
    recipe = BusinessAnalysisRecipe()
    raw = json.dumps(
        {
            "title": "蜜雪冰城商业分析报告",
            "topic": "现制茶饮赛道商业分析",
            "brand": "蜜雪冰城",
            "industry": "现制茶饮",
            "competitors": ["瑞幸", "古茗", "茶百道"],
            "sections": [
                {"title": "价值主张", "key_points": ["痛点推导"]},
            ],
        },
        ensure_ascii=False,
    )
    intent = asyncio.run(
        parse_intent("生成商业分析报告", recipe, FakeLLM([raw]))
    )
    assert intent.meta["brand"] == "蜜雪冰城"
    assert intent.meta["industry"] == "现制茶饮"
    assert intent.meta["competitors"] == ["瑞幸", "古茗", "茶百道"]


def test_parse_intent_competitors_string_split():
    recipe = BusinessAnalysisRecipe()
    raw = json.dumps(
        {
            "title": "品牌商业分析",
            "topic": "商业分析",
            "competitors": "瑞幸、古茗/茶百道",
        },
        ensure_ascii=False,
    )
    intent = asyncio.run(parse_intent("商业分析报告", recipe, FakeLLM([raw])))
    assert intent.meta["competitors"] == ["瑞幸", "古茗", "茶百道"]


def test_parse_intent_without_business_meta():
    recipe = BusinessAnalysisRecipe()
    raw = json.dumps(
        {"title": "普通报告", "topic": "主题", "sections": []},
        ensure_ascii=False,
    )
    intent = asyncio.run(parse_intent("生成报告", recipe, FakeLLM([raw])))
    assert "brand" not in intent.meta
    assert "competitors" not in intent.meta


# ---------------------------------------------------------------------------
# 分章生成走通（8 节 > 3 触发两段式）
# ---------------------------------------------------------------------------

def test_business_content_generated_by_sections():
    recipe = BusinessAnalysisRecipe()
    intent = recipe.fallback_intent("新茶饮品牌商业分析报告")
    responses = [
        f"## {section['title']}\n\n{section['title']}的推导与分析。"
        for section in intent.sections
    ]
    llm = FakeLLM(responses)
    markdown = asyncio.run(generate_content(intent, recipe, llm))
    assert llm.calls == len(intent.sections)
    assert intent.meta["content_qa"]["mode"] == "sections"
    assert intent.meta["content_qa"]["unresolved_sections"] == []
    for section in intent.sections:
        assert f"## {section['title']}" in markdown


# ---------------------------------------------------------------------------
# 设计决策：business 场景
# ---------------------------------------------------------------------------

def test_resolve_design_business_scene():
    decision = resolve_design(
        "帮我做一份品牌商业分析报告",
        recipe_name="business",
    )
    assert decision.scene == "business"
    assert decision.scene_label == "商业分析"
    assert decision.theme == "universal"
    assert decision.color_scheme == "blue"
    assert decision.cover is True
    assert decision.toc is True


def test_resolve_design_quarterly_beats_business():
    """给老板的季度经营分析汇报：季度汇报场景优先。"""
    decision = resolve_design(
        "给老板的季度经营分析汇报",
        recipe_name="report",
    )
    assert decision.scene == "quarterly"


def test_resolve_design_no_business_false_positive():
    decision = resolve_design("今天天气不错", recipe_name="report")
    assert decision.scene != "business"
