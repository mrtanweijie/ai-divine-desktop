from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..config import settings_store
from ..llm import DeepSeekLLM, MockLLM
from ..pdf_renderer import render_html_to_pdf, render_markdown_to_pdf
from .base import PDFIntent
from .content import generate_content
from .intent import parse_intent
from .recipes import detect_recipe, get_recipe
from .travel_html import looks_like_travel_html, travel_prompt_to_html


def _title_from_markdown(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return re.sub(r"^#+\s*", "", stripped).strip()
    return ""


def _summary_from_markdown(content: str) -> str:
    seen_title = False
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            seen_title = True
            continue
        if (
            seen_title
            and len(stripped) > 12
            and not stripped.startswith(("|", "-", "*", ">"))
        ):
            return re.sub(r"[*_`]", "", stripped)[:150]
    return ""


def _route_from_markdown(content: str) -> list[str]:
    for line in content.splitlines():
        if "→" in line or "->" in line:
            clean = re.sub(r"\*\*", "", line)
            clean = re.split(r"[：:]\s*", clean)[-1]
            return [
                part.strip().rstrip("，。、")
                for part in re.split(r"→|->|,|、|·|/", clean)
                if part.strip()
            ]
    return []


def _looks_like_generic_travel_fallback(content: str) -> bool:
    return any(
        token in content
        for token in (
            "围绕用户需求生成的一份完整旅行攻略",
            "待补充",
            "D1｜第 1 天",
        )
    )


def _suggest_resume_theme(prompt: str, resume_data: dict[str, Any]) -> str:
    text = prompt.lower()
    if any(
        word in text
        for word in ("kami_white", "kami 白色", "纯白投递", "白色版")
    ):
        return "kami_white"
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
        images: bool = False,
        base_dir: Path | None = None,
        llm: Any | None = None,
        content: str | None = None,
        resume_data: dict[str, Any] | None = None,
        color_overrides: dict[str, str] | None = None,
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
                "kami_white",
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

        use_content = bool(content)
        if use_content:
            intent = recipe.fallback_intent(prompt)
            markdown = content
            content_title = _title_from_markdown(markdown)
            if content_title:
                intent.title = content_title
            summary = _summary_from_markdown(markdown)
            if summary:
                intent.meta["summary"] = summary
            route = _route_from_markdown(markdown)
            if route:
                intent.meta["route"] = route
                intent.meta["destination"] = route[0]
            if recipe_name == "travel":
                source = markdown
                meta = dict(intent.meta)
                if theme in ("travel", "travel_mag"):
                    meta["theme"] = theme
                intent = PDFIntent(
                    title=intent.title,
                    topic=source,
                    style=recipe.css_template,
                    color_scheme=recipe.color_scheme,
                    sections=[
                        {
                            "title": "现有内容",
                            "key_points": [source],
                        }
                    ],
                    meta=meta,
                )
                markdown = await generate_content(intent, recipe, llm)
        else:
            intent = await parse_intent(prompt, recipe, llm)
            if recipe_name == "travel" and theme in ("travel", "travel_mag"):
                intent.meta["theme"] = theme
            markdown = await generate_content(intent, recipe, llm)

        if recipe_name == "travel" and (
            not looks_like_travel_html(markdown)
            or _looks_like_generic_travel_fallback(markdown)
        ):
            markdown = travel_prompt_to_html(prompt) or markdown

        final_style = style or recipe.css_template
        final_theme = theme or recipe.css_template
        final_color = color_scheme or recipe.color_scheme
        if recipe_name == "travel" or final_theme in ("travel", "travel_mag"):
            cover = True
            toc = False
        if recipe_name == "travel" and final_theme in ("travel", "travel_mag"):
            from ..pdf_theme_manager import travel_color_overrides

            overrides = travel_color_overrides(
                final_color, color_overrides, theme=final_theme
            )
            meta = render_html_to_pdf(
                markdown,
                output,
                title=intent.title,
                paper_size=paper_size,
                cover=True,
                cover_data=intent.meta,
                base_dir=base_dir,
                theme=final_theme,
                overrides=overrides,
                images=images,
            )
        else:
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
                cover_data=intent.meta,
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
