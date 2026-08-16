from __future__ import annotations

import colorsys
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

_TRAVEL_BASE_PRINT_CSS = """
@page {
  size: A4;
  margin: 1.2cm 1.5cm 1.0cm 1.5cm;

  @bottom-left {
    content: string(doc-title);
    font-size: 8.5pt;
    color: #9a8b7e;
    font-family: "Noto Sans SC", "PingFang SC", sans-serif;
    border-top: 0.5pt solid #d8c9b8;
    padding-top: 4pt;
    width: 50%;
    text-align: left;
    vertical-align: top;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  @bottom-right {
    content: counter(page);
    font-size: 8.5pt;
    color: #9a8b7e;
    font-family: "Noto Sans SC", "PingFang SC", sans-serif;
    border-top: 0.5pt solid #d8c9b8;
    padding-top: 4pt;
    width: 50%;
    text-align: right;
    vertical-align: top;
  }
}

.page.day-block {
  page-break-after: always;
  page-break-inside: auto;
}

.page {
  width: auto;
  min-height: auto;
  margin: 0;
  padding: 1.2cm 0 1.2cm;
  box-shadow: none;
  box-decoration-break: clone;
}

.header {
  visibility: hidden;
  height: 0;
  overflow: hidden;
}

.header .doc-title {
  string-set: doc-title content();
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

# 经典版 travel 封面专属打印规则
_TRAVEL_COVER_PRINT_CSS = """
@page cover {
  size: A4;
  margin: 0;

  @bottom-left {
    content: none;
  }

  @bottom-right {
    content: none;
  }
}

.page.cover {
  display: flex;
  flex-direction: column;
  page: cover;
  height: 297mm;
  min-height: 297mm;
  padding: 0;
  position: relative;
  overflow: hidden;
  page-break-after: always;
}

/* 封面顶部色条 */
.page.cover::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 14px;
  background: var(--color-primary);
}

.cover-band {
  margin-top: 100px;
  color: #2C3333;
  padding: 0 var(--spacing-2xl);
  text-align: left;
}
"""

# 杂志版 travel_mag 封面专属打印规则：全出血无页边距，封面样式由模板自带
_TRAVEL_MAG_COVER_PRINT_CSS = """
@page cover {
  size: A4;
  margin: 0;

  @bottom-left {
    content: none;
  }

  @bottom-right {
    content: none;
  }
}

.page.cover {
  display: flex;
  flex-direction: column;
  page: cover;
  height: 297mm;
  min-height: 297mm;
  padding: 0;
  position: relative;
  overflow: hidden;
  page-break-after: always;
}

/* 杂志版正文页左右留白统一由 @page margin 提供，此处仅去掉模板自带的 15mm 双份边距 */
.page:not(.cover) {
  padding: 1.2cm 0 1.2cm;
}
"""

_TRAVEL_PRINT_CSS = _TRAVEL_BASE_PRINT_CSS + _TRAVEL_COVER_PRINT_CSS
_TRAVEL_MAG_PRINT_CSS = _TRAVEL_BASE_PRINT_CSS + _TRAVEL_MAG_COVER_PRINT_CSS

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
    <div class="page cover">
      <div class="cover-band">
        <div class="cover-countries">{countries}</div>
        <h1 class="cover-title">{title}</h1>
        <div class="cover-meta">{meta_line}</div>
      </div>
    </div>
    """,
    "travel_mag": """
    <div class="page cover">
      <div class="cover-hero">
        <div class="hero-kicker">Travel Handbook · 2026</div>
        <div class="hero-watermark">{watermark}</div>
      </div>
      <div class="cover-band">
        <div class="cover-countries">{countries}</div>
        <h1 class="cover-title">{title}</h1>
        <div class="cover-meta">{meta_line}</div>
      </div>
      <div class="cover-body">
        <div class="cover-tagline">{meta_secondary}</div>
        <p class="cover-summary">{summary}</p>
        <div class="stat-row">{stat_pills}</div>
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
        if theme_id in ("travel", "travel_mag"):
            css = self._travel_css(theme_id)
        else:
            css = Path(theme.css_path or "").read_text(encoding="utf-8")
        variables = dict(theme.variables)
        if overrides:
            variables.update(overrides)
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
        filename = (
            "travel_optimized.html"
            if theme_id == "travel_mag"
            else "travel_template.html"
        )
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


def load_theme_css(
    theme_id: str = "universal",
    overrides: dict[str, str] | None = None,
    paper_size: str = "A4",
) -> str:
    return get_theme_manager().load_css(theme_id, overrides, paper_size)


def list_available_themes() -> list[dict[str, str]]:
    return get_theme_manager().list_themes()


TRAVEL_COLOR_PRESETS: dict[str, dict[str, str]] = {
    "teal": {
        "--color-primary": "#2a5a5b",
        "--color-accent": "#3a8a8b",
        "--color-accent-light": "#5ba3a4",
        "--bg-highlight": "#f5f1e8",
        "--bg-cover": "#2a3e3e",
    },
    "warm": {
        "--color-primary": "#b8743a",
        "--color-accent": "#d49556",
        "--color-accent-light": "#e5b37c",
        "--bg-highlight": "#fff3e6",
        "--bg-cover": "#5c3a24",
    },
    "blue": {
        "--color-primary": "#2f5b9e",
        "--color-accent": "#3d7bd6",
        "--color-accent-light": "#6fa8e8",
        "--bg-highlight": "#edf4fc",
        "--bg-cover": "#263a5c",
    },
    "green": {
        "--color-primary": "#2e6b4f",
        "--color-accent": "#3e9a6f",
        "--color-accent-light": "#72bd98",
        "--bg-highlight": "#edf7f1",
        "--bg-cover": "#243f35",
    },
    "purple": {
        "--color-primary": "#5b4b8a",
        "--color-accent": "#7a6bc2",
        "--color-accent-light": "#a99ce0",
        "--bg-highlight": "#f2effa",
        "--bg-cover": "#332b4a",
    },
    "monochrome": {
        "--color-primary": "#333333",
        "--color-accent": "#666666",
        "--color-accent-light": "#999999",
        "--bg-highlight": "#f5f5f5",
        "--bg-cover": "#222222",
    },
}

# travel_mag（杂志版）完整主题色预设。
# 每套主题定义 --teal-* 阶梯（主色）、--amber-*（点缀色）与 hero 封面渐变，
# 换主题色时整体覆盖。新增主题只需在此表加一项即可（键名为 color_scheme 取值）。
TRAVEL_MAG_THEMES: dict[str, dict[str, str]] = {
    # 深青绿（默认）：青绿 + 琥珀暖，经典雅致（模板 :root 默认值）
    "teal": {
        "--teal-50": "#EFF6F6", "--teal-100": "#DCECEC",
        "--teal-200": "#B8D9D9", "--teal-300": "#8CC0C1",
        "--teal-400": "#5BA3A4", "--teal-500": "#3A8A8B",
        "--teal-600": "#2A5A5B", "--teal-700": "#23494A",
        "--teal-800": "#1C3A3B", "--teal-900": "#162E2F",
        "--amber-100": "#F7EAD8", "--amber-300": "#E0BC8C",
        "--amber-500": "#C08552", "--amber-700": "#9A6536",
        "--bg-highlight": "#F6F2E9", "--bg-cover": "#162E2F",
        "--bg-soft": "#F4F7F7", "--border-light": "#E3E9E8",
        "--border-table": "#D8E2E1", "--text-primary": "#22302F",
        "--text-secondary": "#556563", "--text-muted": "#8A9A97",
        "--hero-1": "#162E2F", "--hero-2": "#23494A",
        "--hero-3": "#2A5A5B", "--hero-4": "#3A8A8B",
        "--hero-glow-1": "rgba(192,133,82,0.45)",
        "--hero-glow-2": "rgba(91,163,164,0.35)",
    },
    # 冰蓝主题（提取自 travel-guide-optimized.html）：冰川/极光质感
    "iceblue": {
        "--teal-50": "#EDF3F8", "--teal-100": "#D2E2EE",
        "--teal-200": "#A8C8DE", "--teal-300": "#7EAEC9",
        "--teal-400": "#5B98BD", "--teal-500": "#3A6B8C",
        "--teal-600": "#2C5775", "--teal-700": "#1E4361",
        "--teal-800": "#16344A", "--teal-900": "#0F2638",
        "--amber-100": "#E0EBF2", "--amber-300": "#A8C4D8",
        "--amber-500": "#6B9BBA", "--amber-700": "#3D6B8A",
        "--bg-highlight": "#EDF3F8", "--bg-cover": "#0F2638",
        "--bg-soft": "#EFF4F8", "--border-light": "#D8E0E8",
        "--border-table": "#C8D4E0", "--text-primary": "#1A2433",
        "--text-secondary": "#4A5A6E", "--text-muted": "#8A9BA8",
        "--hero-1": "#0F2638", "--hero-2": "#1E4361",
        "--hero-3": "#2C5775", "--hero-4": "#3A6B8C",
        "--hero-glow-1": "rgba(107,155,186,0.55)",
        "--hero-glow-2": "rgba(126,174,201,0.5)",
    },
    # 沙漠落日（提取自 travel-guide-optimized.html）：暖沙 + 落日金，辽阔热烈
    "desert": {
        "--teal-50": "#FBF3E4", "--teal-100": "#F5E6C8",
        "--teal-200": "#EBCF98", "--teal-300": "#DDB56A",
        "--teal-400": "#C89442", "--teal-500": "#A66A2E",
        "--teal-600": "#8B4513", "--teal-700": "#6D350F",
        "--teal-800": "#5C3A1E", "--teal-900": "#3D2510",
        "--amber-100": "#FBEDD8", "--amber-300": "#F0C97A",
        "--amber-500": "#D49142", "--amber-700": "#8B5A1E",
        "--bg-highlight": "#FBF3E4", "--bg-cover": "#3D2510",
        "--bg-soft": "#FAF5EE", "--border-light": "#EDE0CD",
        "--border-table": "#E0D0B8", "--text-primary": "#2A1F12",
        "--text-secondary": "#5C4A2E", "--text-muted": "#9A8A6E",
        "--hero-1": "#3D2510", "--hero-2": "#5C3A1E",
        "--hero-3": "#8B4513", "--hero-4": "#C77D3C",
        "--hero-glow-1": "rgba(192,133,82,0.55)",
        "--hero-glow-2": "rgba(212,145,66,0.4)",
    },
    # 复古胶片（提取自 travel-guide-optimized.html）：暖灰 + 古铜棕，怀旧胶片
    "vintage": {
        "--teal-50": "#F1EFE8", "--teal-100": "#E5E2D8",
        "--teal-200": "#D3D1C7", "--teal-300": "#B4B2A9",
        "--teal-400": "#888780", "--teal-500": "#6B6A5E",
        "--teal-600": "#5F5E5A", "--teal-700": "#4A4945",
        "--teal-800": "#444441", "--teal-900": "#2C2C2A",
        "--amber-100": "#F7EAD8", "--amber-300": "#D4A868",
        "--amber-500": "#A6772E", "--amber-700": "#633806",
        "--bg-highlight": "#F1EFE8", "--bg-cover": "#2C2C2A",
        "--bg-soft": "#F5F4EF", "--border-light": "#DDD9CC",
        "--border-table": "#CDC8B8", "--text-primary": "#2C2A24",
        "--text-secondary": "#5A5648", "--text-muted": "#8E8A78",
        "--hero-1": "#2C2C2A", "--hero-2": "#444441",
        "--hero-3": "#5F5E5A", "--hero-4": "#888780",
        "--hero-glow-1": "rgba(166,119,46,0.4)",
        "--hero-glow-2": "rgba(136,135,128,0.35)",
    },
    # 午夜墨黑（提取自 travel-guide-optimized.html）：墨蓝 + 夜紫，深邃静谧
    "midnight": {
        "--teal-50": "#2C2C40", "--teal-100": "#262638",
        "--teal-200": "#202032", "--teal-300": "#1A1A2A",
        "--teal-400": "#5A5A7E", "--teal-500": "#4A4A6E",
        "--teal-600": "#3A3A5C", "--teal-700": "#2E2E48",
        "--teal-800": "#222238", "--teal-900": "#16161E",
        "--amber-100": "#E8E6F0", "--amber-300": "#B0ACCC",
        "--amber-500": "#807CA8", "--amber-700": "#504C78",
        "--bg-page": "#FFFFFF", "--bg-highlight": "#F0F0F5",
        "--bg-cover": "#1A1A2E", "--bg-soft": "#F5F5F8",
        "--border-light": "#E0E0E8", "--border-table": "#D0D0DC",
        "--text-primary": "#1A1A2E", "--text-secondary": "#3A3A5C",
        "--text-muted": "#6A6A8A", "--text-inverse": "#FFFFFF",
        "--hero-1": "#0E0E18", "--hero-2": "#1A1A2E",
        "--hero-3": "#2E2E48", "--hero-4": "#3A3A5C",
        "--hero-glow-1": "rgba(90,90,126,0.4)",
        "--hero-glow-2": "rgba(128,124,168,0.3)",
    },

    # 纯黑主题（提取自 travel-guide-optimized.html）：极简纯黑
    "pureblack": {
        # 纯黑主题：teal 阶梯改为正常浅→深灰阶（浅色档做背景如 .ic/todo-list，
        # 深色档做文字如 teal-700），避免黑底黑字；hero/cover 保持深色。
        "--teal-50": "#F7F7F7", "--teal-100": "#EBEBEB",
        "--teal-200": "#DCDCDC", "--teal-300": "#C9C9C9",
        "--teal-400": "#9E9E9E", "--teal-500": "#757575",
        "--teal-600": "#333333", "--teal-700": "#1A1A1A",
        "--teal-800": "#111111", "--teal-900": "#000000",
        "--amber-100": "#E0E0E0", "--amber-300": "#A0A0A0",
        "--amber-500": "#707070", "--amber-700": "#404040",
        "--bg-page": "#FFFFFF", "--bg-highlight": "#F5F5F5",
        "--bg-cover": "#000000", "--bg-soft": "#FAFAFA",
        "--border-light": "#E0E0E0", "--border-table": "#CCCCCC",
        "--text-primary": "#000000", "--text-secondary": "#333333",
        "--text-muted": "#666666", "--text-inverse": "#FFFFFF",
        "--hero-1": "#000000", "--hero-2": "#1A1A1A",
        "--hero-3": "#333333", "--hero-4": "#555555",
        "--hero-glow-1": "rgba(60,60,60,0.2)",
        "--hero-glow-2": "rgba(30,30,30,0.15)",
    },
    # 雾凇青（提取自 travel-guide-optimized.html）：雾灰青 + 灰白，清冷淡雅
    "mistsage": {
        "--teal-50": "#F0F5F4", "--teal-100": "#E0EBE9",
        "--teal-200": "#C8DDD9", "--teal-300": "#A8C5C0",
        "--teal-400": "#8AB5B0", "--teal-500": "#6BA098",
        "--teal-600": "#5A8A82", "--teal-700": "#4A756E",
        "--teal-800": "#3A5A56", "--teal-900": "#2A4540",
        "--amber-100": "#E8EFEE", "--amber-300": "#B8C8C5",
        "--amber-500": "#8AA8A4", "--amber-700": "#5A7A76",
        "--bg-highlight": "#E8EFEE", "--bg-cover": "#2A4540",
        "--bg-soft": "#F2F6F5", "--border-light": "#DDE5E3",
        "--border-table": "#CCD8D5", "--text-primary": "#2A4540",
        "--text-secondary": "#4A6A64", "--text-muted": "#7A9A94",
        "--hero-1": "#2A4540", "--hero-2": "#3A5A56",
        "--hero-3": "#5A8A82", "--hero-4": "#8AB5B0",
        "--hero-glow-1": "rgba(138,181,176,0.35)",
        "--hero-glow-2": "rgba(106,160,152,0.3)",
    },
    # 晨雾灰蓝（提取自 travel-guide-optimized.html）：灰蓝 + 浅雾蓝，宁静柔和
    "mistblue": {
        "--teal-50": "#F0F4F8", "--teal-100": "#E0EAF0",
        "--teal-200": "#C8D8E4", "--teal-300": "#A8BDD0",
        "--teal-400": "#8AA8C0", "--teal-500": "#6A8AAA",
        "--teal-600": "#587892", "--teal-700": "#48687C",
        "--teal-800": "#3A5870", "--teal-900": "#2A4858",
        "--amber-100": "#EBF0F5", "--amber-300": "#BCCBD8",
        "--amber-500": "#8AA0B0", "--amber-700": "#5A7080",
        "--bg-highlight": "#EBF0F5", "--bg-cover": "#2A4858",
        "--bg-soft": "#F2F5F8", "--border-light": "#DDE4EA",
        "--border-table": "#CCD6E0", "--text-primary": "#2A4858",
        "--text-secondary": "#4A687C", "--text-muted": "#7A92A4",
        "--hero-1": "#2A4858", "--hero-2": "#3A5870",
        "--hero-3": "#587892", "--hero-4": "#8AA8C0",
        "--hero-glow-1": "rgba(138,168,192,0.35)",
        "--hero-glow-2": "rgba(106,138,170,0.3)",
    },
    # 暮山紫（提取自 travel-guide-optimized.html）：灰紫 + 淡藕色，温柔雅致
    "duskmauve": {
        "--teal-50": "#F2EFF4", "--teal-100": "#E4DFEA",
        "--teal-200": "#CCC4D6", "--teal-300": "#B8A8C0",
        "--teal-400": "#9A8AAB", "--teal-500": "#7E6E90",
        "--teal-600": "#6A5C7C", "--teal-700": "#584C6A",
        "--teal-800": "#4A3A5C", "--teal-900": "#382A48",
        "--amber-100": "#F0EDF2", "--amber-300": "#C8BECF",
        "--amber-500": "#9A8AAB", "--amber-700": "#6A5C7C",
        "--bg-highlight": "#F0EDF2", "--bg-cover": "#382A48",
        "--bg-soft": "#F4F2F6", "--border-light": "#E0DCE6",
        "--border-table": "#D0CAD8", "--text-primary": "#382A48",
        "--text-secondary": "#5A4C6A", "--text-muted": "#8A7A9A",
        "--hero-1": "#382A48", "--hero-2": "#4A3A5C",
        "--hero-3": "#6A5C7C", "--hero-4": "#9A8AAB",
        "--hero-glow-1": "rgba(154,138,171,0.35)",
        "--hero-glow-2": "rgba(126,110,144,0.3)",
    },
    # 初秋藕粉（提取自 travel-guide-optimized.html）：藕粉 + 暖灰，温暖不甜腻
    "lotuspink": {
        "--teal-50": "#F5F0EF", "--teal-100": "#EBE0DE",
        "--teal-200": "#DAC8C5", "--teal-300": "#D8B8B0",
        "--teal-400": "#C4A098", "--teal-500": "#A88880",
        "--teal-600": "#8E7068", "--teal-700": "#745852",
        "--teal-800": "#6A4A42", "--teal-900": "#4A342E",
        "--amber-100": "#F5EFEF", "--amber-300": "#D8C0BC",
        "--amber-500": "#B89890", "--amber-700": "#8A6A62",
        "--bg-highlight": "#F5EFEF", "--bg-cover": "#4A342E",
        "--bg-soft": "#F6F2F1", "--border-light": "#E5D8D5",
        "--border-table": "#D6C5C0", "--text-primary": "#4A342E",
        "--text-secondary": "#6A4A42", "--text-muted": "#9A7A72",
        "--hero-1": "#4A342E", "--hero-2": "#6A4A42",
        "--hero-3": "#8E7068", "--hero-4": "#C4A098",
        "--hero-glow-1": "rgba(196,160,152,0.35)",
        "--hero-glow-2": "rgba(168,136,128,0.3)",
    },
    # 沙丘米（提取自 travel-guide-optimized.html）：暖米沙 + 浅卡其，自然质朴
    "dunesand": {
        "--teal-50": "#F5F2EB", "--teal-100": "#EBE6D8",
        "--teal-200": "#DCD4BE", "--teal-300": "#D4C8B0",
        "--teal-400": "#BCAE92", "--teal-500": "#A49678",
        "--teal-600": "#8C7E62", "--teal-700": "#746450",
        "--teal-800": "#5C5240", "--teal-900": "#403828",
        "--amber-100": "#F5F2EB", "--amber-300": "#D8CEB8",
        "--amber-500": "#B8A882", "--amber-700": "#82745A",
        "--bg-highlight": "#F5F2EB", "--bg-cover": "#403828",
        "--bg-soft": "#F6F4EE", "--border-light": "#E2DCCF",
        "--border-table": "#D2C8B8", "--text-primary": "#403828",
        "--text-secondary": "#5C5240", "--text-muted": "#8A7E62",
        "--hero-1": "#403828", "--hero-2": "#5C5240",
        "--hero-3": "#8C7E62", "--hero-4": "#BCAE92",
        "--hero-glow-1": "rgba(188,174,146,0.35)",
        "--hero-glow-2": "rgba(164,150,120,0.3)",
    },
    # 烟雨灰（提取自 travel-guide-optimized.html）：暖灰 + 银灰，极简克制
    "smokegray": {
        "--teal-50": "#F2F1EE", "--teal-100": "#E6E4E0",
        "--teal-200": "#D2D0CC", "--teal-300": "#C0BFB8",
        "--teal-400": "#A8A7A0", "--teal-500": "#8E8D86",
        "--teal-600": "#76756E", "--teal-700": "#5E5D56",
        "--teal-800": "#4A4945", "--teal-900": "#343430",
        "--amber-100": "#F2F1EE", "--amber-300": "#C8C6C0",
        "--amber-500": "#A8A7A0", "--amber-700": "#76756E",
        "--bg-highlight": "#F2F1EE", "--bg-cover": "#343430",
        "--bg-soft": "#F4F3F0", "--border-light": "#DDD9D4",
        "--border-table": "#CCC8C2", "--text-primary": "#343430",
        "--text-secondary": "#4A4945", "--text-muted": "#7A7972",
        "--hero-1": "#343430", "--hero-2": "#4A4945",
        "--hero-3": "#76756E", "--hero-4": "#A8A7A0",
        "--hero-glow-1": "rgba(168,167,160,0.35)",
        "--hero-glow-2": "rgba(142,141,134,0.3)",
    },
}

# 常用颜色名 → 基准色值（未收录的颜色名可走 derive_travel_palette 的 HSL 派生）
COLOR_NAMES: dict[str, str] = {    "red": "#E74C3C",
    "红色": "#E74C3C",
    "orange": "#E67E22",
    "橙色": "#E67E22",
    "yellow": "#D4A017",
    "黄色": "#D4A017",
    "green": "#27AE60",
    "绿色": "#27AE60",
    "cyan": "#1FA8A0",
    "青色": "#1FA8A0",
    "blue": "#2F5B9E",
    "蓝色": "#2F5B9E",
    "purple": "#5B4B8A",
    "紫色": "#5B4B8A",
    "pink": "#C94F7C",
    "粉色": "#C94F7C",
    "brown": "#8B5E3C",
    "棕色": "#8B5E3C",
    "teal": "#2A5A5B",
    "青绿": "#2A5A5B",
    "gray": "#555555",
    "灰色": "#555555",
    "black": "#222222",
    "黑色": "#222222",
}

_HEX_COLOR_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")
_RGB_COLOR_RE = re.compile(
    r"^rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)$",
    re.IGNORECASE,
)


def _hex_to_rgb(value: str) -> tuple[int, int, int] | None:
    match = _HEX_COLOR_RE.match((value or "").strip())
    if not match:
        return None
    digits = match.group(1)
    return (
        int(digits[0:2], 16),
        int(digits[2:4], 16),
        int(digits[4:6], 16),
    )


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02X%02X%02X" % tuple(rgb)


def _shift_lightness(
    rgb: tuple[int, int, int], delta: float
) -> tuple[int, int, int]:
    r, g, b = (channel / 255.0 for channel in rgb)
    hue, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
    lightness = max(0.0, min(1.0, lightness + delta))
    r2, g2, b2 = colorsys.hls_to_rgb(hue, lightness, saturation)
    return (round(r2 * 255), round(g2 * 255), round(b2 * 255))


def _resolve_color(value: str) -> tuple[int, int, int] | None:
    """把 #hex / rgb() / 颜色名 统一解析为 RGB；无法解析返回 None。"""
    text = (value or "").strip()
    rgb = _hex_to_rgb(text)
    if rgb:
        return rgb
    match = _RGB_COLOR_RE.match(text)
    if match:
        r, g, b = (int(part) for part in match.groups())
        if all(0 <= channel <= 255 for channel in (r, g, b)):
            return (r, g, b)
    named = COLOR_NAMES.get(text.lower())
    if named:
        return _hex_to_rgb(named)
    return None


def derive_travel_palette(primary_color: str) -> dict[str, str] | None:
    """从单一主色派生整套旅行手册色调；无法解析时返回 None。

    派生规则（与预设 teal 的视觉关系一致）：
    - --color-primary：主色压深到 ≤35% 亮度（保证表头/封面条带白字可读）；
    - --color-accent / --color-accent-light：主色逐级提亮；
    - --bg-highlight：主色极浅的米色系背景块；
    - --bg-cover：主色加深的封面深色条带。
    """
    rgb = _resolve_color(primary_color)
    if not rgb:
        return None
    r, g, b = (channel / 255.0 for channel in rgb)
    hue, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
    primary_l = min(lightness, 0.35)
    primary = colorsys.hls_to_rgb(hue, primary_l, saturation)
    primary_rgb = (
        round(primary[0] * 255),
        round(primary[1] * 255),
        round(primary[2] * 255),
    )
    return {
        "--color-primary": _rgb_to_hex(primary_rgb),
        "--color-accent": _rgb_to_hex(_shift_lightness(primary_rgb, 0.10)),
        "--color-accent-light": _rgb_to_hex(
            _shift_lightness(primary_rgb, 0.22)
        ),
        "--bg-highlight": _rgb_to_hex(_shift_lightness(primary_rgb, 0.42)),
        "--bg-cover": _rgb_to_hex(_shift_lightness(primary_rgb, -0.12)),
    }


def _derive_hero_vars(scale: dict[str, str]) -> dict[str, str]:
    """从派生出的 teal 阶梯生成 hero 封面渐变变量（cover-hero 跟随主题色）。

    与 TRAVEL_MAG_THEMES 预设中 hero 的取色规则一致：
    hero-1 ← teal-900（最深）、hero-2 ← teal-700、hero-3 ← teal-600（主色）、
    hero-4 ← teal-400（亮色），光晕取对应色号的半透明。
    """
    def _rgba(hex_value: str | None, alpha: float) -> str | None:
        rgb = _hex_to_rgb(hex_value or "")
        if not rgb:
            return None
        return f"rgba({rgb[0]},{rgb[1]},{rgb[2]},{alpha})"

    hero = {
        "--hero-1": scale.get("--teal-900") or scale.get("--teal-800") or "#162E2F",
        "--hero-2": scale.get("--teal-700") or scale.get("--teal-600") or "#23494A",
        "--hero-3": scale.get("--teal-600") or "#2A5A5B",
        "--hero-4": scale.get("--teal-400") or scale.get("--teal-500") or "#3A8A8B",
    }
    glow1 = _rgba(scale.get("--teal-500"), 0.45)
    glow2 = _rgba(scale.get("--teal-300"), 0.35)
    if glow1:
        hero["--hero-glow-1"] = glow1
    if glow2:
        hero["--hero-glow-2"] = glow2
    return hero


def _derive_amber_vars(scale: dict[str, str]) -> dict[str, str]:
    """从派生的 teal 阶梯生成 amber 点缀色变量。

    模板多处使用 --amber-*（photo-placeholder 渐变、标签、高亮块等），
    派生路径（自定义色/旧预设名）不命中 TRAVEL_MAG_THEMES 精确分支，
    若不生成会残留模板默认琥珀色。这里直接复用 teal 阶梯同色系值，
    保证整本手册随主题色一致（淡雅系列预设的 amber 本就与 teal 同色相）。
    """
    amber: dict[str, str] = {}
    for src, dst in [
        ("--teal-100", "--amber-100"),
        ("--teal-300", "--amber-300"),
        ("--teal-500", "--amber-500"),
        ("--teal-700", "--amber-700"),
    ]:
        if scale.get(src):
            amber[dst] = scale[src]
    return amber


def derive_teal_scale(primary_color: str) -> dict[str, str] | None:
    """从单一主色派生 travel_mag（杂志版）使用的 teal 阶梯变量。

    原模板 --teal-50..900 以 #2A5A5B 为基准：越浅越接近白、越深越接近黑。
    这里以主色为 600 档，按同比例向浅色（50-500）和深色（700-900）扩展。
    """
    rgb = _resolve_color(primary_color)
    if not rgb:
        return None
    r, g, b = (channel / 255.0 for channel in rgb)
    hue, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
    # 600 档亮度 = min(主色亮度, 0.30)（深青绿基准 #2A5A5B 亮度≈0.27）
    base_l = min(lightness, 0.30)
    scale = {
        "--teal-600": _rgb_to_hex(
            (round(c * 255) for c in colorsys.hls_to_rgb(hue, base_l, saturation))
        ),
    }
    # 浅色档：50→500 逐步接近白（亮度递增）
    for idx, l in enumerate(
        [min(base_l + 0.62, 0.97), min(base_l + 0.50, 0.93),
         min(base_l + 0.38, 0.87), min(base_l + 0.27, 0.80),
         min(base_l + 0.15, 0.72), base_l + 0.05]
    ):
        key = "--teal-50" if idx == 0 else f"--teal-{idx * 100}"
        scale[key] = _rgb_to_hex(
            (round(c * 255) for c in colorsys.hls_to_rgb(hue, l, saturation))
        )
    # 深色档：700→900 逐步接近黑
    for idx, l in enumerate(
        [max(base_l - 0.06, 0.06), max(base_l - 0.12, 0.04),
         max(base_l - 0.18, 0.02)]
    ):
        key = f"--teal-{700 + idx * 100}"
        scale[key] = _rgb_to_hex(
            (round(c * 255) for c in colorsys.hls_to_rgb(hue, l, saturation))
        )
    return scale


def _resolve_theme_key(value: str) -> str | None:
    """把 LLM 可能传的主题名解析为 TRAVEL_MAG_THEMES 的 key。

    支持形式：中文 label（雾凇青）、key 带括号（mistsage（雾凇青）/
    雾凇青（mistsage））、key 前后有多余空白；无法识别返回 None。
    """
    text = (value or "").strip().lower()
    if not text:
        return None
    if text in TRAVEL_MAG_THEMES:
        return text
    # 中文 label → key（如 雾凇青 → mistsage）
    for theme_key, theme_vars in TRAVEL_MAG_THEMES.items():
        label = _TRAVEL_MAG_LABELS.get(theme_key)
        if label and label.lower() in text:
            return theme_key
    # 形如 "mistsage（雾凇青）" 或 "雾凇青（mistsage）"：提取括号内/外的英文 key
    for token in re.split(r"[()（）\s,，;；]+", text):
        if token and token in TRAVEL_MAG_THEMES:
            return token
    return None


_TRAVEL_MAG_LABELS: dict[str, str] = {
    "teal": "深青绿",
    "iceblue": "极地冰蓝",
    "desert": "沙漠落日",
    "vintage": "复古胶片",
    "midnight": "午夜墨黑",
    "pureblack": "纯黑",
    "mistsage": "雾凇青",
    "mistblue": "晨雾灰蓝",
    "duskmauve": "暮山紫",
    "lotuspink": "初秋藕粉",
    "dunesand": "沙丘米",
    "smokegray": "烟雨灰",
}


def _ensure_dark_cover(overrides: dict[str, str]) -> None:
    """--bg-cover 是封面深色条带（cover-band 背景，其上为白字），
    LLM 有时会传浅色（如 #F2E9DC/#E9F2F7）导致白字看不清：
    亮度超过阈值时压深为派生阶梯最深色（teal-900）。"""
    cover = overrides.get("--bg-cover")
    if not cover:
        return
    rgb = _hex_to_rgb(str(cover).strip().lstrip("#"))
    if not rgb:
        return
    luminance = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    if luminance > 150:
        scale = derive_teal_scale(
            overrides.get("--color-primary") or str(cover)
        )
        deep = (
            (scale or {}).get("--teal-900")
            or overrides.get("--teal-900")
            or "#2C2C2A"
        )
        overrides["--bg-cover"] = deep


def travel_color_overrides(
    color_scheme: str = "teal",
    custom: dict[str, str] | None = None,
    theme: str = "travel",
) -> dict[str, str]:
    """计算旅行手册的 CSS 变量覆盖。

    color_scheme 支持预设名（teal/blue/green/warm/purple/monochrome），
    也支持直接传颜色名或色值（如 "红色"、"#E74C3C"）自动派生整套色调；
    custom 里只需给 {"--color-primary": "<颜色>"} 即可派生配套色，
    显式传入的其他变量（--color-accent/--bg-cover/--bg-highlight 等）优先级最高。
    theme=travel_mag 时额外派生 --teal-50..900 阶梯变量。
    """
    key = (color_scheme or "teal").strip().lower()
    # 兼容 LLM 传中文主题名（"雾凇青"）或混合写法（"雾凇青（mistsage）"）：
    # 把中文 label 映射回主题 key，避免 fallback 成默认 teal。
    if key not in TRAVEL_MAG_THEMES and key not in TRAVEL_COLOR_PRESETS:
        resolved = _resolve_theme_key(key)
        if resolved:
            key = resolved
    # travel_mag 且命中完整主题预设：直接用整套主题色（精确颜色，不做 HSL 派生）
    if theme == "travel_mag" and key in TRAVEL_MAG_THEMES:
        overrides = dict(TRAVEL_MAG_THEMES[key])
        # 仍保留经典变量映射，供封面/通用样式使用
        preset = TRAVEL_COLOR_PRESETS.get(key)
        if preset:
            overrides.update(preset)
        primary = custom.get("--color-primary") if custom else None
        if primary:
            # 用户自定义主色（如通过“其他”输入）：
            # 从主色派生整套 teal 阶梯 + hero 封面渐变 + amber 点缀 + cover 深色，
            # 覆盖预设主题色，避免只改 --color-primary 一个变量（mag 模板不用它）。
            scale = derive_teal_scale(str(primary))
            if scale:
                overrides.update(scale)
                overrides.update(_derive_hero_vars(scale))
                overrides.update(_derive_amber_vars(scale))
                # cover-band 背景：取派生阶梯最深色（teal-900），与预设主题一致。
                # 直接覆盖（custom 显式给的 --bg-cover 会在 update(custom) 时覆盖回来）
                overrides["--bg-cover"] = (
                    scale.get("--teal-900") or scale.get("--teal-800")
                )
            overrides["--color-primary"] = str(primary)
        overrides.update(custom or {})
        overrides.pop("--primary", None)
        _ensure_dark_cover(overrides)
        return overrides
    if key in TRAVEL_COLOR_PRESETS:
        overrides = dict(TRAVEL_COLOR_PRESETS[key])
        primary_source = overrides.get("--color-primary")
    elif key in TRAVEL_MAG_THEMES:
        # 经典模板（travel）没有 --teal-* 阶梯变量：把 mag 主题映射为经典变量，
        # 使淡雅系列（雾凇青/晨雾灰蓝/沙丘米等）在经典模板下也能正确换色。
        mag = TRAVEL_MAG_THEMES[key]
        overrides = {
            "--color-primary": mag["--teal-600"],
            "--color-primary-dark": mag["--teal-800"],
            "--color-accent": mag["--teal-500"],
            "--color-accent-light": mag["--teal-400"],
            "--bg-highlight": mag["--bg-highlight"],
            "--bg-cover": mag["--bg-cover"],
        }
        primary_source = overrides.get("--color-primary")
    else:
        derived = derive_travel_palette(key)
        overrides = (
            derived if derived else dict(TRAVEL_COLOR_PRESETS["teal"])
        )
        primary_source = overrides.get("--color-primary")
    custom = dict(custom or {})
    primary = custom.get("--color-primary")
    if primary:
        derived = derive_travel_palette(str(primary))
        if derived:
            overrides.update(derived)
        primary_source = str(primary)
    if theme == "travel_mag" and primary_source:
        scale = derive_teal_scale(primary_source)
        if scale:
            overrides.update(scale)
            # 派生 hero 封面渐变变量，使 cover-hero 跟随主题色
            # （LLM 传旧预设名/自定义色值时不会命中 TRAVEL_MAG_THEMES 精确分支）
            overrides.update(_derive_hero_vars(scale))
            # 派生 amber 点缀色，避免 photo-placeholder 等渐变残留默认琥珀色
            overrides.update(_derive_amber_vars(scale))
            # cover-band 背景：取派生阶梯最深色（teal-900），与预设主题一致。
            # 直接覆盖（custom 显式给的 --bg-cover 会在 update(custom) 时覆盖回来）
            overrides["--bg-cover"] = (
                scale.get("--teal-900") or scale.get("--teal-800")
            )
    overrides.update(custom)
    overrides.pop("--primary", None)
    # --bg-cover 亮度兜底：LLM 传浅色时压深（cover-band 白字可读）
    _ensure_dark_cover(overrides)
    return overrides


def _watermark_from_title(title: str) -> str:
    """从标题提取封面水印简称。

    规则：优先取第一个分隔符（·｜|-—/空格）前的主体地名；
    否则去掉“数字+日/天/晚”的时长后缀；再退化为去掉数字后取前 4 个字符；
    兜底“旅行”。避免 170px 大字号水印被截断（如只显示前 2 字）。
    """
    text = str(title or "").strip()
    if not text:
        return "旅行"
    for sep in ("·", "｜", "|", "-", "—", "—", "/", " "):
        if sep in text:
            text = text.split(sep)[0].strip()
            break
    # 去掉时长后缀（阿拉伯数字或中文数字 + 日/天/晚），如“5日游”“十二日”
    m = re.search(r"(?:\d+|[零一二三四五六七八九十百千万两]+)\s*[日天晚]", text)
    if m:
        text = text[: m.start()].strip()
    text = re.sub(r"\d+", "", text)
    if not text:
        return "旅行"
    return text[:4] or "旅行"


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
        dates = str(extra.get("dates") or "").strip()
        tags = extra.get("tags")
        if isinstance(tags, list):
            tags = [str(t).strip() for t in tags if str(t).strip()]
        elif isinstance(tags, str):
            tags = [
                part.strip()
                for part in re.split(r"[,、×xX/]", tags)
                if part.strip()
            ]
        else:
            tags = []
        tag_line = " × ".join(tags)
        if tag_line and dates:
            extra["meta_line"] = f"{tag_line}｜{dates}"
        elif tag_line:
            extra["meta_line"] = tag_line
        elif dates:
            extra["meta_line"] = dates
        else:
            dest = str(extra.get("destination") or "").strip()
            dur = str(extra.get("duration") or "").strip()
            joined = " · ".join(part for part in (dest, dur) if part)
            extra["meta_line"] = joined or subtitle or "AI Divine 生成文档"
    extra["summary"] = str(extra.get("summary") or subtitle or "").strip()
    extra["meta_secondary"] = str(
        extra.get("meta_secondary") or extra.get("route_constraint") or ""
    ).strip()
    for key, value in list(extra.items()):
        if key == "route_tags" or value is None:
            continue
        extra[key] = html_lib.escape(str(value))
    data.update(extra)
    if theme_id == "travel_mag":
        # 水印优先用 LLM 提供的真实简称（2-6 字），否则从标题智能提取
        wm = str(data.get("watermark") or "").strip()
        wm = re.sub(r"\s+", "", wm)
        if not (2 <= len(wm) <= 6):
            wm = _watermark_from_title(data.get("title") or "")
        data["watermark"] = wm
        # meta_line 的标签部分转成 .tag 胶囊：`标签1 × 标签2｜日期` → tag spans + ｜日期
        meta_line = data.get("meta_line") or ""
        if "｜" in meta_line:
            tag_part, _, date_part = meta_line.partition("｜")
            tags_html = "".join(
                f'<span class="tag">{t.strip()}</span>'
                for t in re.split(r"×|x|X", tag_part)
                if t.strip()
            )
            if tags_html:
                data["meta_line"] = f"{tags_html}｜{date_part}"
        pills: list[str] = []
        days = str(data.get("days") or "").strip()
        countries = str(data.get("countries") or "").strip()
        duration = str(data.get("duration") or "").strip()
        distance = str(data.get("distance") or "").strip()
        cities = str(data.get("city_count") or "").strip()
        transport = str(data.get("transport") or "").strip()
        if days:
            pills.append(
                f'<span class="stat-pill"><span class="dot"></span>全程 <b>{days}</b> 天</span>'
            )
        if countries:
            country_count = len(
                [p for p in re.split(r"[×xX×,]", countries) if p.strip()]
            )
            pills.append(
                f'<span class="stat-pill"><span class="dot"></span><b>{country_count}</b> 国</span>'
            )
        if duration:
            pills.append(
                f'<span class="stat-pill"><span class="dot"></span>{duration}</span>'
            )
        if distance:
            pills.append(
                f'<span class="stat-pill"><span class="dot"></span>约 <b>{distance}</b> km</span>'
            )
        if cities:
            pills.append(
                f'<span class="stat-pill"><span class="dot"></span><b>{cities}</b> 座城市</span>'
            )
        if transport:
            pills.append(
                f'<span class="stat-pill"><span class="dot"></span>交通 <b>{transport}</b></span>'
            )
        data["stat_pills"] = "\n      ".join(pills)
    return template.format(**data)


_IMG_SRC_RE = re.compile(
    r'<img\b[^>]*?\bsrc=(["\'])(.*?)\1[^>]*>',
    re.IGNORECASE | re.DOTALL,
)

_PLACEHOLDER_RE = re.compile(
    r'<div class="photo-placeholder">(.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)


def _fetch_image_data(src: str) -> tuple[bytes, str] | None:
    """下载图片，返回 (data, content_type)；失败/非图片/超限返回 None。"""
    try:
        import base64
        import urllib.request

        request = urllib.request.Request(
            src,
            headers={"User-Agent": "Mozilla/5.0 (Divine PDF Renderer)"},
        )
        with urllib.request.urlopen(request, timeout=6) as response:
            data = response.read(2 * 1024 * 1024 + 1)  # 上限 2MB
            if len(data) > 2 * 1024 * 1024:
                return None
            ctype = response.headers.get("Content-Type", "") or ""
            if not ctype.startswith("image/"):
                return None
        return data, ctype
    except Exception:
        return None


def _image_data_uri(src: str) -> str | None:
    fetched = _fetch_image_data(src)
    if not fetched:
        return None
    import base64

    data, ctype = fetched
    return f"data:{ctype};base64,{base64.b64encode(data).decode('ascii')}"


def _keyword_to_image_url(keyword: str) -> str:
    """把景点关键词转成稳定的图片 URL。

    优先 Unsplash（若关键词本身是 unsplash photo 链接则直接用）；
    否则用 picsum.photos 的 seed 模式（按关键词生成固定图，无需 API key），
    seed 用 URL 编码的中文+英文关键词，保证同景点多次生成图片一致。
    """
    from urllib.parse import quote

    keyword = (keyword or "").strip()
    if keyword.startswith(("http://", "https://")):
        return keyword
    seed = quote(keyword or "travel", safe="")
    return f"https://picsum.photos/seed/{seed}/900/600"


def _ensure_placeholder_blocks(html_body: str) -> str:
    """LLM 有时会省略 photo-placeholder（即使提示词要求）。

    对每个 day-title，若其所在 page 内没有 photo-placeholder，
    在 day-title 闭合后自动插入一个渐变占位（含 photo-note），
    保证配图逻辑有占位可处理。
    """
    if 'class="day-title"' not in html_body:
        return html_body

    # 一次性收集所有 (day 标题, 插入位置)，从后往前插入避免位置漂移
    insertions: list[tuple[int, str]] = []
    for m in re.finditer(
        r'<h2[^>]*class="day-title"[^>]*>(.*?)</h2>',
        html_body,
        re.DOTALL,
    ):
        insert_at = m.end()
        # 当前 page 范围（到下一个 page 开头）：判断该页是否已有 placeholder
        page_end = html_body.find('<div class="page">', insert_at)
        if page_end == -1:
            page_end = len(html_body)
        if "photo-placeholder" in html_body[insert_at:page_end]:
            continue
        title = re.sub(r"<[^>]+>", "", m.group(1))
        title = html_lib.unescape(title).strip()
        title = re.sub(r"\s+", " ", title)
        placeholder = (
            '<div class="photo-placeholder">'
            f'<span class="photo-note">Photo · {title or "当日看点"}</span>'
            "</div>"
        )
        insertions.append((insert_at, "\n  " + placeholder))

    for insert_at, block in sorted(insertions, reverse=True):
        html_body = html_body[:insert_at] + block + html_body[insert_at:]
    return html_body


def _inline_placeholder_images(html_body: str, auto_fill: bool = True) -> str:
    """处理 photo-placeholder 的图片：

    1. 已有 <img>：下载外链转 base64 内嵌（成功 → PDF 离线可用；失败 → 移除 img）；
    2. 无 <img> 且 auto_fill=True（用户要求配图）：默认从 photo-note 提取关键词，
       生成图片 URL 下载内嵌（成功 → 有图；失败 → 保留渐变占位）。
       auto_fill=False（默认首轮）：保持渐变占位，不自动下载。
    CSS 无法检测 <img> 加载失败（坏链会渲染成白块盖住渐变），必须在渲染前处理。
    """
    # 先兜底：LLM 省略 placeholder 时自动插入（确保配图有占位可处理）
    html_body = _ensure_placeholder_blocks(html_body)
    if "photo-placeholder" not in html_body:
        return html_body

    def _inline_existing(match: re.Match[str]) -> str:
        tag = match.group(0)
        src = (match.group(2) or "").strip()
        if not src:
            return ""
        if src.startswith("data:") or src.startswith("file:"):
            return tag
        if not src.startswith(("http://", "https://")):
            # 本地相对路径：交给 WeasyPrint base_url 解析
            return tag
        uri = _image_data_uri(src)
        if not uri:
            return ""
        return re.sub(
            r'\bsrc=(["\'])(.*?)\1',
            f'src="{uri}"',
            tag,
            count=1,
            flags=re.IGNORECASE,
        )

    # 先处理已有 img（下载或移除）
    if "<img" in html_body:
        html_body = _IMG_SRC_RE.sub(_inline_existing, html_body)

    # 再给没有 img 的 placeholder 自动补图（仅用户要求配图时）
    if not auto_fill:
        return html_body

    def _fill_placeholder(match: re.Match[str]) -> str:
        inner = match.group(1)
        if "<img" in inner:
            return match.group(0)
        note = re.search(
            r'photo-note[^>]*>(.*?)<',
            inner,
            re.IGNORECASE | re.DOTALL,
        )
        keyword = note.group(1).strip() if note else ""
        # 去 HTML 实体与装饰符，保留景点关键词
        keyword = html_lib.unescape(keyword)
        keyword = re.sub(r"[·｜|×•—\-–\s]+", " ", keyword).strip()
        url = _keyword_to_image_url(keyword)
        uri = _image_data_uri(url)
        if not uri:
            return match.group(0)  # 下载失败：保留渐变占位
        return (
            '<div class="photo-placeholder">'
            f'<img src="{uri}" alt=""/>'
            f"{inner}</div>"
        )

    return _PLACEHOLDER_RE.sub(_fill_placeholder, html_body)


def build_travel_html_document(
    html_body: str,
    title: str,
    subtitle: str = "AI Divine 生成文档",
    cover_data: dict[str, Any] | None = None,
    include_cover: bool = True,
    overrides: dict[str, str] | None = None,
    theme: str = "travel",
    images: bool = False,
) -> str:
    css = load_theme_css(theme, overrides=overrides)
    cover_html = (
        build_cover_html(theme, html_lib.escape(title), subtitle, cover_data)
        if include_cover
        else ""
    )
    # 外链图片转 base64 内嵌（失败移除，保留渐变兜底）；
    # images=False 时不自动补图（photo 区域保持渐变占位）
    import logging
    _log = logging.getLogger("divine.pdf")
    _log.warning(
        "[placeholder-debug] images=%s day_title=%d placeholder=%d img=%d",
        images,
        html_body.count('class="day-title"'),
        html_body.count("photo-placeholder"),
        html_body.count("<img"),
    )
    html_body = _inline_placeholder_images(html_body, auto_fill=images)
    _log.warning(
        "[placeholder-debug] after: placeholder=%d img=%d base64=%d",
        html_body.count("photo-placeholder"),
        html_body.count("<img"),
        html_body.count("data:image"),
    )
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<style>{css}</style></head><body>"
        f"{cover_html}"
        "<div class=\"header\">"
        f"<span class=\"doc-title\">{html_lib.escape(title)}</span>"
        "</div>"
        f"{html_body}</body></html>"
    )
