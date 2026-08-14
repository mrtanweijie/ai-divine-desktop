from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import settings_store
from ..llm import DeepSeekLLM, MockLLM
from ..pdf_renderer import render_markdown_to_pdf
from .content import generate_content
from .intent import parse_intent
from .recipes import detect_recipe, get_recipe


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
    ) -> dict[str, Any]:
        recipe_name = kind or detect_recipe(prompt)
        recipe = get_recipe(recipe_name)
        llm = llm or build_llm()

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
