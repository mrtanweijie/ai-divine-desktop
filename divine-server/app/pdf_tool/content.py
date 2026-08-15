from __future__ import annotations

import re
from typing import Any

from .base import PDFIntent, PDFRecipe
from .intent import _llm_text


_SVG_FENCE_RE = re.compile(
    r"```(?:svg|xml)\s*\n(.*?)```", re.IGNORECASE | re.DOTALL
)
_RAW_SVG_RE = re.compile(
    r"(?is)(<svg[^>]*>.*?</svg>)"
)


def _is_simple_icon(svg_text: str) -> bool:
    lowered = svg_text.lower()
    if any(
        token in lowered
        for token in ("<text", "<defs", "gradient", "<pattern", "<image")
    ):
        return False
    width = re.search(r"\bwidth\s*=\s*[\"'](\d+)", svg_text, re.IGNORECASE)
    height = re.search(r"\bheight\s*=\s*[\"'](\d+)", svg_text, re.IGNORECASE)
    if width and int(width.group(1)) > 96:
        return False
    if height and int(height.group(1)) > 96:
        return False
    view_box = re.search(
        r"viewBox\s*=\s*[\"']([-\d.\s]+)[\"']", svg_text, re.IGNORECASE
    )
    if view_box:
        numbers = list(
            map(float, re.findall(r"[-+]?\d*\.?\d+", view_box.group(1)))
        )
        if len(numbers) == 4 and (
            numbers[2] - numbers[0] > 160
            or numbers[3] - numbers[1] > 160
        ):
            return False
    return len(re.findall(r"<[a-zA-Z]", svg_text)) <= 12


def _strip_non_icon_svg(markdown: str) -> str:
    def replace_fenced(match: re.Match[str]) -> str:
        svg = re.search(
            r"(<svg[^>]*>.*?</svg>)",
            match.group(1),
            re.IGNORECASE | re.DOTALL,
        )
        if svg and _is_simple_icon(svg.group(1)):
            return match.group(0)
        return ""

    cleaned = _SVG_FENCE_RE.sub(replace_fenced, markdown)
    cleaned = _RAW_SVG_RE.sub(
        lambda match: (
            match.group(1) if _is_simple_icon(match.group(1)) else ""
        ),
        cleaned,
    )
    return cleaned


async def generate_content(
    intent: PDFIntent,
    recipe: PDFRecipe,
    llm: Any,
) -> str:
    markdown = ""
    try:
        markdown = await _llm_text(
            llm,
            [
                {
                    "role": "system",
                    "content": recipe.content_system_prompt(intent),
                },
                {
                    "role": "user",
                    "content": recipe.content_user_prompt(intent),
                },
            ],
        )
    except Exception:
        markdown = ""
    if recipe.content_format == "html":
        if not markdown:
            return recipe.fallback_content(intent)
        return _strip_non_icon_svg(markdown)
    if not markdown or not re.search(r"^#{1,6}\s", markdown, re.MULTILINE):
        return recipe.fallback_content(intent)
    return _strip_non_icon_svg(markdown)
