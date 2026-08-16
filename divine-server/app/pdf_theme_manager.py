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

# 常用颜色名 → 基准色值（未收录的颜色名可走 derive_travel_palette 的 HSL 派生）
COLOR_NAMES: dict[str, str] = {
    "red": "#E74C3C",
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
    if key in TRAVEL_COLOR_PRESETS:
        overrides = dict(TRAVEL_COLOR_PRESETS[key])
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
    overrides.update(custom)
    overrides.pop("--primary", None)
    return overrides


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
        data["watermark"] = data.get("title", "")[:2] or "旅行"
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


def build_travel_html_document(
    html_body: str,
    title: str,
    subtitle: str = "AI Divine 生成文档",
    cover_data: dict[str, Any] | None = None,
    include_cover: bool = True,
    overrides: dict[str, str] | None = None,
    theme: str = "travel",
) -> str:
    css = load_theme_css(theme, overrides=overrides)
    cover_html = (
        build_cover_html(theme, html_lib.escape(title), subtitle, cover_data)
        if include_cover
        else ""
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
