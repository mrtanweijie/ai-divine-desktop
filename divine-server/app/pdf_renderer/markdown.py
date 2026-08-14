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
    r"(?is)(?<!<div class=\"illustration\">)(<svg[^>]*>.*?</svg>)"
)

def _prepare_markdown(markdown: str) -> str:
    """Lift SVG blocks out of code fences so renderers treat them as images."""

    def wrap_fenced(match: re.Match[str]) -> str:
        svg = re.search(
            r"(<svg[^>]*>.*?</svg>)", match.group(1), re.IGNORECASE | re.DOTALL
        )
        if not svg:
            return match.group(0)
        return f"<div class=\"illustration\">{svg.group(1)}</div>"

    prepared = _SVG_FENCE_RE.sub(wrap_fenced, markdown)
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
        suffix = f"-{count}" if count > 1 else ""
        items.append((level, text, f"{base}{suffix}"))
    if not items:
        return ""
    body = ["<div class=\"toc\"><h1>目录</h1><ul>"]
    for level, text, anchor in items:
        pad = "style=\"margin-left: 1em;\"" if level == 3 else ""
        body.append(
            f"<li {pad}><a href=\"#{html_lib.escape(anchor)}\">"
            f"{html_lib.escape(text)}</a></li>"
        )
    body.append("</ul></div>")
    return "\n".join(body)
