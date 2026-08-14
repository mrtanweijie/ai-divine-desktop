from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
        "file": "travel.css",
        "display_name": "旅行暖橙",
        "description": "暖橙 + 自然绿，适合旅游攻略、美食指南",
        "variables": {
            "--primary": "#ea580c",
            "--primary-light": "#fff7ed",
            "--primary-dark": "#9a3412",
            "--accent": "#059669",
            "--text": "#1c1917",
            "--bg-soft": "#fffbeb",
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

COVER_TEMPLATES: dict[str, str] = {
    "resume": """
    <div class="cover">
      <h1>{title}</h1>
      <div class="subtitle">{subtitle}</div>
      <div class="meta">{theme_name}</div>
    </div>
    <div style="page-break-after:always;"></div>
    """,
    "universal": """
    <div class="cover">
      <div class="cover-content">
        <div class="badge">{badge}</div>
        <h1>{title}</h1>
        <div class="subtitle">{subtitle}</div>
        <div class="meta">
          <span>PDF</span>
          <span class="meta-divider"></span>
          <span>{theme_name}</span>
          <span class="meta-divider"></span>
          <span>AI Divine</span>
        </div>
      </div>
      <div class="footer-note">AI Divine · {theme_name}</div>
    </div>
    <div style="page-break-after:always;"></div>
    """,
    "modern": """
    <div class="cover">
      <div class="cover-content">
        <div class="badge">{badge}</div>
        <h1>{title}</h1>
        <div class="subtitle">{subtitle}</div>
        <div class="meta">
          <span>PDF</span>
          <span class="meta-divider"></span>
          <span>{theme_name}</span>
          <span class="meta-divider"></span>
          <span>AI Divine</span>
        </div>
      </div>
      <div class="footer-note">AI Divine · {theme_name}</div>
    </div>
    <div style="page-break-after:always;"></div>
    """,
    "notion": """
    <div class="cover">
      <h1>{title}</h1>
      <div class="subtitle">{subtitle}</div>
      <div class="meta">{date}</div>
    </div>
    <div style="page-break-after:always;"></div>
    """,
    "linear": """
    <div class="cover">
      <div class="badge">{badge}</div>
      <h1>{title}</h1>
      <div class="subtitle">{subtitle}</div>
      <div class="meta">{theme_name} · AI Divine</div>
    </div>
    <div style="page-break-after:always;"></div>
    """,
    "apple": """
    <div class="cover">
      <div class="badge">{badge}</div>
      <h1>{title}</h1>
      <div class="subtitle">{subtitle}</div>
      <div class="meta">
        <span>PDF</span>
        <span class="meta-divider"></span>
        <span>{theme_name}</span>
        <span class="meta-divider"></span>
        <span>AI Divine</span>
      </div>
      <div class="footer-note">AI Divine · {theme_name}</div>
    </div>
    <div style="page-break-after:always;"></div>
    """,
    "academic": """
    <div class="cover">
      <div class="institution">{institution}</div>
      <h1>{title}</h1>
      <div class="subtitle">{subtitle}</div>
      <div class="author-block">
        <div class="name">{author}</div>
        <div>{affiliation}</div>
      </div>
      <div class="date">{date}</div>
    </div>
    <div style="page-break-after:always;"></div>
    """,
    "travel": """
    <div class="cover">
      <div class="cover-content">
        <div class="badge">旅行攻略</div>
        <h1>{title}</h1>
        <div class="subtitle">{subtitle}</div>
        <div class="trip-meta">
          <div class="trip-meta-item">目的地：{destination}</div>
          <div class="trip-meta-item">天数：{duration}</div>
          <div class="trip-meta-item">人数：{travelers}</div>
        </div>
      </div>
      <div class="footer-note">AI Divine · {theme_name}</div>
    </div>
    <div style="page-break-after:always;"></div>
    """,
    "roadmap": """
    <div class="cover">
      <div class="cover-content">
        <div class="badge">学习路线</div>
        <h1>{title}</h1>
        <div class="subtitle">{subtitle}</div>
        <div class="roadmap-meta">
          <div class="meta-item">周期：{total_weeks}</div>
          <div class="meta-item">节点：{total_nodes}</div>
          <div class="meta-item">目标：{goal}</div>
        </div>
      </div>
      <div class="footer-note">AI Divine · {theme_name}</div>
    </div>
    <div style="page-break-after:always;"></div>
    """,
    "minimal": """
    <div class="cover">
      <h1>{title}</h1>
      <div class="subtitle">{subtitle}</div>
      <div class="meta">{date}</div>
    </div>
    <div style="page-break-after:always;"></div>
    """,
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
        css = Path(theme.css_path or "").read_text(encoding="utf-8")
        variables = dict(theme.variables)
        if overrides:
            variables.update(overrides)
        root_vars = "\n".join(f"  {key}: {value};" for key, value in variables.items())
        css = css.replace(":root {", f":root {{\n{root_vars}")
        css = re.sub(
            r"size:\s*A4\s*;",
            f"size: {paper_size};",
            css,
            flags=re.IGNORECASE,
        )
        self._cache[cache_key] = css
        return css


_default_manager: ThemeManager | None = None


def get_theme_manager() -> ThemeManager:
    global _default_manager
    if _default_manager is None:
        _default_manager = ThemeManager()
    return _default_manager


def load_theme_css(
    theme_id: str = "universal",
    overrides: dict[str, str] | None = None,
    paper_size: str = "A4",
) -> str:
    return get_theme_manager().load_css(theme_id, overrides, paper_size)


def list_available_themes() -> list[dict[str, str]]:
    return get_theme_manager().list_themes()


def build_cover_html(
    theme_id: str,
    title: str,
    subtitle: str = "",
    cover_data: dict[str, str] | None = None,
) -> str:
    theme = get_theme_manager().get_theme(theme_id)
    template = COVER_TEMPLATES.get(theme_id, COVER_TEMPLATES["universal"])
    data = {
        "title": title,
        "subtitle": subtitle,
        "badge": "PDF",
        "theme_name": theme.display_name,
        "author": "AI Divine",
        "affiliation": "",
        "date": "",
        "institution": "",
        "destination": "",
        "duration": "",
        "travelers": "",
        "total_weeks": "",
        "total_nodes": "",
        "goal": "",
    }
    if cover_data:
        data.update(cover_data)
    return template.format(**data)
