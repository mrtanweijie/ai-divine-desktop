from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PDFIntent:
    title: str
    topic: str
    style: str
    color_scheme: str
    sections: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


class PDFRecipe:
    name: str = "simple"
    display_name: str = "文档"
    content_format: str = "markdown"
    css_template: str = "universal"
    color_scheme: str = "blue"
    illustration_plan: dict[str, bool] = {
        "mermaid": False,
        "svg": False,
        "icons_only": True,
        "chart": False,
        "ai_image": False,
    }
    intent_json_hint: str = (
        '{"title": "标题", "topic": "主题", '
        '"sections": [{"title": "章节标题", "key_points": ["要点"]}]}'
    )

    def build_intent_prompt(self, user_input: str) -> str:
        return (
            f"你是{self.display_name}规划器。根据用户需求输出 JSON，不要输出 JSON 以外的内容。\n"
            f"输出结构：{self.intent_json_hint}\n"
            f"用户输入：{user_input}"
        )

    def content_system_prompt(self, intent: PDFIntent) -> str:
        return (
            f"你是资深{self.display_name}作者。根据文档结构撰写完整 Markdown 正文。\n"
            "要求：每个章节用 ## 标题；内容详实；"
            "不要自动生成 SVG 插图；仅当确实需要简单图标时才使用小型 SVG 图标。"
            f"主题：{intent.topic}"
        )

    def content_user_prompt(self, intent: PDFIntent) -> str:
        import json

        return json.dumps(
            {
                "title": intent.title,
                "sections": intent.sections,
                "meta": intent.meta,
            },
            ensure_ascii=False,
            indent=2,
        )

    def fallback_intent(self, user_input: str) -> PDFIntent:
        title = user_input.strip().splitlines()[0][:40] or "文档"
        return PDFIntent(
            title=title,
            topic=user_input,
            style=self.css_template,
            color_scheme=self.color_scheme,
            sections=[
                {
                    "title": f"第 {index} 部分",
                    "key_points": [
                        f"围绕“{title}”展开第 {index} 部分的内容"
                    ],
                }
                for index in range(1, 4)
            ],
            meta={"recipe": self.name},
        )

    def fallback_content(self, intent: PDFIntent) -> str:
        lines = [f"# {intent.title}", "", f"{intent.topic}", ""]
        for section in intent.sections:
            lines.append(f"## {section.get('title') or '章节'}")
            lines.append("")
            for point in section.get("key_points") or []:
                lines.append(f"- {point}")
            lines.append("")
        return "\n".join(lines).strip()
