from __future__ import annotations

import asyncio
import json
import os
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

# 章节数超过该阈值时改用大纲→分章两段式生成（≤3 单次直出，控制成本与延迟）
_SECTIONED_THRESHOLD = 3
# 分章生成并发数：默认串行；可用环境变量 PDF_CONTENT_CONCURRENCY 调整
_CONCURRENCY = max(1, int(os.environ.get("PDF_CONTENT_CONCURRENCY") or "1"))
# 生成后自检的占位词：出现即视为该节未完成
_PLACEHOLDER_TOKENS = ("待补充", "量化数据待补")

# 配图提示：仅在用户要求配图（images=true）的 markdown 类配方中追加到 system prompt
_ILLUSTRATION_HINT = (
    "\n\n【配图（可选）】用户要求文档配图：可在 1-3 个合适的位置插入图片语法 "
    "![图片说明](keyword:与段落内容强相关的2-4字关键词)；"
    "如掌握确定可访问的真实图片 URL 也可直接使用该 URL。"
    "不要编造没有把握的 URL；系统会下载内嵌图片，失败自动降级为占位块。"
)


def _system_prompt(intent: PDFIntent, recipe: PDFRecipe) -> str:
    prompt = recipe.content_system_prompt(intent)
    if (
        recipe.content_format == "markdown"
        and isinstance(intent.meta, dict)
        and intent.meta.get("images_requested")
    ):
        prompt += _ILLUSTRATION_HINT
    return prompt


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


# ---------------------------------------------------------------------------
# 大纲 → 分章两段式生成
# ---------------------------------------------------------------------------

def _usable_sections(intent: PDFIntent) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for section in intent.sections or []:
        if not isinstance(section, dict):
            continue
        title = str(section.get("title") or "").strip()
        points = [
            str(point).strip()
            for point in (section.get("key_points") or [])
            if str(point).strip()
        ]
        if title or points:
            result.append({"title": title, "key_points": points})
    return result


def _normalize_text(text: str) -> str:
    cleaned = re.sub(r"[\s：:，,。·\-—|]+", "", text or "")
    return cleaned


def _section_title_present(text: str, title: str) -> bool:
    """宽松判断章节文本是否包含其标题（标题行或正文均可）。"""
    if not title:
        return bool((text or "").strip())
    needle = _normalize_text(title)
    return bool(needle) and needle in _normalize_text(text)


def _has_placeholder(text: str) -> bool:
    return any(token in (text or "") for token in _PLACEHOLDER_TOKENS)


def _normalize_section_text(text: str, section: dict[str, Any]) -> str:
    """清理单章输出：去围栏、去误输出的文档大标题、补缺失的章节标题行。"""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    cleaned = re.sub(r"^```(?:markdown)?\s*\n", "", cleaned)
    cleaned = re.sub(r"\n```\s*$", "", cleaned)
    # 误输出的文档大标题（# ）整行去掉，避免拼装后重复
    cleaned = re.sub(r"^#\s+.+\n+", "", cleaned, count=1)
    if not re.match(r"^#{1,6}\s", cleaned):
        title = str(section.get("title") or "").strip()
        cleaned = f"## {title}\n\n{cleaned}" if title else cleaned
    return cleaned.strip()


def _fallback_section(section: dict[str, Any]) -> str:
    title = section.get("title") or "章节"
    lines = [f"## {title}", ""]
    for point in section.get("key_points") or []:
        lines.append(f"- {point}")
    return "\n".join(lines).strip()


async def _generate_section_text(
    intent: PDFIntent,
    recipe: PDFRecipe,
    llm: Any,
    outline: list[dict[str, Any]],
    index: int,
    strict: bool = False,
) -> str:
    section = outline[index]
    instruction = (
        f"只输出第 {section['index']} 节「{section['title']}」的 Markdown 正文："
        "以 `## 章节标题` 开头，围绕该节 key_points 展开；"
        "不要输出其他章节、不要输出文档大标题、不要输出解释或代码围栏。"
    )
    if strict:
        instruction += (
            f"标题必须原样使用「{section['title']}」；"
            "正文严禁出现“待补充/量化数据待补”等占位词，"
            "没有的数据用定性描述替代。"
        )
    payload = {
        "document_title": intent.title,
        "outline": outline,
        "write_section_index": section["index"],
        "instruction": instruction,
    }
    try:
        return await _llm_text(
            llm,
            [
                {
                    "role": "system",
                    "content": _system_prompt(intent, recipe),
                },
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            ],
        )
    except Exception:
        return ""


async def _generate_by_sections(
    intent: PDFIntent,
    recipe: PDFRecipe,
    llm: Any,
    sections: list[dict[str, Any]],
) -> tuple[str, list[str], list[str]]:
    """逐章生成 → 拼装 → 自检（缺失标题/占位词各重试一轮）。"""
    outline = [
        {
            "index": position + 1,
            "title": section["title"],
            "key_points": section["key_points"],
        }
        for position, section in enumerate(sections)
    ]
    texts: list[str | None] = [None] * len(sections)
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async def worker(position: int) -> None:
        async with semaphore:
            texts[position] = await _generate_section_text(
                intent, recipe, llm, outline, position
            )

    await asyncio.gather(*(worker(i) for i in range(len(sections))))

    assembled = [
        _normalize_section_text(texts[i] or "", sections[i])
        for i in range(len(sections))
    ]

    raw_texts = [texts[i] or "" for i in range(len(sections))]

    # 自检基于 LLM 原文（而非补标题后的归一化文本）：
    # 标题完全未出现 / 含占位词 / 空输出的章节，strict 模式重生成一轮
    regenerated: list[str] = []
    unresolved: list[str] = []
    for i, section in enumerate(sections):
        label = section["title"] or f"section-{i + 1}"
        if _section_title_present(
            raw_texts[i], section["title"]
        ) and not _has_placeholder(raw_texts[i]):
            continue
        retry = await _generate_section_text(
            intent, recipe, llm, outline, i, strict=True
        )
        retry_ok = _section_title_present(
            retry, section["title"]
        ) and not _has_placeholder(retry)
        if retry_ok:
            assembled[i] = _normalize_section_text(retry, section)
            regenerated.append(label)
        if not _section_title_present(assembled[i], section["title"]):
            # 仍缺标题：仅在原文为空时用要点兜底，保证文档结构完整
            if not assembled[i]:
                assembled[i] = _fallback_section(section)
            unresolved.append(label)

    markdown = "\n\n".join(part for part in assembled if part).strip()
    return markdown, regenerated, unresolved


async def _generate_single_shot(
    intent: PDFIntent,
    recipe: PDFRecipe,
    llm: Any,
) -> str:
    try:
        return await _llm_text(
            llm,
            [
                {
                    "role": "system",
                    "content": _system_prompt(intent, recipe),
                },
                {
                    "role": "user",
                    "content": recipe.content_user_prompt(intent),
                },
            ],
        )
    except Exception:
        return ""


async def generate_content(
    intent: PDFIntent,
    recipe: PDFRecipe,
    llm: Any,
) -> str:
    if recipe.content_format == "html":
        markdown = await _generate_single_shot(intent, recipe, llm)
        if not markdown:
            return recipe.fallback_content(intent)
        return _strip_non_icon_svg(markdown)

    sections = _usable_sections(intent)
    if recipe.sectioned_content and len(sections) > _SECTIONED_THRESHOLD:
        markdown, regenerated, unresolved = await _generate_by_sections(
            intent, recipe, llm, sections
        )
        mode = "sections"
    else:
        markdown = await _generate_single_shot(intent, recipe, llm)
        regenerated, unresolved = [], []
        mode = "single"

    markdown = _strip_non_icon_svg(markdown)
    if isinstance(intent.meta, dict):
        intent.meta["content_qa"] = {
            "mode": mode,
            "sections": len(sections),
            "regenerated": regenerated,
            "unresolved_sections": unresolved,
            "placeholders_left": sum(
                markdown.count(token) for token in _PLACEHOLDER_TOKENS
            ),
        }
    if not markdown or not re.search(r"^#{1,6}\s", markdown, re.MULTILINE):
        return recipe.fallback_content(intent)
    return markdown
