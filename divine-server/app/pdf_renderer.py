from __future__ import annotations

import base64
import contextlib
import html as html_lib
import importlib.util
import io
import logging
import re
from io import BytesIO
from pathlib import Path
from string import Template
from typing import Any

STYLE_KEYS = ("modern", "academic", "corporate", "minimal", "playful")
COLOR_KEYS = ("blue", "green", "warm", "monochrome", "purple")
PAPER_KEYS = ("a4", "letter", "legal")
_WEASYPRINT_OK: bool | None = None
logger = logging.getLogger("divine.pdf")

COLOR_MAP = {
    "blue": {"accent": "#2563eb", "light": "#eaf1fe"},
    "green": {"accent": "#15803d", "light": "#ecfdf3"},
    "warm": {"accent": "#c2570a", "light": "#fff4e5"},
    "monochrome": {"accent": "#111827", "light": "#f3f4f6"},
    "purple": {"accent": "#6d28d9", "light": "#f3e8ff"},
}

_STYLE_FONT = {
    "academic": '"Songti SC", "STSong", "Noto Serif CJK SC", serif',
    "playful": '"PingFang SC", "Microsoft YaHei", sans-serif',
    "corporate": '"PingFang SC", "Microsoft YaHei", sans-serif',
    "minimal": '"PingFang SC", "Microsoft YaHei", sans-serif',
    "modern": '"Noto Sans SC", "Source Han Sans CN", "PingFang SC", sans-serif',
}

_PAGE_CSS = Template(
    """
@page {
  size: $paper;
  margin: 2.2cm 2cm 2.5cm 2cm;
  @top-center {
    content: element(header);
    border-bottom: 0.5pt solid #e0e0e0;
    padding-bottom: 4pt;
  }
  @bottom-center {
    content: counter(page) " / " counter(pages);
    font-size: 8.5pt;
    color: #999;
    font-family: $font_family;
  }
}
body {
  font-family: $font_family;
  font-size: 10.5pt;
  line-height: 1.85;
  color: #2c2c2c;
}
h1 {
  font-size: 24pt;
  font-weight: 700;
  color: #1a1a2e;
  margin-top: 0;
  margin-bottom: 0.4em;
  line-height: 1.3;
  letter-spacing: -0.02em;
}
h2 {
  font-size: 16pt;
  font-weight: 600;
  color: $accent;
  margin-top: 2em;
  margin-bottom: 0.6em;
  padding-left: 0.6em;
  border-left: 4pt solid $accent;
  line-height: 1.4;
  page-break-after: avoid;
}
h3 {
  font-size: 13pt;
  font-weight: 600;
  color: #333;
  margin-top: 1.5em;
  margin-bottom: 0.4em;
  page-break-after: avoid;
}
h4 {
  font-size: 11pt;
  font-weight: 600;
  color: #555;
  margin-top: 1.2em;
}
p {
  margin: 0.6em 0;
  orphans: 2;
  widows: 2;
}
ul, ol {
  margin: 0.6em 0;
  padding-left: 1.4em;
}
li {
  margin: 0.35em 0;
  padding-left: 0.2em;
}
li::marker {
  color: $accent;
  font-weight: 600;
}
.illustration,
figure {
  text-align: center;
  margin: 1.8em auto;
  page-break-inside: avoid;
  page-break-after: avoid;
}
.illustration img,
figure img,
.illustration svg {
  max-width: 82%;
  height: auto;
  border-radius: 6px;
  box-shadow: 0 3px 14px rgba(0, 0, 0, 0.10);
}
figcaption,
.illustration .caption {
  font-size: 8.5pt;
  color: #888;
  margin-top: 0.5em;
  font-style: italic;
}
pre {
  background: #f6f8fa;
  border: 1pt solid #e1e4e8;
  border-radius: 6px;
  padding: 1em 1.2em;
  margin: 1.2em 0;
  font-size: 9pt;
  line-height: 1.55;
  overflow-x: auto;
  page-break-inside: avoid;
}
code {
  font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
  font-size: 8.5pt;
  background: #f0f2f5;
  padding: 1pt 4pt;
  border-radius: 3pt;
}
pre code {
  background: none;
  padding: 0;
}
blockquote {
  border-left: 3pt solid $accent;
  background: $light;
  margin: 1.2em 0;
  padding: 0.8em 1.2em;
  border-radius: 0 6px 6px 0;
  color: #444;
  font-style: italic;
  page-break-inside: avoid;
}
table {
  width: 100%;
  border-collapse: collapse;
  margin: 1.5em 0;
  font-size: 9.5pt;
  page-break-inside: auto;
}
thead {
  background: $accent;
  color: white;
}
th, td {
  padding: 0.5em 0.8em;
  border: 0.5pt solid #ddd;
  text-align: left;
}
tbody tr:nth-child(even) {
  background: #f9fafb;
}
a {
  color: $accent;
  text-decoration: none;
  border-bottom: 0.5pt dotted $accent;
}
.cover {
  page-break-after: always;
  text-align: center;
  padding-top: 28vh;
}
.cover h1 {
  font-size: 32pt;
  letter-spacing: -0.03em;
}
.cover .subtitle {
  font-size: 14pt;
  color: #666;
  margin-top: 0.8em;
  font-weight: 300;
}
.cover .meta {
  margin-top: 2.5em;
  font-size: 9.5pt;
  color: #aaa;
}
.running-header {
  position: running(header);
  font-size: 8.5pt;
  color: #888;
}
.resource-card {
  border: 1pt solid #e0e0e0;
  border-radius: 6px;
  padding: 0.7em 1em;
  margin: 0.8em 0;
  background: #fafbfc;
  page-break-inside: avoid;
}
.resource-card .tag {
  display: inline-block;
  font-size: 7.5pt;
  font-weight: 600;
  padding: 1pt 6pt;
  border-radius: 3pt;
  background: $light;
  color: $accent;
  margin-right: 0.5em;
}
h1, h2, h3, h4 {
  orphans: 2;
  widows: 2;
}
"""
)


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


def _weasyprint_available() -> bool:
    global _WEASYPRINT_OK
    if _WEASYPRINT_OK is not None:
        return _WEASYPRINT_OK
    if importlib.util.find_spec("weasyprint") is None:
        _WEASYPRINT_OK = False
        return False
    # cffi may resolve system libraries through the process environment even
    # when common paths cannot be found, so always attempt the import once.
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        try:
            import weasyprint  # noqa: F401

            _WEASYPRINT_OK = True
        except Exception:
            _WEASYPRINT_OK = False
    return _WEASYPRINT_OK


def _render_with_weasyprint(
    markdown: str,
    output: Path,
    title: str,
    style: str,
    color_scheme: str,
    paper_size: str,
    cover: bool,
    toc: bool,
    base_dir: Path | None = None,
    theme: str = "universal",
) -> None:
    from weasyprint import HTML

    import markdown as markdown_lib

    from .pdf_theme_manager import build_cover_html, load_theme_css

    css = load_theme_css(theme, paper_size=paper_size)
    prepared = _prepare_markdown(markdown)
    body = markdown_lib.markdown(
        prepared,
        extensions=["extra", "tables", "fenced_code", "sane_lists"],
    )
    cover_html = ""
    if cover:
        cover_html = build_cover_html(
            theme,
            html_lib.escape(title),
            "AI Divine 生成文档",
        )
    toc_html = _build_toc(markdown) if toc else ""
    document = (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<style>{css}</style></head><body>"
        "<div class=\"header\">"
        f"<span class=\"doc-title\">{html_lib.escape(title)}</span>"
        "</div>"
        f"{cover_html}{toc_html}{body}</body></html>"
    )
    kwargs: dict[str, Any] = {"string": document}
    if base_dir is not None:
        kwargs["base_url"] = str(base_dir)
    HTML(**kwargs).write_pdf(str(output), presentational_hints=True)


def _rasterize_svg(svg_text: str) -> tuple[BytesIO, float, float]:
    from resvg_py import svg_to_bytes

    from PIL import Image as PILImage

    png_bytes = svg_to_bytes(svg_string=svg_text)
    stream = BytesIO(png_bytes)
    with PILImage.open(stream) as image:
        width, height = image.size
    max_width = 440.0
    scale = min(1.0, max_width / max(float(width), 1))
    return BytesIO(png_bytes), width * scale, height * scale


def _image_from_src(
    src: str | None,
    base_dir: Path | None = None,
):
    from reportlab.platypus import Image

    from PIL import Image as PILImage

    if not src:
        return None
    try:
        if src.startswith("data:"):
            data = base64.b64decode(src.split(",", 1)[1])
            if src.startswith("data:image/svg"):
                stream, width, height = _rasterize_svg(data.decode("utf-8"))
                return Image(stream, width=width, height=height)
        else:
            path = Path(src)
            if not path.is_absolute() and base_dir is not None:
                path = Path(base_dir) / path
            if not path.is_file():
                return None
            if path.suffix.lower() == ".svg":
                stream, width, height = _rasterize_svg(
                    path.read_text(encoding="utf-8")
                )
                return Image(stream, width=width, height=height)
            data = path.read_bytes()
        with PILImage.open(BytesIO(data)) as image:
            width, height = image.size
    except Exception:
        return None
    max_width = 440.0
    scale = min(1.0, max_width / max(float(width), 1))
    return Image(BytesIO(data), width=width * scale, height=height * scale)


def _inline_reportlab(node: Any) -> str:
    from bs4 import NavigableString

    if isinstance(node, NavigableString):
        return html_lib.escape(str(node), quote=False)
    if not getattr(node, "name", None):
        return ""
    name = node.name.lower()
    children = "".join(_inline_reportlab(child) for child in node.children)
    if name in ("b", "strong"):
        return f"<b>{children}</b>"
    if name in ("i", "em"):
        return f"<i>{children}</i>"
    if name == "code":
        return f'<font face="Courier">{children}</font>'
    if name == "br":
        return "<br/>"
    if name in ("a", "span", "p", "div", "td", "th", "li"):
        return children
    return children


def _reportlab_styles(font_name: str) -> dict[str, Any]:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import ParagraphStyle

    base = ParagraphStyle(
        "body",
        fontName=font_name,
        fontSize=10.5,
        leading=15.5,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#1B1F24"),
        spaceAfter=6,
    )
    return {
        "body": base,
        "cell": ParagraphStyle(
            "cell", parent=base, fontSize=9.5, leading=13
        ),
        "title": ParagraphStyle(
            "title", parent=base, fontSize=20, leading=26, spaceAfter=14
        ),
        "h1": ParagraphStyle(
            "h1", parent=base, fontSize=16, leading=21, spaceBefore=10
        ),
        "h2": ParagraphStyle(
            "h2", parent=base, fontSize=14, leading=19, spaceBefore=8
        ),
        "h3": ParagraphStyle(
            "h3", parent=base, fontSize=12.5, leading=17, spaceBefore=6
        ),
        "code": ParagraphStyle(
            "code",
            parent=base,
            fontName="Courier",
            fontSize=8.5,
            leading=11,
            backColor=colors.HexColor("#F4F6F8"),
            borderPadding=6,
            spaceAfter=8,
        ),
        "bullet": ParagraphStyle("bullet", parent=base, leftIndent=14),
        "quote": ParagraphStyle(
            "quote",
            parent=base,
            leftIndent=12,
            textColor=colors.HexColor("#5B6472"),
            borderPadding=6,
        ),
    }


def _table_flowable(table: Any, styles: dict[str, Any]):
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, Table, TableStyle

    rows = []
    for row in table.find_all("tr", recursive=False):
        cells = []
        for cell in row.find_all(["td", "th"], recursive=False):
            cells.append(
                Paragraph(_inline_reportlab(cell), styles["cell"])
            )
        if cells:
            rows.append(cells)
    if not rows:
        return None
    flowable = Table(rows)
    flowable.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D6DAE0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF1F4")),
            ]
        )
    )
    return flowable


def _walk_story(
    node: Any,
    styles: dict[str, Any],
    story: list[Any],
    base_dir: Path | None = None,
) -> None:
    from reportlab.platypus import (
        HRFlowable,
        Image,
        Paragraph,
        Preformatted,
        Spacer,
    )

    if not getattr(node, "name", None):
        return
    name = node.name.lower()
    if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = min(int(name[1]), 3)
        story.append(
            Paragraph(
                _inline_reportlab(node),
                styles[f"h{level}"],
            )
        )
        return
    if name == "p":
        if not node.find(["img", "svg"]):
            story.append(Paragraph(_inline_reportlab(node), styles["body"]))
            return
        buffer: list[str] = []

        def flush_buffer() -> None:
            if buffer:
                story.append(Paragraph("".join(buffer), styles["body"]))
                buffer.clear()

        for child in node.children:
            if getattr(child, "name", None) in ("img", "svg"):
                flush_buffer()
                _walk_story(child, styles, story, base_dir)
            else:
                buffer.append(_inline_reportlab(child))
        flush_buffer()
        return
    if name in ("ul", "ol"):
        for item in node.find_all("li", recursive=False):
            story.append(
                Paragraph(
                    "• " + _inline_reportlab(item),
                    styles["bullet"],
                )
            )
        return
    if name == "pre":
        story.append(Preformatted(node.get_text(), styles["code"]))
        return
    if name == "blockquote":
        story.append(Paragraph(_inline_reportlab(node), styles["quote"]))
        return
    if name == "hr":
        story.append(HRFlowable(width="100%", thickness=0.8))
        return
    if name == "table":
        table = _table_flowable(node, styles)
        if table:
            story.append(table)
        return
    if name == "img":
        image = _image_from_src(node.get("src"), base_dir)
        if image:
            story.append(image)
        return
    if name == "svg":
        stream, width, height = _rasterize_svg(str(node))
        story.append(Image(stream, width=width, height=height))
        return
    if name == "div":
        for child in node.find_all(recursive=False):
            _walk_story(child, styles, story, base_dir)
        return
    if name == "figure":
        for child in node.find_all(recursive=False):
            _walk_story(child, styles, story, base_dir)
        return
    if name == "br":
        story.append(Spacer(1, 4))
        return
    for child in node.find_all(recursive=False):
        _walk_story(child, styles, story, base_dir)


def _render_rich_reportlab(
    markdown: str,
    output: Path,
    title: str,
    base_dir: Path | None = None,
) -> None:
    import markdown as markdown_lib
    from bs4 import BeautifulSoup
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import Paragraph, SimpleDocTemplate

    from . import pdf_export

    pdf_export._register_font()
    styles = _reportlab_styles(pdf_export.FONT_NAME)
    prepared = _prepare_markdown(markdown)
    html_doc = markdown_lib.markdown(
        prepared,
        extensions=["extra", "tables", "fenced_code", "sane_lists"],
    )
    soup = BeautifulSoup(html_doc, "html.parser")
    story: list[Any] = [
        Paragraph(html_lib.escape(title), styles["title"]),
    ]
    root = soup.body or soup
    for child in root.find_all(recursive=False):
        _walk_story(child, styles, story, base_dir)
    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=48,
        rightMargin=48,
        topMargin=48,
        bottomMargin=48,
        title=title,
    )
    doc.build(story)


def _render_with_reportlab(
    markdown: str,
    output: Path,
    title: str,
    base_dir: Path | None = None,
    theme: str = "universal",
) -> None:
    try:
        _render_rich_reportlab(markdown, output, title, base_dir)
    except Exception:
        from .pdf_export import render_markdown_pdf

        output.write_bytes(render_markdown_pdf(markdown, title))


def render_markdown_to_pdf(
    markdown: str,
    output: Path,
    title: str = "PDF文档",
    style: str = "modern",
    color_scheme: str = "blue",
    paper_size: str = "A4",
    cover: bool = False,
    toc: bool = False,
    base_dir: Path | None = None,
    theme: str = "universal",
) -> dict[str, Any]:
    normalized_style = _normalize(style, STYLE_KEYS, "modern")
    normalized_color = _normalize(color_scheme, COLOR_KEYS, "blue")
    normalized_paper = _normalize(paper_size, PAPER_KEYS, "a4")
    if _weasyprint_available():
        try:
            _render_with_weasyprint(
                markdown,
                output,
                title,
                normalized_style,
                normalized_color,
                normalized_paper,
                cover,
                toc,
                base_dir,
                theme,
            )
            renderer = "weasyprint"
            return {
                "title": title,
                "style": normalized_style,
                "color_scheme": normalized_color,
                "paper_size": normalized_paper,
                "renderer": renderer,
            }
        except Exception:
            logger.warning(
                "weasyprint render failed, falling back to reportlab",
                exc_info=True,
            )
            pass
    _render_with_reportlab(markdown, output, title, base_dir, theme)
    renderer = "reportlab"
    return {
        "title": title,
        "style": normalized_style,
        "color_scheme": normalized_color,
        "paper_size": normalized_paper,
        "renderer": renderer,
    }
