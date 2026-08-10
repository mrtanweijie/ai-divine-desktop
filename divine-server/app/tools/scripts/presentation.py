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


def main() -> None:
    data = json.load(sys.stdin)
    workspace = Path(data["workspace"])
    output_root = Path(data.get("output_dir") or workspace)
    params = data.get("params") or {}
    title = params.get("title") or "未命名演示文稿"
    slides = params.get("slides") or []
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
    output_path = output_dir / safe_name(title, "演示文稿")

    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    _add_title_slide(prs, title, len(slides))
    for index, item in enumerate(slides, 1):
        _add_content_slide(
            prs,
            index,
            item.get("heading") or "无标题",
            item.get("body") or "",
        )
    prs.save(output_path)
    print(
        json.dumps(
            {
                "success": True,
                "message": "PPT 生成完成",
                "file_name": output_path.name,
                "filepath": str(output_path),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
