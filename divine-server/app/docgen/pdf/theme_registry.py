"""主题注册与 CSS 加载：THEMES 注册表、ThemeManager、主题/模块 CSS 组装。

从 theme_manager.py（原 2,039 行单文件）拆出。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any
from .theme_colors import _semantic_colors

THEMES: dict[str, dict[str, Any]] = {
    "universal": {
        "file": "universal.css",
        "display_name": "通用现代",
        "description": "中性蓝灰，适合报告、攻略、路线、手册、讲义等通用场景",
        "variables": {
            "--primary": "#2563eb",
            "--primary-light": "#eff6ff",
            "--primary-dark": "#1e40af",
            "--accent": "#0ea5e9",
            "--text": "#111827",
            "--bg-soft": "#f8fafc",
        },
    },
    "resume": {
        "file": "resume.css",
        "display_name": "个人简历",
        "description": "单栏专业简历，适合求职、简历打印",
        "variables": {
            "--primary": "#1e40af",
            "--primary-light": "#eff6ff",
            "--text": "#1f2937",
            "--text-secondary": "#4b5563",
            "--bg-soft": "#f8fafc",
        },
    },
    "notion": {
        "file": "notion.css",
        "display_name": "Notion 极简",
        "description": "留白多、轻量编辑感，适合阅读型文档",
        "variables": {
            "--primary": "#2383e2",
            "--primary-light": "#eaf3fd",
            "--text": "#37352f",
            "--text-secondary": "#6b6b6b",
            "--bg-soft": "#f7f7f5",
        },
    },
    "linear": {
        "file": "linear.css",
        "display_name": "Linear 紧凑",
        "description": "高信息密度，适合研发协作文档",
        "variables": {
            "--primary": "#5e6ad2",
            "--primary-light": "#f0f1ff",
            "--text": "#202129",
            "--text-secondary": "#5c5f6e",
            "--bg-soft": "#f7f7fb",
        },
    },
    "apple": {
        "file": "apple.css",
        "display_name": "Apple 舒适",
        "description": "大圆角、柔和阴影，视觉舒适",
        "variables": {
            "--primary": "#0071e3",
            "--primary-light": "#e8f2ff",
            "--text": "#1d1d1f",
            "--text-secondary": "#6e6e73",
            "--bg-soft": "#f5f5f7",
        },
    },
    "modern": {
        "file": "modern.css",
        "display_name": "现代科技",
        "description": "蓝灰配色，适合技术报告、商业文档",
        "variables": {
            "--primary": "#2563eb",
            "--primary-light": "#dbeafe",
            "--primary-dark": "#1e40af",
            "--accent": "#0ea5e9",
            "--text": "#1e293b",
            "--bg-soft": "#f8fafc",
        },
    },
    "academic": {
        "file": "academic.css",
        "display_name": "学术典雅",
        "description": "衬线字体 + 酒红点缀，适合论文、研究报告",
        "variables": {
            "--primary": "#742a2a",
            "--primary-light": "#fef5f5",
            "--accent": "#2d3748",
            "--text": "#1a202c",
            "--bg-soft": "#f7fafc",
        },
    },
    "travel": {
        "file": "travel_template.html",
        "display_name": "旅行手册",
        "description": "深青绿 + 米色重点块，严格复刻旅行手册 PDF",
        "variables": {
            "--color-primary": "#2a5a5b",
            "--color-accent": "#3a8a8b",
            "--color-accent-light": "#5ba3a4",
            "--bg-page": "#ffffff",
            "--bg-card": "#ffffff",
            "--bg-highlight": "#f5f1e8",
            "--bg-cover": "#2a3e3e",
            "--text-primary": "#2c3333",
            "--text-secondary": "#5a6a6a",
            "--text-muted": "#8a9a9a",
            "--text-inverse": "#ffffff",
            "--border-light": "#e5e5e5",
            "--border-table": "#dde5e5",
        },
    },
    "travel_mag": {
        "file": "travel_optimized.html",
        "display_name": "旅行杂志",
        "description": "衬线标题 + teal/琥珀杂志风，渐变大图封面，适合精品旅行手册",
        "variables": {
            "--color-primary": "#2a5a5b",
            "--color-accent": "#3a8a8b",
            "--color-accent-light": "#5ba3a4",
            "--bg-page": "#ffffff",
            "--bg-highlight": "#f6f2e9",
            "--bg-cover": "#162e2f",
            "--text-primary": "#22302f",
            "--text-secondary": "#556563",
            "--text-muted": "#8a9a97",
            "--text-inverse": "#ffffff",
            "--border-light": "#e3e9e8",
            "--border-table": "#d8e2e1",
        },
    },
    "travel_swiss": {
        "file": "travel_swiss.html",
        "display_name": "旅行瑞士网格",
        "description": "近黑 + 朱红单强调色，排版驱动的极简现代风，适合都市与人文路线",
        "variables": {
            "--color-primary": "#E4572E",
            "--color-accent": "#C74722",
            "--color-accent-light": "#F08A68",
            "--bg-page": "#FAFAF8",
            "--bg-highlight": "#FBE9E2",
            "--bg-cover": "#141414",
            "--text-primary": "#1d1d1b",
            "--text-secondary": "#5C5C58",
            "--text-muted": "#8F8F89",
            "--text-inverse": "#ffffff",
            "--border-light": "#E2DFD8",
            "--border-table": "#D6D2C8",
        },
    },
    "travel_bento": {
        "file": "travel_bento.html",
        "display_name": "旅行便当卡片",
        "description": "靛蓝 + 圆角卡片的产品化现代风，chip 与渐变胶囊点缀，适合亲子与轻户外",
        "variables": {
            "--color-primary": "#4F46E5",
            "--color-accent": "#6D28D9",
            "--color-accent-light": "#A5B4FC",
            "--bg-page": "#ffffff",
            "--bg-highlight": "#EEF0FE",
            "--bg-cover": "#312E81",
            "--text-primary": "#1B1F27",
            "--text-secondary": "#5B6472",
            "--text-muted": "#9AA3B2",
            "--text-inverse": "#ffffff",
            "--border-light": "#E7E9EE",
            "--border-table": "#E7E9EE",
        },
    },
    "travel_aurora": {
        "file": "travel_aurora.html",
        "display_name": "旅行暗夜极光",
        "description": "深夜蓝封面 + 青紫光晕，科技感现代风，适合自然风光与星空路线",
        "variables": {
            "--color-primary": "#0891B2",
            "--color-accent": "#7C3AED",
            "--color-accent-light": "#67E8F9",
            "--bg-page": "#ffffff",
            "--bg-highlight": "#0B1020",
            "--bg-cover": "#0B1020",
            "--text-primary": "#171C2B",
            "--text-secondary": "#5A6172",
            "--text-muted": "#98A0B3",
            "--text-inverse": "#ffffff",
            "--border-light": "#E5E8F0",
            "--border-table": "#E5E8F0",
        },
    },
    "roadmap": {
        "file": "roadmap.css",
        "display_name": "知识图谱",
        "description": "深紫 + 科技蓝渐变，适合学习路线、技能树",
        "variables": {
            "--primary": "#7c3aed",
            "--primary-light": "#f3e8ff",
            "--primary-dark": "#4c1d95",
            "--accent": "#2563eb",
            "--text": "#1e1b4b",
            "--bg-soft": "#faf5ff",
        },
    },
    "minimal": {
        "file": "minimal.css",
        "display_name": "极简黑白",
        "description": "留白为主，适合笔记、日记、简洁报告",
        "variables": {
            "--text": "#222222",
            "--text-secondary": "#555555",
            "--bg-soft": "#fafafa",
            "--border": "#eeeeee",
        },
    },
}


@dataclass
class ThemeConfig:
    name: str
    display_name: str
    description: str
    variables: dict[str, str] = field(default_factory=dict)
    css_path: str | None = None


class ThemeManager:
    def __init__(self, themes_dir: Path | None = None) -> None:
        self.themes_dir = themes_dir or (
            Path(__file__).resolve().parent / "pdf_themes"
        )
        self._cache: dict[str, str] = {}

    def list_themes(self) -> list[dict[str, str]]:
        return [
            {
                "id": theme_id,
                "name": info["display_name"],
                "description": info["description"],
            }
            for theme_id, info in THEMES.items()
        ]

    def get_theme(self, theme_id: str) -> ThemeConfig:
        if theme_id not in THEMES:
            theme_id = "universal"
        info = THEMES[theme_id]
        return ThemeConfig(
            name=theme_id,
            display_name=info["display_name"],
            description=info["description"],
            variables=info["variables"],
            css_path=str(self.themes_dir / info["file"]),
        )

    def load_css(
        self,
        theme_id: str = "universal",
        overrides: dict[str, str] | None = None,
        paper_size: str = "A4",
    ) -> str:
        cache_key = json.dumps(
            [theme_id, overrides or {}, paper_size],
            ensure_ascii=False,
            sort_keys=True,
        )
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        theme = self.get_theme(theme_id)
        if theme_id.startswith("travel"):
            css = self._travel_css(theme_id)
        else:
            css = Path(theme.css_path or "").read_text(encoding="utf-8")
        variables = dict(theme.variables)
        # 语义色 token：主题未定义时按深浅自动注入（模块 callout/trend 使用）
        if "--success" not in variables:
            variables.update(_semantic_colors(theme_id))
        if overrides:
            variables.update(overrides)
        # 标准别名（--primary/--accent 等）一律按「主题默认 + 覆盖值」重算，
        # 不能先物化再覆盖：旅行配色管线只带 --color-* 系，若别名已按主题
        # 默认值物化（如 swiss 的 --accent=#C74722），换色后会原样保留，
        # 表现为“选了主题色没效果”。
        variables.update(_module_standard_vars(variables))
        root_vars = "\n".join(f"  {key}: {value};" for key, value in variables.items())
        if variables:
            css += f"\n:root {{\n{root_vars}\n}}\n"
        css = re.sub(
            r"size:\s*A4\s*;",
            f"size: {paper_size};",
            css,
            flags=re.IGNORECASE,
        )
        self._cache[cache_key] = css
        return css

    def _travel_css(self, theme_id: str = "travel") -> str:
        filename = THEMES.get(theme_id, {}).get("file") or "travel_template.html"
        template_path = self.themes_dir / filename
        template = template_path.read_text(encoding="utf-8")
        match = re.search(
            r"<style[^>]*>(.*?)</style>",
            template,
            re.IGNORECASE | re.DOTALL,
        )
        css = match.group(1) if match else template
        return css


_TRAVEL_SKELETON_CACHE: dict[str, str] = {}


def travel_template_skeleton(theme: str = "travel") -> str:
    """从 travel 模板提取紧凑的页面结构骨架（供 LLM 生成旅行攻略时参考）。

    保留文件头部的【页面映射总表】注释 + 每种页面的代表性示例（去样式、去注释、
    去重复页、去页脚），保证 AI 生成的内容与模板的页面结构一一对应。
    骨架随模板文件自动更新，无需手工维护。
    """
    cached = _TRAVEL_SKELETON_CACHE.get(theme)
    if cached:
        return cached
    filename = THEMES.get(theme, {}).get("file")
    if not filename:
        filename = (
            "travel_optimized.html" if theme == "travel_mag" else "travel_template.html"
        )
    template_path = (
        Path(__file__).resolve().parent / "pdf_themes" / filename
    )
    template = template_path.read_text(encoding="utf-8")

    first_comment_match = re.search(r"<!--(.*?)-->", template, re.DOTALL)
    first_comment = (
        first_comment_match.group(1).strip() if first_comment_match else ""
    )

    no_style = re.sub(
        r"<style[^>]*>.*?</style>",
        "",
        template,
        flags=re.IGNORECASE | re.DOTALL,
    )
    no_comments = re.sub(r"<!--.*?-->", "", no_style, flags=re.DOTALL)
    chunks = re.split(r'(?=<div class="page)', no_comments)
    pages = [
        chunk
        for chunk in chunks
        if chunk.lstrip().startswith('<div class="page')
    ]

    # 每种页面保留的代表性示例数量（顺序与模板页序一致）
    keep_counts = {
        "cover": 1,        # P1 封面
        "overview": 1,     # P2 路线总览
        "day": 1,          # P3 每日行程（示例，其余天数同构重复）
        "culture": 1,      # P4 游牧文化体验专页（可选特色页）
        "risk": 1,         # P5 行李天气与风险控制
        "budget": 1,       # P6 预算与预订节奏（可选扩展页）
    }

    def classify(page: str) -> str:
        # 现代旅行主题（swiss/bento/aurora）页面标记（优先判定，
        # 其 body 不含下方经典/mag 标记，不会互相误判）
        if 'class="stepper"' in page:
            return "overview"
        if 'class="day-bar"' in page:
            return "day"
        if 'class="budget-bars"' in page:
            return "budget"
        # 经典（travel）/ 杂志（travel_mag）页面标记
        if "cover-band" in page:
            return "cover"
        if ">路线总览<" in page:
            return "overview"
        if 'class="day-title"' in page:
            return "day"
        if 'class="feature-title"' in page and "体验专页" in page:
            return "culture"
        if ">行李、天气与风险控制<" in page:
            return "risk"
        if "预算与预订节奏" in page:
            return "budget"
        return "other"  # 其他页面/碎片（不保留）

    seen: dict[str, int] = {}
    kept: list[str] = []
    for page in pages:
        kind = classify(page)
        if kind == "other":
            continue
        if seen.get(kind, 0) >= keep_counts.get(kind, 0):
            continue
        seen[kind] = seen.get(kind, 0) + 1
        page = re.sub(
            r'\s*<div class="page-footer">.*?</div>\s*',
            "",
            page,
            flags=re.DOTALL,
        )
        page = re.sub(r"\n{3,}", "\n\n", page).strip()
        kept.append(page)

    header_lines = [
        "以下是旅行手册 HTML 模板的页面结构骨架（来自 %s）。" % filename,
        "其中 {{双花括号}} 是内容占位符：输出时必须替换为实际内容，不要保留 {{ }}。",
        "页面顺序必须与【页面映射总表】一致：",
        "路线总览 → 每日行程 → 行李、天气与风险控制（游牧文化/体验专页为可选特色页）。",
    ]
    parts = ["\n".join(header_lines)]
    if first_comment:
        parts.append(first_comment)
    parts.extend(kept)
    result = "\n\n".join(parts)
    _TRAVEL_SKELETON_CACHE[theme] = result
    return result


_default_manager: ThemeManager | None = None


def get_theme_manager() -> ThemeManager:
    global _default_manager
    if _default_manager is None:
        _default_manager = ThemeManager()
    return _default_manager


# 模块标准变量：各主题变量命名不统一（--text vs --text-main、--bg-soft vs --bg-surface 等），
# 模块样式统一引用以下标准变量。按别名映射取主题值，缺失用默认值。
_MODULE_STANDARD_ALIASES: dict[str, tuple[str, ...]] = {
    "--primary": ("--primary", "--color-primary", "--text", "#2563eb"),
    "--primary-light": ("--primary-light", "--color-accent-light", "#eff6ff"),
    "--accent": ("--accent", "--color-accent", "--text-light", "#0ea5e9"),
    # swiss 模板直接引用 --accent-light（无回退），缺失时预算条无色
    "--accent-light": ("--accent-light", "--color-accent-light", "#e0f2fe"),
    "--text-main": ("--text-main", "--text", "#111827"),
    "--text-muted": ("--text-muted", "--text-secondary", "#4b5563"),
    "--text-light": ("--text-light", "#9ca3af"),
    "--bg-page": ("--bg-page", "#ffffff"),
    "--bg-surface": ("--bg-surface", "--bg-soft", "#f9fafb"),
    "--bg-dark": ("--bg-dark", "#1f2937"),
    "--border": ("--border", "#e5e7eb"),
}


def _module_standard_vars(variables: dict[str, str]) -> dict[str, str]:
    """从主题变量映射出模块标准变量（缺失项用默认值补齐）。"""
    out: dict[str, str] = {}
    for key, aliases in _MODULE_STANDARD_ALIASES.items():
        value = aliases[-1]  # 默认值（# 开头）
        for alias in aliases:
            if alias in variables:
                value = variables[alias]
                break
        out[key] = value
    return out


_MODULES_CSS: str | None = None


def _modules_css() -> str:
    """10 个布局模块样式（追加在所有主题 CSS 之后，主题变量由 :root 注入）。"""
    global _MODULES_CSS
    if _MODULES_CSS is None:
        path = Path(__file__).resolve().parent / "pdf_themes" / "modules.css"
        _MODULES_CSS = path.read_text(encoding="utf-8")
    return _MODULES_CSS


def load_theme_css(
    theme_id: str = "universal",
    overrides: dict[str, str] | None = None,
    paper_size: str = "A4",
) -> str:
    css = get_theme_manager().load_css(theme_id, overrides, paper_size)
    if "travel" not in theme_id:
        css += _modules_css()
    return css


def list_available_themes() -> list[dict[str, str]]:
    return get_theme_manager().list_themes()
