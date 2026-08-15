from __future__ import annotations

import json
import re
from typing import Any, AsyncIterator

from .base import PDFIntent, PDFRecipe


async def _llm_text(
    llm: Any,
    messages: list[dict[str, str]],
) -> str:
    chunks: list[str] = []
    stream: AsyncIterator[dict[str, Any]] = llm.stream(messages)
    async for event in stream:
        if event.get("type") == "message":
            chunks.append(str(event.get("content") or ""))
    return "".join(chunks).strip()


def _extract_json(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


async def parse_intent(
    user_input: str,
    recipe: PDFRecipe,
    llm: Any,
) -> PDFIntent:
    prompt = recipe.build_intent_prompt(user_input)
    raw = ""
    try:
        raw = await _llm_text(
            llm,
            [
                {
                    "role": "system",
                    "content": "只输出 JSON，不要输出解释或 Markdown 围栏。",
                },
                {"role": "user", "content": prompt},
            ],
        )
    except Exception:
        raw = ""
    data = _extract_json(raw)
    if not data:
        return recipe.fallback_intent(user_input)
    sections = data.get("sections")
    if not isinstance(sections, list) or not sections:
        sections = [
            {
                "title": "正文",
                "key_points": [data.get("topic") or user_input],
            }
        ]
    route_value = data.get("route")
    if isinstance(route_value, str):
        route_value = [
            part.strip()
            for part in re.split(r"→|->|,|、", route_value)
            if part.strip()
        ]
    return PDFIntent(
        title=str(data.get("title") or user_input[:40] or "文档"),
        topic=str(data.get("topic") or user_input),
        style=str(data.get("style") or recipe.css_template),
        color_scheme=str(
            data.get("color_scheme") or recipe.color_scheme
        ),
        sections=sections,
        meta={
            "recipe": recipe.name,
            "destination": data.get("destination"),
            "days": data.get("days"),
            "duration": data.get("duration"),
            "travelers": data.get("travelers"),
            "countries": data.get("countries"),
            "route": route_value,
            "dates": data.get("dates"),
            "summary": data.get("summary"),
            "style": data.get("style"),
        },
    )
