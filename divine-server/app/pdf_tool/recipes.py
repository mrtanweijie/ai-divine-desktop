from __future__ import annotations

from .base import PDFIntent, PDFRecipe


class ReportRecipe(PDFRecipe):
    name = "report"
    display_name = "报告"
    css_template = "universal"
    color_scheme = "blue"
    intent_json_hint = (
        '{"title": "报告标题", "topic": "报告主题", '
        '"sections": [{"title": "章节", "key_points": ["要点"]}]}'
    )

    def content_system_prompt(self, intent: PDFIntent) -> str:
        return (
            "你是技术分析师和商务报告作者。根据文档结构生成专业报告 Markdown。\n"
            "要求：包含摘要、背景、分析、结论；关键数据用表格或要点；"
            "不要自动生成复杂 SVG 插图，仅允许简单图标。\n"
            f"报告主题：{intent.topic}"
        )


class TravelRecipe(PDFRecipe):
    name = "travel"
    display_name = "旅游攻略"
    css_template = "playful"
    color_scheme = "green"
    illustration_plan = {
        "mermaid": False,
        "svg": False,
        "icons_only": True,
        "chart": False,
        "ai_image": False,
    }
    intent_json_hint = (
        '{"title": "攻略标题", "destination": "目的地", "days": 3, '
        '"style": "休闲|打卡|深度|亲子", '
        '"sections": [{"title": "Day 1", "key_points": ["行程", "美食", "交通"]}]}'
    )

    def content_system_prompt(self, intent: PDFIntent) -> str:
        meta = intent.meta or {}
        return (
            "你是资深旅行博主。根据行程结构撰写实用、生动的旅游攻略 Markdown。\n"
            "要求：每天一节；包含交通、预算、贴士；不要自动生成复杂 SVG 插图，仅允许简单图标。\n"
            f"目的地：{meta.get('destination', intent.topic)}，"
            f"天数：{meta.get('days', '未指定')}，风格：{meta.get('style', '休闲')}"
        )

    def fallback_intent(self, user_input: str) -> PDFIntent:
        title = user_input.strip().splitlines()[0][:40] or "旅游攻略"
        return PDFIntent(
            title=title,
            topic=user_input,
            style=self.css_template,
            color_scheme=self.color_scheme,
            sections=[
                {
                    "title": f"Day {index}",
                    "key_points": ["行程安排", "美食推荐", "交通与住宿"],
                }
                for index in range(1, 4)
            ],
            meta={
                "recipe": self.name,
                "destination": user_input,
                "days": 3,
                "style": "休闲",
            },
        )


class RoadmapRecipe(PDFRecipe):
    name = "roadmap"
    display_name = "学习路线"
    css_template = "modern"
    color_scheme = "blue"
    illustration_plan = {
        "mermaid": False,
        "svg": False,
        "icons_only": True,
        "chart": False,
        "ai_image": False,
    }
    intent_json_hint = (
        '{"title": "路线标题", "topic": "学习主题", '
        '"sections": [{"title": "阶段名", "key_points": ["知识点", "资源", "练习"]}]}'
    )

    def content_system_prompt(self, intent: PDFIntent) -> str:
        return (
            "你是技术教育专家。根据学习路线结构生成系统化 Markdown 学习指南。\n"
            "要求：每个阶段一节；节点用卡片格式；资源用列表；"
            "不要自动生成复杂 SVG 插图，仅允许简单图标。\n"
            f"学习主题：{intent.topic}"
        )


class BookRecipe(PDFRecipe):
    name = "book"
    display_name = "电子书/手册"
    css_template = "academic"
    color_scheme = "warm"
    intent_json_hint = (
        '{"title": "书名", "topic": "手册主题", '
        '"sections": [{"title": "章标题", "key_points": ["小节", "要点"]}]}'
    )

    def content_system_prompt(self, intent: PDFIntent) -> str:
        return (
            "你是书籍/手册作者。根据章节结构撰写可读性强、结构完整的 Markdown 内容。\n"
            "要求：每章一节；包含引言、正文、小结；不要自动生成复杂 SVG 插图，仅允许简单图标。\n"
            f"主题：{intent.topic}"
        )


class SlideRecipe(PDFRecipe):
    name = "slide"
    display_name = "讲义"
    css_template = "minimal"
    color_scheme = "monochrome"
    illustration_plan = {
        "mermaid": False,
        "svg": False,
        "icons_only": True,
        "chart": True,
        "ai_image": False,
    }
    intent_json_hint = (
        '{"title": "讲义标题", "topic": "课程主题", '
        '"sections": [{"title": "小节", "key_points": ["要点", "示例"]}]}'
    )

    def content_system_prompt(self, intent: PDFIntent) -> str:
        return (
            "你是课程讲师。根据提纲生成适合打印的讲义 Markdown。\n"
            "要求：每个小节一节；每节先给结论再展开；控制信息密度；"
            "不要自动生成复杂 SVG 插图，仅允许简单图标。\n"
            f"课程主题：{intent.topic}"
        )


RECIPE_REGISTRY: dict[str, type[PDFRecipe]] = {
    recipe.name: recipe
    for recipe in (
        ReportRecipe,
        TravelRecipe,
        RoadmapRecipe,
        BookRecipe,
        SlideRecipe,
    )
}


def get_recipe(name: str | None) -> PDFRecipe:
    key = (name or "").strip().lower()
    cls = RECIPE_REGISTRY.get(key) or ReportRecipe
    return cls()


def detect_recipe(user_input: str) -> str:
    text = user_input.lower()
    if any(
        word in text
        for word in ("旅游", "攻略", "行程", "旅行", "景点", "目的地")
    ):
        return "travel"
    if any(
        word in text
        for word in ("学习路线", "路线图", "学习路径", "从入门到", "roadmap")
    ):
        return "roadmap"
    if any(
        word in text
        for word in ("报告", "周报", "月报", "分析", "调研", "总结")
    ):
        return "report"
    if any(
        word in text
        for word in ("电子书", "手册", "书籍", "书", "指南", "book")
    ):
        return "book"
    if any(
        word in text
        for word in ("讲义", "提纲", "幻灯片", "演示", "课程", "讲座")
    ):
        return "slide"
    return "report"
