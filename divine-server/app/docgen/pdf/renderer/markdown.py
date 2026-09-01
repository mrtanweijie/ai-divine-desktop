"""Markdown preprocessing and lightweight HTML/TOC conversion."""

from __future__ import annotations

import html as html_lib
import re

def _normalize(value: str, choices: tuple[str, ...], fallback: str) -> str:
    cleaned = (value or "").strip().lower()
    return cleaned if cleaned in choices else fallback

def _slugify(text: str) -> str:
    slug = re.sub(r"\s+", "-", text.strip().lower())
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "", slug, flags=re.UNICODE)
    return slug or "section"

_SVG_FENCE_RE = re.compile(
    r"```(?:svg|xml)\s*\n(.*?)```", re.IGNORECASE | re.DOTALL
)

_RAW_SVG_RE = re.compile(
    r"(?is)(?<!<div class=\"illustration\">)"
    r"(<svg(?![^>]*class=\"ico\")[^>]*>.*?</svg>)"
)

# ---------------------------------------------------------------------------
# 布局模块约定（GitHub Alert 风格 + 表格标记）
# 在 python-markdown 转换前把约定语法转成模块 HTML 块
# ---------------------------------------------------------------------------

_ALERT_START_RE = re.compile(r"^>\s*\[!([a-z-]+)\]\s*(.*)$", re.IGNORECASE)

_ALERT_TYPES = frozenset(
    {"note", "info", "warning", "success", "error", "quote", "conclusion", "bio"}
)

_QUOTE_BLOCK_RE = re.compile(r"(?m)^(?:>\s?.*\n?)+")

# 表格 + 标记行：每行以 | 开头（[^\n]* 限定单行，避免跨表格合并匹配）
_TABLE_MARK_RE = re.compile(
    r"(?m)((?:\|[^\n]*\|\s*\n){1,})\s*\{\:\s*\.([a-z-]+)\s*\}\s*$"
)

_TABLE_MODULES = frozenset(
    {"hero-stat", "compare", "timeline", "features", "metrics", "tags"}
)

_HL_VALUES = frozenset({"yes", "true", "1", "是", "高亮", "hl"})

# Callout 图标：文本字符（WeasyPrint 66 的 SVG 渲染不认 CSS stroke/currentColor，
# 内联 SVG 图标在 PDF 中会无描边不可见；字体字符渲染稳定且颜色跟随主题）。
_CALLOUT_ICONS = {
    "note": "ℹ",
    "info": "ℹ",
    "warning": "⚠",
    "success": "✓",
    "error": "✕",
}


def _parse_table_rows(block_text: str) -> list[list[str]]:
    """解析约定表格；跳过表头与分隔行（有分隔行时第一行视为表头）。"""
    rows: list[list[str]] = []
    has_separator = False
    for line in block_text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells and all(
            re.fullmatch(r":?-{2,}:?", cell or "-") for cell in cells
        ):
            has_separator = True
            continue
        if cells and all(not cell for cell in cells):
            continue
        rows.append(cells)
    if has_separator and rows:
        rows = rows[1:]  # 去掉表头行
    return rows


def _render_alert_block(kind: str, title: str, body: list[str]) -> str:
    esc = html_lib.escape
    if kind in ("note", "info", "warning", "success", "error"):
        icon = _CALLOUT_ICONS[kind]
        title_html = f'<div class="callout-title">{esc(title) or kind.capitalize()}</div>' if title else ""
        text = " ".join(esc(line) for line in body)
        return (
            f'<div class="callout-box {kind}"><div class="ci">{icon}</div>'
            f"<div>{title_html}<div class=\"callout-body\">{text}</div></div></div>"
        )
    if kind == "quote":
        attribution = ""
        quote_lines = []
        for line in body:
            if line.startswith(("—", "-", "——")):
                attribution = f'<div class="attribution">{esc(line.lstrip("-— "))}</div>'
            else:
                quote_lines.append(esc(line))
        title_html = f'<div class="module-label">{esc(title)}</div>' if title else ""
        return (
            '<div class="module pull-quote" data-emphasis="medium">'
            f"{title_html}<blockquote>"
            '<span class="quote-mark opening">"</span>'
            f"{' '.join(quote_lines) if quote_lines else '&nbsp;'}"
            '<span class="quote-mark closing">"</span>'
            f"</blockquote>{attribution}</div>"
        )
    if kind == "conclusion":
        return (
            '<div class="module conclusion-box">'
            f'<div class="conclusion-label">{esc(title) or "总结"}</div>'
            f'<div class="conclusion-text">{" ".join(esc(line) for line in body)}</div>'
            "</div>"
        )
    if kind == "bio":
        name, sep, role = title.partition("|")
        name = name.strip()
        role = role.strip()
        initials = esc(name[:2] or "?")
        return (
            '<div class="module bio-card">'
            f'<div class="bio-avatar">{initials}</div>'
            f"<div><div class=\"bio-name\">{esc(name)}</div>"
            f'<div class="bio-title">{esc(role)}</div></div>'
            f'<div class="bio-text">{" ".join(esc(line) for line in body)}</div>'
            "</div>"
        )
    return ""


_STAT_UNIT_RE = re.compile(r"^([\d.,]+)\s*(.*)$")


def _split_stat_unit(raw: str) -> tuple[str, str]:
    """把数值拆成 数字 + 单位（"12 项"→("12","项")、"92%"→("92","%")、"38h"→("38","h")）。"""
    text = (raw or "").strip()
    match = _STAT_UNIT_RE.match(text)
    if match and match.group(2):
        return match.group(1), match.group(2)
    return text, ""


def _render_table_module(kind: str, rows: list[list[str]]) -> str:
    esc = html_lib.escape
    if kind == "hero-stat":
        items = []
        for cells in rows[:4]:
            label = esc(cells[0]) if len(cells) > 0 else ""
            num, unit = _split_stat_unit(cells[1] if len(cells) > 1 else "")
            unit_html = f'<span class="stat-unit">{esc(unit)}</span>' if unit else ""
            value = f"{esc(num)}{unit_html}"
            trend = ""
            if len(cells) > 2 and cells[2].strip():
                raw = cells[2].strip()
                if raw.startswith("+"):
                    trend = f'<div class="stat-trend up">▲ {esc(raw[1:])}</div>'
                elif raw.startswith("-"):
                    trend = f'<div class="stat-trend down">▼ {esc(raw[1:])}</div>'
                else:
                    trend = f'<div class="stat-trend up">{esc(raw)}</div>'
            items.append(
                f'<div class="stat-item"><div class="stat-value">{value}</div>'
                f'<div class="stat-label">{label}</div>{trend}</div>'
            )
        cols = max(2, min(len(items), 4))
        return (
            '<div class="module hero-stat" data-emphasis="high">'
            f'<div class="stat-grid grid-{cols}">{"".join(items)}</div></div>'
        )
    if kind == "compare":
        left: list[str] = []
        right: list[str] = []
        for cells in rows:
            if len(cells) > 0:
                left.append(f"<li>{esc(cells[0])}</li>")
            if len(cells) > 1:
                right.append(f"<li>{esc(cells[1])}</li>")
        return (
            '<div class="module two-col-compare"><div class="compare-grid">'
            '<div class="compare-panel before"><div class="compare-header">'
            '<span class="compare-badge">Before</span></div>'
            f'<ul class="compare-list">{"".join(left)}</ul></div>'
            '<div class="compare-divider"><span class="divider-label">VS</span></div>'
            '<div class="compare-panel after"><div class="compare-header">'
            '<span class="compare-badge highlight">After</span></div>'
            f'<ul class="compare-list">{"".join(right)}</ul></div>'
            "</div></div>"
        )
    if kind == "timeline":
        nodes = []
        for cells in rows:
            date = esc(cells[0]) if len(cells) > 0 else ""
            event = esc(cells[1]) if len(cells) > 1 else ""
            detail = esc(cells[2]) if len(cells) > 2 else ""
            highlight = (
                len(cells) > 3
                and cells[3].strip().lower() in _HL_VALUES
            )
            hl_cls = " highlight" if highlight else ""
            detail_html = f'<div class="timeline-detail">{detail}</div>' if detail else ""
            nodes.append(
                f'<div class="timeline-node{hl_cls}"><div class="timeline-dot"></div>'
                f'<div class="timeline-date">{date}</div>'
                f'<div class="timeline-event">{event}</div>{detail_html}</div>'
            )
        return (
            '<div class="module timeline"><div class="timeline-track">'
            f'{"".join(nodes)}</div></div>'
        )
    if kind == "features":
        items = []
        for cells in rows[:4]:
            icon = esc(cells[0]) if len(cells) > 0 and cells[0].strip() else ""
            label = esc(cells[1]) if len(cells) > 1 else ""
            desc = esc(cells[2]) if len(cells) > 2 else ""
            icon_html = f'<div class="feature-icon">{icon}</div>' if icon else ""
            items.append(
                f'<div class="feature-item">{icon_html}'
                f'<div class="feature-label">{label}</div>'
                f'<div class="feature-desc">{desc}</div></div>'
            )
        # P0-4：按数据行数动态选择列数（2/3/4 列）
        cols = min(max(len(items), 2), 4)
        return (
            '<div class="module feature-grid">'
            f'<div class="feature-grid-container cols-{cols}">'
            f'{"".join(items)}</div></div>'
        )
    if kind == "metrics":
        items = []
        for cells in rows:
            label = esc(cells[0]) if len(cells) > 0 else ""
            value = esc(cells[1]) if len(cells) > 1 else ""
            percent = ""
            if len(cells) > 2:
                raw = re.sub(r"[^\d.]", "", cells[2])
                if raw:
                    percent = min(100, max(0, float(raw)))
            width = f" style=\"width:{percent:.0f}%\"" if percent != "" else ""
            pct_html = (
                f'<span class="metric-pct">{percent:.0f}%</span>'
                if percent != ""
                else ""
            )
            items.append(
                '<div class="metric-item">'
                f'<div class="metric-header"><span class="metric-label">{label}</span>'
                f'<span class="metric-value">{value}{pct_html}</span></div>'
                f'<div class="metric-bar"><div class="metric-fill"{width}></div></div>'
                "</div>"
            )
        return f'<div class="module metric-row">{"".join(items)}</div>'
    if kind == "tags":
        tags = []
        for cells in rows:
            text = esc(cells[0]) if len(cells) > 0 else ""
            hl = (
                len(cells) > 1
                and cells[1].strip().lower() in _HL_VALUES
            )
            cls = " tag hl" if hl else " tag"
            tags.append(f'<span class="{cls.strip()}">{text}</span>')
        return f'<div class="module tag-cloud"><div class="tags">{"".join(tags)}</div></div>'
    return ""


def _convert_alert_blocks(markdown: str) -> str:
    def replace(match: re.Match[str]) -> str:
        raw_lines = match.group(0).splitlines()
        first = raw_lines[0].strip()
        alert = _ALERT_START_RE.match(first)
        if not alert:
            return match.group(0)
        kind = alert.group(1).lower()
        if kind not in _ALERT_TYPES:
            return match.group(0)
        title = alert.group(2).strip()
        lines = [re.sub(r"^>\s?", "", line) for line in raw_lines]
        body = [line.strip() for line in lines[1:] if line.strip()]
        return _render_alert_block(kind, title, body)

    return _QUOTE_BLOCK_RE.sub(replace, markdown)


def _convert_marked_tables(markdown: str) -> str:
    def replace(match: re.Match[str]) -> str:
        table_text = match.group(1)
        kind = match.group(2).lower()
        if kind not in _TABLE_MODULES:
            return match.group(0)
        rows = _parse_table_rows(table_text)
        if not rows:
            return match.group(0)
        return _render_table_module(kind, rows)

    return _TABLE_MARK_RE.sub(replace, markdown)


def _convert_modules(markdown: str) -> str:
    """把模块约定的 markdown 转成模块 HTML（在 markdown 库转换前执行）。"""
    return _convert_marked_tables(_convert_alert_blocks(markdown))


def _prepare_markdown(markdown: str) -> str:
    """预处理：模块约定 → 模块 HTML；SVG 块移出代码围栏。

    Returns:
        转换后的 markdown（含内嵌 HTML 块），供 WeasyPrint 渲染。
    """
    prepared = _convert_modules(markdown)

    def wrap_fenced(match: re.Match[str]) -> str:
        svg = re.search(
            r"(<svg[^>]*>.*?</svg>)", match.group(1), re.IGNORECASE | re.DOTALL
        )
        if not svg:
            return match.group(0)
        return f"<div class=\"illustration\">{svg.group(1)}</div>"

    prepared = _SVG_FENCE_RE.sub(wrap_fenced, prepared)
    prepared = _RAW_SVG_RE.sub(
        lambda match: (
            f"<div class=\"illustration\">{match.group(1)}</div>"
        ),
        prepared,
    )
    return prepared

def _markdown_to_html(markdown: str) -> str:
    """Lightweight Markdown-to-HTML converter for offline PDF rendering."""
    lines = markdown.splitlines()
    parts: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    in_code = False
    code_lines: list[str] = []
    heading_ids: dict[str, int] = {}

    def flush_paragraph() -> None:
        if not paragraph:
            return
        parts.append(f"<p>{' '.join(paragraph)}</p>")
        paragraph.clear()

    def flush_list() -> None:
        if not list_items:
            return
        items = "".join(f"<li>{item}</li>" for item in list_items)
        parts.append(f"<ul>{items}</ul>")
        list_items.clear()

    def flush_block() -> None:
        flush_paragraph()
        flush_list()

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if in_code:
            if stripped.startswith("```"):
                code = html_lib.escape("\n".join(code_lines), quote=False)
                parts.append(f"<pre><code>{code}</code></pre>")
                code_lines = []
                in_code = False
            else:
                code_lines.append(line)
            continue
        if stripped.startswith("```"):
            flush_block()
            in_code = True
            code_lines = []
            continue
        if stripped.startswith("#"):
            flush_block()
            level = min(len(stripped) - len(stripped.lstrip("#")), 4)
            text = stripped.lstrip("#").strip()
            escaped = html_lib.escape(text)
            base = _slugify(text)
            count = heading_ids.get(base, 0) + 1
            heading_ids[base] = count
            suffix = f"-{count}" if count > 1 else ""
            parts.append(f"<h{level} id=\"{base}{suffix}\">{escaped}</h{level}>")
            continue
        if re.match(r"^[-*]\s+", stripped):
            flush_paragraph()
            list_items.append(html_lib.escape(re.sub(r"^[-*]\s+", "", stripped)))
            continue
        if stripped in ("---", "***", "___"):
            flush_block()
            parts.append("<hr/>")
            continue
        if stripped.startswith(">"):
            flush_block()
            quote = html_lib.escape(re.sub(r"^>\s?", "", stripped))
            parts.append(f"<blockquote>{quote}</blockquote>")
            continue
        if not stripped:
            flush_block()
            continue
        flush_list()
        paragraph.append(html_lib.escape(line))

    if in_code:
        code = html_lib.escape("\n".join(code_lines), quote=False)
        parts.append(f"<pre><code>{code}</code></pre>")
    flush_block()
    return "\n".join(parts)

def _build_toc(markdown: str) -> str:
    """生成目录 HTML（toc-item 结构：编号 + 标题链接 + 自动页码）。

    页码由 CSS `target-counter(attr(href), page)` 自动生成（WeasyPrint 支持），
    无需 JS。锚点规则与 _add_heading_ids 一致：第一个标题无后缀，
    重复标题从 -1 递增。结构：.toc > .toc-item.toc-level-N > .num + a.title
    """
    items: list[tuple[int, str, str]] = []
    heading_ids: dict[str, int] = {}
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("##"):
            continue
        level = min(len(stripped) - len(stripped.lstrip("#")), 4)
        if level < 2 or level > 3:
            continue
        text = stripped.lstrip("#").strip()
        base = _slugify(text)
        count = heading_ids.get(base, 0) + 1
        heading_ids[base] = count
        suffix = "" if count == 1 else f"-{count - 1}"
        items.append((level, text, f"{base}{suffix}"))
    if not items:
        return ""
    body = ['<div class="toc"><h2>目录</h2>']
    for index, (level, text, anchor) in enumerate(items, start=1):
        body.append(
            f'<div class="toc-item toc-level-{level}">'
            f'<span class="num">{index:02d}</span>'
            f'<a class="title" href="#{html_lib.escape(anchor)}">'
            f"{html_lib.escape(text)}</a></div>"
        )
    body.append("</div>")
    return "\n".join(body)


def _add_heading_ids(html: str) -> str:
    """给 h2/h3 注入 id（锚点规则与 _build_toc 一致）。

    供 WeasyPrint 的 target-counter 目录页码与锚点跳转使用；
    在 markdown 库转换后调用。
    """
    used: dict[str, int] = {}

    def replace(match: re.Match[str]) -> str:
        level = match.group(1)
        inner = match.group(2)
        text = re.sub(r"<[^>]+>", "", inner)
        base = _slugify(text)
        count = used.get(base, 0) + 1
        used[base] = count
        suffix = "" if count == 1 else f"-{count - 1}"
        return f'<h{level} id="{base}{suffix}">{inner}</h{level}>'

    return re.sub(r"<h([23])>(.*?)</h\1>", replace, html)
