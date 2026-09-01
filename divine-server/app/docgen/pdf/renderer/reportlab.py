"""ReportLab fallback renderer for offline PDF generation."""

from __future__ import annotations

import base64
import html as html_lib
from io import BytesIO
from pathlib import Path
from typing import Any

from .markdown import _prepare_markdown

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

    from .. import export

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
        from ..export import render_markdown_pdf

        output.write_bytes(render_markdown_pdf(markdown, title))
