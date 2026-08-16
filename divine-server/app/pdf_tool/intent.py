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


def _clean_title(raw: str) -> str:
    """把 LLM 返回的标题压缩成简洁文件名友好的标题。

    若标题是完整需求句（含“为…生成/请…/帮我…”等 prompt 特征，或带句号/超长），
    去掉语气词、取“手册/攻略/指南/路线/行程”前的核心片段。
    """
    title = raw.strip()
    if not title:
        return ""
    # 去掉 prompt 式前缀：“为游客生成一份 …” / “请帮我生成一份 …” / “制作一份 …” 等
    # 只匹配「祈使动词 + 一份/一个」结构，避免吞掉书名号内容
    title = re.sub(
        r"^(?:请|麻烦|帮我|给我|为|为游客|帮|请帮)(?:我|你)?(?:生成|制作|写|做|输出|设计|规划|出一份|安排)?(?:一份|一个)?",
        "",
        title,
    )
    title = re.sub(r"^(?:游客|大家)?(?:生成|制作|做|写|输出|设计|出一份)(?:一份|一个)?", "", title)
    title = re.sub(r"^一份?", "", title)
    title = re.sub(r"^[。，、：:；;\s]+", "", title)
    # 若仍是长句（含句号/逗号或超 30 字），取第一个标点前
    if len(title) > 30 or re.search(r"[。！？!?]", title):
        cut = re.split(r"[。！？!?，,]", title)[0]
        title = cut.strip()
    title = re.sub(r"[\s]+", "", title)
    return title[:30]


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
    tags_value = data.get("tags")
    if isinstance(tags_value, str):
        tags_value = [
            part.strip()
            for part in re.split(r"[,、×xX/]", tags_value)
            if part.strip()
        ]
    raw_title = str(data.get("title") or "").strip()
    if not raw_title:
        raw_title = user_input[:40]
    title = _clean_title(raw_title)
    return PDFIntent(
        title=title or "旅行攻略",
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
            "tags": tags_value,
            "route": route_value,
            "dates": data.get("dates"),
            "summary": data.get("summary"),
            "style": data.get("style"),
            "watermark": data.get("watermark"),
        },
    )
