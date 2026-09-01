from __future__ import annotations

import html as html_lib
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
)

FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
FONT_NAME = "ArialUnicode"


def _register_font() -> None:
    global FONT_NAME
    if FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return
    try:
        pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_PATH))
        pdfmetrics.registerFontFamily(
            FONT_NAME,
            normal=FONT_NAME,
            bold=FONT_NAME,
            italic=FONT_NAME,
            boldItalic=FONT_NAME,
        )
    except Exception:
        FONT_NAME = "Helvetica"


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle(
        "body",
        fontName=FONT_NAME,
        fontSize=10.5,
        leading=15,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#1B1F24"),
        spaceAfter=6,
    )
    return {
        "body": base,
        "title": ParagraphStyle(
            "title",
            parent=base,
            fontSize=20,
            leading=26,
            spaceAfter=14,
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
    }


def _escape(text: str) -> str:
    return html_lib.escape(text, quote=False)


def render_markdown_pdf(text: str, title: str = "对话导出") -> bytes:
    _register_font()
    styles = _styles()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=48,
        rightMargin=48,
        topMargin=48,
        bottomMargin=48,
        title=title,
    )
    story = [Paragraph(_escape(title), styles["title"])]
    in_code = False
    code_lines: list[str] = []

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                story.append(
                    Preformatted(
                        "\n".join(code_lines),
                        styles["code"],
                    )
                )
                code_lines = []
            in_code = not in_code
            continue
        if in_code:
            code_lines.append(line)
            continue
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            heading = stripped.lstrip("#").strip()
            key = f"h{min(3, level)}"
            story.append(Paragraph(_escape(heading), styles[key]))
            continue
        if stripped in ("---", "***", "___"):
            story.append(
                HRFlowable(
                    width="100%",
                    thickness=0.8,
                    color=colors.HexColor("#D6DAE0"),
                    spaceBefore=4,
                    spaceAfter=6,
                )
            )
            continue
        if not stripped:
            story.append(Spacer(1, 4))
            continue
        if stripped.startswith(("- ", "* ")):
            story.append(
                Paragraph("• " + _escape(stripped[2:]), styles["bullet"])
            )
            continue
        story.append(Paragraph(_escape(line), styles["body"]))

    if code_lines:
        story.append(Preformatted("\n".join(code_lines), styles["code"]))
    doc.build(story)
    return buffer.getvalue()


def export_chat_pdf(text: str, output: Path) -> None:
    output.write_bytes(render_markdown_pdf(text))
