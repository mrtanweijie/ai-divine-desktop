from __future__ import annotations

import html as html_lib
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
        "file": "travel_template.html",
        "display_name": "旅行手册",
        "description": "米白纸感 + 暖橙 + 青蓝，适合旅行攻略、路线手册、目的地指南",
        "variables": {
            "--color-primary": "#b8743a",
            "--color-primary-light": "#d49556",
            "--color-primary-dark": "#8b5a2b",
            "--color-accent": "#2c6e7f",
            "--bg-page": "#faf6f0",
            "--bg-card": "#ffffff",
            "--bg-section": "#f3ede3",
            "--bg-highlight": "#fff8ee",
            "--text-primary": "#2c2420",
            "--text-secondary": "#6b5d52",
            "--text-muted": "#9a8b7e",
            "--color-morning": "#c98b3a",
            "--color-afternoon": "#b06a2c",
            "--color-evening": "#5b4e6e",
            "--color-warning": "#c0392b",
            "--border-color": "#e0d5c7",
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

_TRAVEL_PRINT_CSS = """
@page {
  size: A4;
  margin: 2.2cm 1.8cm 2.5cm 1.8cm;

  @top-center {
    content: element(header);
    border-bottom: 1pt solid #e0d5c7;
    padding-bottom: 5pt;
  }

  @bottom-center {
    content: counter(page) " / " counter(pages);
    font-size: 8.5pt;
    color: #9a8b7e;
    font-family: "Noto Sans SC", "PingFang SC", sans-serif;
  }
}

@page cover {
  size: A4;
  margin: 0;

  @top-center {
    content: none;
  }

  @bottom-center {
    content: none;
  }
}

.cover {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  page: cover;
  height: 297mm;
  min-height: 297mm;
  padding: 80pt 30pt 60pt;
  position: relative;
  overflow: hidden;
  page-break-after: always;
}

.cover-bg {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 0;
}

.cover-content {
  position: relative;
  z-index: 1;
  color: var(--text-inverse);
}

.page.day-block {
  page-break-after: auto;
  page-break-inside: avoid;
}

.page.day-block + .page.day-block {
  border-top: 1pt solid var(--border-color);
}

.header {
  position: running(header);
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 8pt;
  color: var(--text-muted);
}

.header .doc-title {
  font-weight: 600;
  color: var(--color-primary-dark);
}

@media print {
  html,
  body {
    background: #ffffff;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }

  .page,
  .cover {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
}
"""

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
      <div class="cover-bg"></div>
      <div class="cover-content">
        <div class="cover-countries">{countries}</div>
        <h1 class="cover-title">{title}</h1>
        <div class="cover-meta">{meta_line}</div>
        <div class="cover-meta" style="font-size:14px;">{meta_secondary}</div>
        <div class="cover-route-tags">{route_tags}</div>
        <p class="cover-summary">{summary}</p>
      </div>
    </div>
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
        if theme_id == "travel":
            css = self._travel_css()
        else:
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

    def _travel_css(self) -> str:
        template_path = self.themes_dir / "travel_template.html"
        template = template_path.read_text(encoding="utf-8")
        match = re.search(
            r"<style[^>]*>(.*?)</style>",
            template,
            re.IGNORECASE | re.DOTALL,
        )
        css = match.group(1) if match else template
        return css + _TRAVEL_PRINT_CSS


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
    cover_data: dict[str, Any] | None = None,
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
        "dates": "",
        "countries": "",
        "meta_line": "",
        "meta_secondary": "",
        "route_tags": "",
        "summary": subtitle,
        "total_weeks": "",
        "total_nodes": "",
        "goal": "",
    }
    extra = dict(cover_data or {})
    route = extra.pop("route", None)
    if isinstance(route, list):
        tags = [
            str(item).strip()
            for item in route
            if item is not None and str(item).strip()
        ]
        extra["route_tags"] = (
            "".join(
                f'<span class="cover-tag">{html_lib.escape(tag)}</span>'
                for tag in tags
            )
            if tags
            else ""
        )
        if not extra.get("countries") and tags:
            extra["countries"] = " × ".join(tags[:2])
    if not extra.get("meta_line"):
        meta_parts = [
            str(extra.get(key) or "").strip()
            for key in ("destination", "duration", "travelers", "dates")
        ]
        extra["meta_line"] = (
            " · ".join(part for part in meta_parts if part)
            or subtitle
            or "AI Divine 生成文档"
        )
    extra["summary"] = str(extra.get("summary") or subtitle or "").strip()
    extra["meta_secondary"] = str(
        extra.get("meta_secondary") or extra.get("route_constraint") or ""
    ).strip()
    for key, value in list(extra.items()):
        if key == "route_tags" or value is None:
            continue
        extra[key] = html_lib.escape(str(value))
    data.update(extra)
    return template.format(**data)


def build_travel_html_document(
    html_body: str,
    title: str,
    subtitle: str = "AI Divine 生成文档",
    cover_data: dict[str, Any] | None = None,
    include_cover: bool = True,
) -> str:
    css = load_theme_css("travel")
    cover_html = (
        build_cover_html("travel", html_lib.escape(title), subtitle, cover_data)
        if include_cover
        else ""
    )
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<style>{css}</style></head><body>"
        "<div class=\"header\">"
        f"<span class=\"doc-title\">{html_lib.escape(title)}</span>"
        "</div>"
        f"{cover_html}{html_body}</body></html>"
    )
