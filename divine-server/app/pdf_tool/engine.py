from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import settings_store
from ..llm import DeepSeekLLM, MockLLM
from ..pdf_renderer import render_markdown_to_pdf
from .content import generate_content
from .intent import parse_intent
from .recipes import detect_recipe, get_recipe


def _suggest_resume_theme(prompt: str, resume_data: dict[str, Any]) -> str:
    text = prompt.lower()
    if any(
        word in text
        for word in ("kami", "resume-optimizer", "resume optimizer", "排版优化")
    ):
        return "kami"
    if any(
        word in text
        for word in ("linkedin", "领英", "海外投递", "国际投递")
    ):
        return "linkedin"
    if any(
        word in text
        for word in ("金融", "银行", "投行", "证券", "基金", "财务", "审计", "信托")
    ):
        return "finance"
    if any(
        word in text
        for word in ("boss", "直聘", "招聘平台", "ats", "海投")
    ):
        return "boss_zhipin"
    if any(
        word in text
        for word in (
            "大厂",
            "外企",
            "传统行业",
            "国企",
            "央企",
        )
    ):
        return "professional"
    if any(
        word in text
        for word in ("互联网", "创业", "设计", "新媒体", "游戏", "内推", "熟人")
    ):
        return "creative"
    if any(
        word in text
        for word in ("学术", "咨询", "金融", "法律", "科研", "高校", "律师")
    ):
        return "minimal"
    return "professional"


def build_llm() -> Any:
    settings = settings_store.load()
    provider = settings.get("provider") or "auto"
    api_key = settings.get("api_key") or ""
    if provider == "mock" or (provider == "auto" and not api_key):
        return MockLLM()
    return DeepSeekLLM()


class PDFTool:
    """Unified entry for all PDF generation requirements."""

    async def run(
        self,
        prompt: str,
        output: Path,
        kind: str | None = None,
        style: str | None = None,
        theme: str | None = None,
        color_scheme: str | None = None,
        paper_size: str = "A4",
        cover: bool = False,
        toc: bool = False,
        base_dir: Path | None = None,
        llm: Any | None = None,
        content: str | None = None,
        resume_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        recipe_name = kind or detect_recipe(prompt)
        recipe = get_recipe(recipe_name)
        llm = llm or build_llm()

        if recipe_name == "resume" and resume_data:
            from ..resume_themes.renderer import render_resume

            resume_theme = "professional"
            if theme in (
                "professional",
                "creative",
                "minimal",
                "boss_zhipin",
                "finance",
                "linkedin",
                "kami",
            ):
                resume_theme = theme
            elif not theme or theme in ("resume", "universal", "auto"):
                resume_theme = _suggest_resume_theme(prompt, resume_data)
            render_resume(resume_data, str(output), theme=resume_theme)
            return {
                "recipe": recipe.name,
                "display_name": recipe.display_name,
                "theme": resume_theme,
                "title": str(resume_data.get("name") or prompt[:40]),
                "renderer": "weasyprint",
            }

        if content:
            intent = recipe.fallback_intent(prompt)
            markdown = content
        else:
            intent = await parse_intent(prompt, recipe, llm)
            markdown = await generate_content(intent, recipe, llm)

        final_style = style or recipe.css_template
        final_theme = theme or recipe.css_template
        final_color = color_scheme or recipe.color_scheme
        meta = render_markdown_to_pdf(
            markdown,
            output,
            title=intent.title,
            style=final_style,
            color_scheme=final_color,
            paper_size=paper_size,
            cover=cover,
            toc=toc,
            base_dir=base_dir,
            theme=final_theme,
        )
        return {
            "recipe": recipe.name,
            "display_name": recipe.display_name,
            "theme": final_theme,
            "intent": {
                "title": intent.title,
                "topic": intent.topic,
                "sections": intent.sections,
                "meta": intent.meta,
            },
            "markdown": markdown,
            **meta,
        }
