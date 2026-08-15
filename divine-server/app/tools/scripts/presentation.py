import json
import re
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.tools.scripts.file_utils import unique_output_path  # noqa: E402
from app import ppt_themes  # noqa: E402

BG_DARK = RGBColor(0x10, 0x13, 0x1A)
BG_LIGHT = RGBColor(0xFF, 0xFF, 0xFF)
ACCENT = RGBColor(0x4F, 0x8F, 0xFF)
TEXT_DARK = RGBColor(0x1A, 0x1D, 0x24)
TEXT_MUTED = RGBColor(0x6B, 0x72, 0x80)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT_NAME = "PingFang SC"

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


def safe_name(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "_", name).strip("._")
    if not cleaned:
        cleaned = fallback
    if not cleaned.endswith(".pptx"):
        cleaned += ".pptx"
    return cleaned


def _solid(shape, color):
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    shape.shadow.inherit = False


def _set_run(run, size, color, bold=False):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = FONT_NAME
    r_pr = run._r.get_or_add_rPr()
    ea = r_pr.find(qn("a:ea"))
    if ea is None:
        ea = r_pr.makeelement(qn("a:ea"), {})
        r_pr.append(ea)
    ea.set("typeface", FONT_NAME)


def _add_title_slide(prs, title, count):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, SLIDE_H)
    _solid(bg, BG_DARK)

    accent = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0.95), Inches(2.62), Inches(0.14), Inches(1.25)
    )
    _solid(accent, ACCENT)

    title_box = slide.shapes.add_textbox(
        Inches(1.35), Inches(2.55), Inches(10.6), Inches(1.6)
    )
    tf = title_box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = title
    _set_run(p.runs[0], 46, WHITE, bold=True)

    meta = slide.shapes.add_textbox(
        Inches(1.35), Inches(4.25), Inches(10), Inches(0.6)
    )
    tf = meta.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = f"AI Divine  ·  {count} 页"
    _set_run(p.runs[0], 18, RGBColor(0x9A, 0xA3, 0xB2))

    footer = slide.shapes.add_textbox(
        Inches(1.35), Inches(6.75), Inches(10), Inches(0.4)
    )
    tf = footer.text_frame
    p = tf.paragraphs[0]
    p.text = "AI Divine"
    _set_run(p.runs[0], 13, RGBColor(0x6B, 0x72, 0x80))


def _add_content_slide(prs, index, heading, body):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, SLIDE_H)
    _solid(bg, BG_LIGHT)

    top = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, Inches(0.09)
    )
    _solid(top, ACCENT)

    label = slide.shapes.add_textbox(
        Inches(0.95), Inches(0.55), Inches(8), Inches(0.4)
    )
    tf = label.text_frame
    p = tf.paragraphs[0]
    p.text = f"{index:02d}"
    _set_run(p.runs[0], 15, ACCENT, bold=True)

    title_box = slide.shapes.add_textbox(
        Inches(0.95), Inches(1.0), Inches(11.4), Inches(1.0)
    )
    tf = title_box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = heading
    _set_run(p.runs[0], 34, TEXT_DARK, bold=True)

    body_box = slide.shapes.add_textbox(
        Inches(0.95), Inches(2.25), Inches(11.4), Inches(4.4)
    )
    tf = body_box.text_frame
    tf.word_wrap = True
    tf.clear()
    for i, raw in enumerate(body.splitlines()):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        level = 1 if raw.startswith(("  ", "\t", "- ", "• ")) else 0
        text = raw.lstrip("-•· \t")
        p.text = f"{'• ' if level == 0 else '– '}{text}"
        _set_run(p.runs[0], 22 if level == 0 else 18, TEXT_DARK, bold=(level == 0))
        p.space_after = Pt(12)
        p.line_spacing = 1.25

    footer = slide.shapes.add_textbox(
        Inches(0.95), Inches(6.85), Inches(11.4), Inches(0.35)
    )
    tf = footer.text_frame
    p = tf.paragraphs[0]
    p.text = heading
    p.alignment = PP_ALIGN.RIGHT
    _set_run(p.runs[0], 11, TEXT_MUTED)


def _slide_heading(item: object) -> str:
    if isinstance(item, dict):
        return str(item.get("heading") or item.get("title") or "无标题")
    return "无标题"


def _slide_body(item: object) -> str:
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return ""
    points = item.get("points") or item.get("bullets") or item.get("list")
    if isinstance(points, list):
        lines = []
        for point in points:
            text = str(point).strip()
            if text and not text.startswith(("-", "•", "–")):
                text = f"- {text}"
            lines.append(text)
        return "\n".join(lines)
    return str(
        item.get("body")
        or item.get("content")
        or item.get("text")
        or ""
    )


def _is_cover_slide(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    return bool(
        item.get("subtitle")
        and not item.get("points")
        and not item.get("bullets")
        and not item.get("list")
        and not item.get("body")
        and not item.get("content")
        and not item.get("text")
    )


def _slide_items(item: object) -> list[str]:
    if isinstance(item, str):
        return [line for line in item.splitlines() if line.strip()]
    if not isinstance(item, dict):
        return []
    points = (
        item.get("points")
        or item.get("bullets")
        or item.get("list")
        or item.get("items")
        or item.get("columns")
    )
    if isinstance(points, list):
        return [
            str(point.get("title") or point.get("content") or point)
            if isinstance(point, dict)
            else str(point)
            for point in points
        ]
    body = _slide_body(item)
    return [line for line in body.splitlines() if line.strip()]


def _slide_layout(item: object) -> str:
    if isinstance(item, dict):
        layout = str(item.get("layout") or "").lower()
        if layout in ("cards", "timeline", "columns", "default"):
            return layout
    heading = _slide_heading(item).lower()
    if any(
        word in heading
        for word in ("时间线", "timeline", "路线", "roadmap", "阶段")
    ):
        return "timeline"
    items = _slide_items(item)
    if len(items) >= 5:
        return "cards"
    if 0 < len(items) <= 3:
        return "columns"
    return "default"


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"])
    output_root = Path(data.get("output_dir") or workspace)
    params = data.get("params") or {}
    title = params.get("title") or "未命名演示文稿"
    slides = params.get("slides") or []
    theme = str(params.get("theme") or params.get("style") or "universal").strip()
    output_dir = output_root / "presentations"
    raw_path = str(params.get("path") or "").strip()
    if raw_path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = workspace / candidate
        output_dir = candidate.resolve()
        try:
            output_dir.relative_to(workspace.resolve())
        except ValueError:
            print(
                json.dumps(
                    {"success": False, "message": f"保存路径越界: {output_dir}"},
                    ensure_ascii=False,
                )
            )
            return
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = unique_output_path(output_dir, title, "演示文稿", ".pptx")

    prs = Presentation()
    prs.slide_width = ppt_themes.SLIDE_W
    prs.slide_height = ppt_themes.SLIDE_H
    subtitle = ""
    slide_items = slides
    if slides and _is_cover_slide(slides[0]):
        subtitle = str(slides[0].get("subtitle") or "")
        slide_items = slides[1:]
    ppt_themes.add_title_slide(
        prs,
        title,
        len(slide_items),
        theme,
        subtitle=subtitle,
    )
    for index, item in enumerate(slide_items, 1):
        heading = _slide_heading(item)
        body = _slide_body(item)
        layout = _slide_layout(item)
        if layout == "cards":
            ppt_themes.add_cards_slide(
                prs, index, heading, _slide_items(item), theme
            )
        elif layout == "timeline":
            ppt_themes.add_timeline_slide(
                prs, index, heading, _slide_items(item), theme
            )
        elif layout == "columns":
            ppt_themes.add_columns_slide(
                prs, index, heading, _slide_items(item), theme
            )
        else:
            ppt_themes.add_content_slide(
                prs, index, heading, body, theme
            )
    prs.save(output_path)
    print(
        json.dumps(
            {
                "success": True,
                "message": "PPT 生成完成",
                "file_name": output_path.name,
                "filepath": str(output_path),
                "data": {"theme": theme},
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
