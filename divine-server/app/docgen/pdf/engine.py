from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any

from ...config import settings_store
from ...llm import DeepSeekLLM, MockLLM
from .renderer import render_html_to_pdf, render_markdown_to_pdf
from .renderer.qa import inspect_pdf, render_with_qa
from .theme_manager import (
    derive_universal_palette,
    travel_color_overrides,
    universal_color_overrides,
)
from .base import PDFIntent
from .content import generate_content
from .design_enforcer import enforce_design
from .design_rules import resolve_design
from .illustration import inline_markdown_images
from .intent import _clean_title, parse_intent
from .recipes import detect_recipe, get_recipe
from .travel_html import looks_like_travel_html, travel_prompt_to_html


def _title_from_markdown(content: str) -> str:
    """提取一级标题（# 标题）；## 章节名不会被误认为文档标题。"""
    for line in content.splitlines():
        stripped = line.strip()
        if re.match(r"^#\s", stripped):
            return re.sub(r"^#+\s*", "", stripped).strip()
    return ""


_COVER_META_RE = re.compile(
    r"<!--\s*cover-meta:\s*(\{.*?\})\s*-->", re.DOTALL | re.IGNORECASE
)


def _extract_cover_meta(markdown: str) -> dict[str, Any] | None:
    """从正文解析 Agent 输出的封面元数据注释（<!-- cover-meta: {...} -->）。"""
    match = _COVER_META_RE.search(markdown or "")
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except (json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _this_week_range() -> str:
    """本周日期范围（周一 – 周日），供周报类封面默认周期。"""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return f"{monday.strftime('%m.%d')} – {sunday.strftime('%m.%d')}"


def _hero_stat_from_markdown(markdown: str) -> dict[str, Any] | None:
    """提取正文中第一个 hero-stat 表格，供 split 封面右侧面板使用。"""
    match = re.search(
        r"(?m)((?:\|[^\n]*\|\s*\n){1,})\s*\{\:\s*\.hero-stat\s*\}", markdown
    )
    if not match:
        return None
    from .renderer.markdown import _parse_table_rows

    rows = _parse_table_rows(match.group(1))
    if not rows:
        return None
    stats = [
        {
            "label": str(row[0]).strip(),
            "value": str(row[1]).strip() if len(row) > 1 else "",
        }
        for row in rows[:4]
    ]
    first = stats[0]
    return {
        "value": first.get("value") or first.get("label", ""),
        "label": first.get("label", ""),
        "stats": stats[1:],
    }


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
            and not stripped.startswith(("|", "-", "*", ">", "{:"))
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
    """统一 20 套模板（12 母版 + 8 经典主题）按行业/场景关键词推荐。"""
    text = prompt.lower()
    from ..resume.templates.registry import TEMPLATE_REGISTRY

    for entry in TEMPLATE_REGISTRY.values():
        if any(word in text for word in entry["industry_keywords"]):
            return entry["id"]
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
        cover: bool | None = None,
        toc: bool | None = None,
        images: bool = False,
        base_dir: Path | None = None,
        llm: Any | None = None,
        content: str | None = None,
        resume_data: dict[str, Any] | None = None,
        color_overrides: dict[str, str] | None = None,
        cover_style: str | None = None,
        resume_layout: str | None = None,
    ) -> dict[str, Any]:
        recipe_name = kind or detect_recipe(prompt)
        recipe = get_recipe(recipe_name)
        llm = llm or build_llm()

        if recipe_name == "resume" and resume_data:
            # 职责单一：本工具只产出 PDF。简历的可编辑 HTML 走 html_resume 工具。
            # 统一模板库（templates/，19 套）单一渲染路径。
            if not theme or theme in ("resume", "universal", "auto"):
                resume_theme = _suggest_resume_theme(prompt, resume_data)
            else:
                resume_theme = theme

            from ..resume.templates import render_template_resume
            from ..resume.templates.registry import TEMPLATE_REGISTRY, get_entry

            if resume_theme not in TEMPLATE_REGISTRY:
                resume_theme = _suggest_resume_theme(prompt, resume_data)

            files = render_template_resume(
                resume_data,
                str(output),
                template_id=resume_theme,
                layout=(resume_layout or "single").strip() or "single",
                output_format="pdf",
                color_scheme=color_scheme,
                color_overrides=color_overrides,
            )
            return {
                "recipe": recipe.name,
                "display_name": get_entry(resume_theme)["display_name"],
                "theme": resume_theme,
                "title": str(resume_data.get("name") or prompt[:40]),
                "renderer": "weasyprint",
                "filepath": files[0] if files else str(output),
            }

        use_content = bool(content)
        if use_content:
            intent = recipe.fallback_intent(prompt)
            markdown = content
            content_title = _title_from_markdown(markdown)
            if content_title:
                intent.title = content_title
            else:
                # 无一级标题时用清洗后的用户需求作标题，避免封面显示章节名
                intent.title = _clean_title(prompt) or intent.title
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
                if theme.startswith("travel"):
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
            if recipe_name == "travel" and theme.startswith("travel"):
                intent.meta["theme"] = theme
            # markdown 类配方的配图开关：内容生成时注入配图提示
            intent.meta["images_requested"] = bool(images)
            markdown = await generate_content(intent, recipe, llm)

        if recipe_name == "travel" and (
            not looks_like_travel_html(markdown)
            or _looks_like_generic_travel_fallback(markdown)
        ):
            markdown = travel_prompt_to_html(prompt) or markdown

        # 设计决策层：显式参数 > prompt 风格词 > DesignSpec（LLM 设计师）
        # > 场景分类 > 配方默认。
        # 旅行（travel）走独立主题体系，resolve_design 内直接透传，不影响其流程。
        design_spec = None
        if isinstance(intent.meta, dict):
            design_spec = intent.meta.pop("design", None)
        if not isinstance(design_spec, dict):
            design_spec = None
        design = resolve_design(
            prompt,
            recipe_name=recipe_name,
            theme=theme,
            style=style,
            color_scheme=color_scheme,
            cover=cover,
            toc=toc,
            cover_style=cover_style,
            recipe_theme=recipe.css_template,
            recipe_color=recipe.color_scheme,
            design_spec=design_spec,
        )
        design = enforce_design(design, recipe)
        final_style = style or recipe.css_template
        final_theme = design.theme
        final_color = design.color_scheme
        cover = design.cover
        toc = design.toc
        # 封面风格注入：显式 cover_style > 场景 → cover_style + 封面辅助数据
        if cover and intent.meta is not None:
            # 显式传入的 cover_style 优先于场景自动选择
            effective_cover_style = design.cover_style or "left-aligned"
            intent.meta["cover_style"] = effective_cover_style
            # Agent 输出的封面元数据（<!-- cover-meta: {...} -->）优先
            cover_meta = _extract_cover_meta(markdown)
            if cover_meta:
                for key, value in cover_meta.items():
                    if value is not None and value != "":
                        intent.meta.setdefault(key, value)
            intent.meta.setdefault("badge", design.scene_label or "PDF")
            intent.meta.setdefault("author", "AI Divine")
            intent.meta.setdefault("date", datetime.now().strftime("%Y-%m-%d"))
            week_range = _this_week_range()
            # 各封面风格的特色字段默认值（Agent/用户显式提供时优先）
            if effective_cover_style == "minimal":
                intent.meta.setdefault(
                    "doc_type",
                    f"{design.scene_label or 'DOC'} · {week_range}",
                )
                intent.meta.setdefault(
                    "info", {"周期": week_range, "来源": "AI Divine"}
                )
            elif effective_cover_style == "split":
                intent.meta.setdefault(
                    "meta",
                    {
                        "汇报对象": "管理层",
                        "周期": intent.meta["date"],
                        "来源": "AI Divine",
                    },
                )
                if not intent.meta.get("highlight") and markdown:
                    highlight = _hero_stat_from_markdown(markdown)
                    if highlight:
                        intent.meta["highlight"] = highlight
            elif effective_cover_style == "centered":
                intent.meta.setdefault("issue_no", intent.meta["date"])
            elif effective_cover_style == "left-aligned":
                intent.meta.setdefault(
                    "meta",
                    {"作者": intent.meta["author"], "日期": intent.meta["date"]},
                )
            elif effective_cover_style == "hero-graphic":
                intent.meta.setdefault("cta_text", "→ 详见正文")
        if recipe_name == "travel" or final_theme.startswith("travel"):
            cover = True
            toc = False
        # 非旅行配方开启配图时：远程图/keyword 图下载内嵌，失败降级占位块
        #（travel 的配图在 render_html_to_pdf 内部处理）
        if images and recipe_name != "travel":
            markdown = inline_markdown_images(markdown)
        if recipe_name == "travel" and final_theme.startswith("travel"):
            # 主色优先级：theme_colors 显式值 > DesignSpec 主色 > color_scheme 预设
            travel_custom = color_overrides
            if not travel_custom and design.primary_color:
                travel_custom = {"--color-primary": design.primary_color}
            overrides = travel_color_overrides(
                final_color, travel_custom, theme=final_theme
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
            # travel 固定页式排版：质检只上报（空白页/越界），不自动修复
            meta["qa"] = inspect_pdf(output)
        else:
            # 合并链：DesignSpec 派生色 → theme_colors 显式值（后者优先）
            md_overrides = universal_color_overrides(color_overrides)
            if design.primary_color:
                derived = derive_universal_palette(design.primary_color)
                if derived:
                    md_overrides = {**derived, **md_overrides}
            meta, qa_report = render_with_qa(
                partial(
                    render_markdown_to_pdf,
                    markdown,
                    output,
                    title=intent.title,
                ),
                output,
                {
                    "style": final_style,
                    "color_scheme": final_color,
                    "paper_size": paper_size,
                    "cover": cover,
                    "toc": toc,
                    "base_dir": base_dir,
                    "theme": final_theme,
                    "cover_data": intent.meta,
                    "overrides": md_overrides or None,
                },
            )
            meta["qa"] = qa_report
        return {
            "recipe": recipe.name,
            "display_name": recipe.display_name,
            "theme": final_theme,
            "design": design.as_dict(),
            "intent": {
                "title": intent.title,
                "topic": intent.topic,
                "sections": intent.sections,
                "meta": intent.meta,
            },
            "markdown": markdown,
            **meta,
        }
