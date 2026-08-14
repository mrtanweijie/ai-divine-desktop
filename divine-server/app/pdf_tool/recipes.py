from __future__ import annotations

import html as html_lib

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


class ResumeRecipe(PDFRecipe):
    name = "resume"
    display_name = "个人简历"
    css_template = "resume"
    color_scheme = "blue"
    illustration_plan = {
        "mermaid": False,
        "svg": False,
        "icons_only": True,
        "chart": False,
        "ai_image": False,
    }
    intent_json_hint = (
        '{"title": "姓名 - 目标职位", "name": "姓名", "role": "目标职位", '
        '"contact": "邮箱 · 电话 · 城市", "summary": "一句话简介", '
        '"skills": ["技能一", "技能二"], '
        '"sections": [{"title": "工作经历", "key_points": ["公司 · 职位 · 时间", "成果一"]}]}'
    )

    def content_system_prompt(self, intent: PDFIntent) -> str:
        meta = intent.meta or {}
        return (
            "你是资深简历顾问。根据简历结构输出适合直接打印的单页 A4 简历 HTML。\n"
            "使用以下类：resume-header、resume-name、resume-role、resume-contact、"
            "resume-summary、resume-section、skill-tag、experience-item、"
            "project-card、resume-point。\n"
            "要求：信息密度高、无多余装饰；不要使用 SVG 插图。\n"
            "内容规范：把职责描述改成成果描述；每条经历保留 2-4 条高密度 bullet；\n"
            "bullet 使用“动作 + 产物 + 结果”结构，优先量化；没有精确数字时写范围、频率或流程变化；\n"
            "严禁编造指标、头衔或项目背景，缺失数据用“[量化数据待补]”占位；\n"
            "每个项目先写一句背景（系统定位 + 服务对象 + 解决什么问题），再列 bullet；\n"
            "Kami 风格时项目按 角色/动作/结果 三段式，impact 必须量化；\n"
            "核心技能按 分类|内容 的技能行组织，内容写 1-2 行并尽量占满整行；\n"
            "工作经历按 公司/部门/角色 + 项目子标题 + 2-4 条成果 bullet；\n"
            "页数按内容实际需要控制，不强制一页；用户要求一页版时再压缩。\n"
            f"姓名：{meta.get('name', intent.title)}，"
            f"目标职位：{meta.get('role', '')}"
        )

    def fallback_intent(self, user_input: str) -> PDFIntent:
        title = user_input.strip().splitlines()[0][:40] or "个人简历"
        return PDFIntent(
            title=title,
            topic=user_input,
            style=self.css_template,
            color_scheme=self.color_scheme,
            sections=[
                {"title": "个人简介", "key_points": [user_input]},
                {"title": "核心技能", "key_points": ["技能一", "技能二"]},
                {"title": "工作经历", "key_points": ["公司 · 职位 · 时间"]},
                {"title": "项目经历", "key_points": ["项目名称 · 成果"]},
                {"title": "教育背景", "key_points": ["学校 · 专业 · 时间"]},
            ],
            meta={
                "recipe": self.name,
                "name": user_input,
                "role": "",
                "contact": "",
                "summary": user_input,
                "skills": [],
            },
        )

    def fallback_content(self, intent: PDFIntent) -> str:
        meta = intent.meta or {}
        name = html_lib.escape(str(meta.get("name") or intent.title))
        role = html_lib.escape(str(meta.get("role") or ""))
        contact = html_lib.escape(str(meta.get("contact") or ""))
        summary = html_lib.escape(str(meta.get("summary") or intent.topic))
        skills = meta.get("skills") or []

        lines = [
            '<div class="resume-header">',
            f'<div class="resume-name">{name}</div>',
            f'<div class="resume-role">{role}</div>' if role else "",
            f'<div class="resume-contact">{contact}</div>' if contact else "",
            "</div>",
            f'<div class="resume-summary">{summary}</div>',
        ]
        if isinstance(skills, list) and skills:
            tags = "".join(
                f'<span class="skill-tag">{html_lib.escape(str(skill))}</span>'
                for skill in skills
            )
            lines.append(f'<div class="resume-section-title">核心技能</div>')
            lines.append(f'<div class="skill-tags">{tags}</div>')

        for section in intent.sections:
            title = str(section.get("title") or "经历")
            points = section.get("key_points") or []
            lines.append(f'<div class="resume-section-title">{html_lib.escape(title)}</div>')
            card_class = (
                "experience-item"
                if any(word in title for word in ("工作", "经历"))
                else "project-card"
                if "项目" in title
                else "resume-block"
            )
            lines.append(f'<div class="{card_class}">')
            for point in points:
                lines.append(
                    f'<div class="resume-point">{html_lib.escape(str(point))}</div>'
                )
            lines.append("</div>")
        return "\n".join(line for line in lines if line).strip()


RECIPE_REGISTRY: dict[str, type[PDFRecipe]] = {
    recipe.name: recipe
    for recipe in (
        ReportRecipe,
        TravelRecipe,
        RoadmapRecipe,
        BookRecipe,
        SlideRecipe,
        ResumeRecipe,
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
        for word in ("简历", "resume", "cv", "求职")
    ):
        return "resume"
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
