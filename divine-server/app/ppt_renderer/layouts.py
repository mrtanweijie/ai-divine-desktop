"""14 种版式渲染与分发。

版式：cover / toc / section / bullets / two_col / cards / timeline /
columns / compare / kpi / quote / table / chart / end。
所有版式统一从主题 token 取色，正文按 textfit 自适应字号。
"""

from __future__ import annotations

import math
from typing import Any, Callable

from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from . import charts, tables
from .textfit import pick_size, split_title_desc
from .themes import (add_oval, add_rect, add_textbox, blend, get_ppt_theme,
                     gradient, is_light, rgb, set_alpha, set_run, solid)

MARGIN = 0.7
CONTENT_W = 13.333 - MARGIN * 2
CONTENT_TOP = 2.0
CONTENT_H = 4.55

LAYOUTS = {
    "cover", "toc", "section", "bullets", "two_col", "cards", "timeline",
    "columns", "compare", "kpi", "quote", "table", "chart", "end", "default",
}


# ---------------------------------------------------------------- 页面公共块

def _chrome(slide: Any, theme: dict[str, Any], index: int, heading: str) -> None:
    """内容页公共骨架：背景 + 顶部强调条 + 序号 + 标题 + 页脚。"""
    add_rect(slide, 0, 0, 13.333, 7.5, theme["content_bg"])
    add_rect(slide, 0, 0, 13.333, 0.09, theme["accent"])

    label = add_textbox(slide, MARGIN, 0.5, 8, 0.4)
    set_run(label.text_frame.paragraphs[0].add_run(), 14,
            theme["accent"], bold=True, font=theme["font"])
    label.text_frame.paragraphs[0].runs[0].text = f"{index:02d}"

    if heading:
        size = pick_size(heading, CONTENT_W, 0.85, [30, 26, 22])
        box = add_textbox(slide, MARGIN, 0.92, CONTENT_W, 0.9)
        p = box.text_frame.paragraphs[0]
        set_run(p.add_run(), size, theme["text"], bold=True, font=theme["font"])
        p.runs[0].text = heading

    _footer(slide, theme, heading)


def _footer(slide: Any, theme: dict[str, Any], text: str) -> None:
    if not text:
        return
    box = add_textbox(slide, MARGIN, 6.98, CONTENT_W, 0.32)
    p = box.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.RIGHT
    display = text if len(text) <= 32 else text[:31] + "…"
    set_run(p.add_run(), 10.5, blend(theme["content_bg"], theme["muted"], 0.75),
            font=theme["font"])
    p.runs[0].text = display


def _bullets(box: Any, theme: dict[str, Any], points: list[str],
             sizes: list[float], height_in: float) -> None:
    """带强调色圆点的要点列表，按总量自适应字号。"""
    tf = box.text_frame
    total = sum(len(p) for p in points) or 1
    per_size = pick_size("x" * max(24, total // max(len(points), 1)),
                         box.width / 914400, height_in / max(len(points), 1) * 1.6,
                         sizes)
    for i, raw in enumerate(points):
        title, desc = split_title_desc(raw)
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(10)
        p.line_spacing = 1.22
        dot = p.add_run()
        set_run(dot, per_size, theme["accent"], bold=True, font=theme["font"])
        dot.text = "•  "
        main = p.add_run()
        set_run(main, per_size, theme["text"], bold=bool(desc),
                font=theme["font"])
        main.text = title if desc else raw
        if desc:
            sub = p.add_run()
            set_run(sub, max(per_size - 2.5, 10.5), theme["muted"],
                    font=theme["font"])
            sub.text = f"　{desc}"


def _cover_bg(slide: Any, theme: dict[str, Any]) -> None:
    """封面/结尾页背景：深色底走渐变，浅色底纯色 + 几何光斑。"""
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, 13.333, 7.5)
    if is_light(theme["cover_bg"]):
        solid(bg, theme["cover_bg"])
        halo = add_oval(slide, 9.6, 3.2, 4.6, 4.6, theme["accent"])
        set_alpha(halo, 10)
        halo2 = add_oval(slide, 11.2, 0.4, 2.4, 2.4, theme["accent"])
        set_alpha(halo2, 8)
    else:
        gradient(bg, theme["cover_bg"], blend(theme["cover_bg"], theme["accent"], 0.55),
                 angle=115)
        halo = add_oval(slide, 9.8, 3.6, 4.4, 4.4, theme["accent"])
        set_alpha(halo, 16)
        halo2 = add_oval(slide, 11.4, 0.3, 2.2, 2.2, theme["accent"])
        set_alpha(halo2, 12)


# ---------------------------------------------------------------- 媒体块

def _media_block(slide: Any, theme: dict[str, Any], image: dict[str, Any] | None,
                 x: float, y: float, w: float, h: float,
                 resolve_media: Callable[[str], Any] | None) -> None:
    """图文两栏的媒体区：有图贴图（cover-crop），无图渐变占位。"""
    picture = None
    path_str = str((image or {}).get("path") or "").strip()
    if path_str and resolve_media:
        try:
            picture = resolve_media(path_str)
        except Exception:  # noqa: BLE001 — 图片不可用时降级为占位
            picture = None

    if picture is not None:
        try:
            pic = slide.shapes.add_picture(str(picture), Inches(x), Inches(y),
                                           Inches(w), Inches(h))
            _cover_crop(pic, w, h)
        except Exception:  # noqa: BLE001
            picture = None

    if picture is None:
        panel = add_rect(slide, x, y, w, h, theme["accent_light"], rounded=True)
        panel.line.color.rgb = rgb(blend(theme["content_bg"],
                                         theme["accent_light"], 0.5))
        panel.line.width = Pt(1)
        glyph = add_oval(slide, x + w / 2 - 0.42, y + h / 2 - 0.86, 0.84, 0.84,
                         theme["accent"])
        set_alpha(glyph, 22)
        note = add_textbox(slide, x + 0.3, y + h / 2 + 0.14, w - 0.6, 0.4)
        p = note.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        set_run(p.add_run(), 12, theme["muted"], font=theme["font"])
        p.runs[0].text = "配图占位 · 可由 image_generate 生成"

    caption = str((image or {}).get("caption") or "").strip()
    if caption:
        cap = add_textbox(slide, x, y + h + 0.08, w, 0.32)
        p = cap.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        set_run(p.add_run(), 10.5, theme["muted"], font=theme["font"])
        p.runs[0].text = caption


def _cover_crop(pic: Any, w: float, h: float) -> None:
    """按目标框比例裁剪图片（cover 模式，不拉伸变形）。"""
    try:
        native_w, native_h = pic.image.size
        if not native_w or not native_h:
            return
        native_ar = native_w / native_h
        box_ar = w / h
        if native_ar > box_ar:
            crop = (1 - box_ar / native_ar) / 2
            pic.crop_left = crop
            pic.crop_right = crop
        else:
            crop = (1 - native_ar / box_ar) / 2
            pic.crop_top = crop
            pic.crop_bottom = crop
    except Exception:  # noqa: BLE001 — 裁剪失败保持拉伸
        pass


# ---------------------------------------------------------------- 各版式

def _layout_cover(slide: Any, theme: dict[str, Any], item: dict[str, Any],
                  index: int) -> None:
    _cover_bg(slide, theme)
    add_rect(slide, 0.95, 2.52, 0.14, 1.35, theme["accent"])

    title = str(item.get("heading") or item.get("title") or "未命名演示文稿")
    size = pick_size(title, 10.4, 1.9, [44, 40, 36, 32])
    box = add_textbox(slide, 1.35, 2.35, 10.6, 2.0)
    tf = box.text_frame
    p = tf.paragraphs[0]
    p.line_spacing = 1.15
    set_run(p.add_run(), size, theme["cover_text"], bold=True, font=theme["font"])
    p.runs[0].text = title

    y = 4.45
    subtitle = str(item.get("subtitle") or "").strip()
    if subtitle:
        sub = add_textbox(slide, 1.35, 4.42, 10.6, 0.7)
        set_run(sub.text_frame.paragraphs[0].add_run(), 16, theme["meta"],
                font=theme["font"])
        sub.text_frame.paragraphs[0].runs[0].text = subtitle
        y = 5.25

    meta = add_textbox(slide, 1.35, y, 10.6, 0.5)
    set_run(meta.text_frame.paragraphs[0].add_run(), 13, theme["meta"],
            font=theme["font"])
    pages = int(item.get("_pages") or max(index - 1, 0))
    meta.text_frame.paragraphs[0].runs[0].text = f"AI Divine · {pages} 页"

    brand = add_textbox(slide, 1.35, 6.8, 6, 0.4)
    set_run(brand.text_frame.paragraphs[0].add_run(), 12,
            blend(theme["cover_bg"], theme["cover_text"], 0.45),
            font=theme["font"])
    brand.text_frame.paragraphs[0].runs[0].text = "AI Divine"


def _layout_toc(slide: Any, theme: dict[str, Any], item: dict[str, Any],
                index: int) -> None:
    _chrome(slide, theme, index, str(item.get("heading") or "目录"))
    points = [str(p) for p in (item.get("points") or []) if str(p).strip()][:8]
    rule_color = blend(theme["content_bg"], theme["muted"], 0.82)
    for i, title in enumerate(points):
        col, row = i % 2, i // 2
        x = MARGIN + col * (CONTENT_W / 2 + 0.25)
        y = 2.15 + row * 1.42
        w = CONTENT_W / 2 - 0.25
        num = add_textbox(slide, x, y, 0.75, 0.5)
        set_run(num.text_frame.paragraphs[0].add_run(), 15, theme["accent"],
                bold=True, font=theme["font"])
        num.text_frame.paragraphs[0].runs[0].text = f"{i + 1:02d}"
        entry = add_textbox(slide, x + 0.75, y, w - 0.75, 0.62)
        size = pick_size(title, w - 0.75, 0.6, [17, 15, 13])
        set_run(entry.text_frame.paragraphs[0].add_run(), size, theme["text"],
                bold=True, font=theme["font"])
        entry.text_frame.paragraphs[0].runs[0].text = title
        add_rect(slide, x, y + 0.78, w, 0.016, rule_color)


def _layout_section(slide: Any, theme: dict[str, Any], item: dict[str, Any],
                    index: int) -> None:
    add_rect(slide, 0, 0, 13.333, 7.5, theme["cover_bg"])
    if is_light(theme["cover_bg"]):
        halo = add_oval(slide, 10.0, 4.4, 3.8, 3.8, theme["accent"])
        set_alpha(halo, 9)
    number = add_textbox(slide, 0.9, 1.0, 6, 2.0)
    set_run(number.text_frame.paragraphs[0].add_run(), 96, 
            blend(theme["cover_bg"], theme["accent"], 0.5),
            bold=True, font=theme["font"])
    number.text_frame.paragraphs[0].runs[0].text = f"{index:02d}"

    kicker = add_textbox(slide, 0.95, 3.35, 6, 0.45)
    set_run(kicker.text_frame.paragraphs[0].add_run(), 13, theme["accent"],
            bold=True, font=theme["font"])
    kicker.text_frame.paragraphs[0].runs[0].text = f"PART {index:02d}"

    heading = str(item.get("heading") or item.get("title") or "")
    size = pick_size(heading, 11.4, 1.1, [40, 34, 28])
    title = add_textbox(slide, 0.95, 3.82, 11.4, 1.15)
    set_run(title.text_frame.paragraphs[0].add_run(), size,
            theme["cover_text"], bold=True, font=theme["font"])
    title.text_frame.paragraphs[0].runs[0].text = heading

    sub = str(item.get("subtitle") or item.get("body") or "").strip()
    if sub:
        sub_box = add_textbox(slide, 0.95, 5.1, 10.8, 0.7)
        size = pick_size(sub, 10.8, 0.7, [15, 13.5, 12])
        set_run(sub_box.text_frame.paragraphs[0].add_run(), size, theme["meta"],
                font=theme["font"])
        sub_box.text_frame.paragraphs[0].runs[0].text = sub


def _layout_bullets(slide: Any, theme: dict[str, Any], item: dict[str, Any],
                    index: int) -> None:
    heading = str(item.get("heading") or item.get("title") or "")
    _chrome(slide, theme, index, heading)
    body = item.get("body") or item.get("content") or item.get("text") or ""
    points = [str(p) for p in (item.get("points") or []) if str(p).strip()]
    if not points and body:
        points = [line.strip() for line in str(body).splitlines() if line.strip()]
    if not points:
        points = ["（本页暂无内容）"]
    box = add_textbox(slide, MARGIN, CONTENT_TOP, CONTENT_W, CONTENT_H)
    _bullets(box, theme, points, [20, 18, 16, 14], CONTENT_H)


def _layout_two_col(slide: Any, theme: dict[str, Any], item: dict[str, Any],
                    index: int, resolve_media: Callable[[str], Any] | None) -> None:
    heading = str(item.get("heading") or item.get("title") or "")
    _chrome(slide, theme, index, heading)
    image = item.get("image") if isinstance(item.get("image"), dict) else {}
    media_w = 5.4
    text_w = CONTENT_W - media_w - 0.45
    media_left = str((image or {}).get("position") or "left") != "right"
    media_x = MARGIN if media_left else MARGIN + text_w + 0.45
    text_x = MARGIN + media_w + 0.45 if media_left else MARGIN

    _media_block(slide, theme, image, media_x, CONTENT_TOP, media_w, CONTENT_H - 0.4,
                 resolve_media)
    points = [str(p) for p in (item.get("points") or []) if str(p).strip()]
    if not points:
        points = [str(item.get("body") or item.get("content") or "")]
    box = add_textbox(slide, text_x, CONTENT_TOP + 0.05, text_w, CONTENT_H - 0.3)
    _bullets(box, theme, points, [16, 14.5, 13, 12], CONTENT_H - 0.3)


def _layout_cards(slide: Any, theme: dict[str, Any], item: dict[str, Any],
                  index: int) -> None:
    heading = str(item.get("heading") or item.get("title") or "")
    _chrome(slide, theme, index, heading)
    points = [str(p) for p in (item.get("points") or []) if str(p).strip()][:8]
    if not points:
        points = ["暂无内容"]
    palette = theme.get("chart_palette") or [theme["accent"]]
    n = len(points)
    cols = 2 if n <= 4 else (3 if n <= 6 else 4)
    rows = math.ceil(n / cols)
    gap = 0.3
    card_w = (CONTENT_W - gap * (cols - 1)) / cols
    card_h = min((CONTENT_H - gap * (rows - 1)) / rows, 2.3)
    desc_sizes = [12.5, 11.5, 10.5] if cols <= 3 else [11.5, 10.5, 10]
    for i, raw in enumerate(points):
        title, desc = split_title_desc(raw)
        col, row = i % cols, i // cols
        x = MARGIN + col * (card_w + gap)
        y = CONTENT_TOP + row * (card_h + gap)
        card = add_rect(slide, x, y, card_w, card_h, theme["accent_light"],
                        rounded=True, radius=0.07)
        card.line.color.rgb = rgb(blend(theme["content_bg"],
                                        theme["accent_light"], 0.35))
        card.line.width = Pt(1)
        dot = add_oval(slide, x + 0.22, y + 0.22, 0.13, 0.13,
                       palette[i % len(palette)])
        set_alpha(dot, 90)
        if desc:
            t_box = add_textbox(slide, x + 0.22, y + 0.48, card_w - 0.44, 0.5)
            t_size = pick_size(title, card_w - 0.44, 0.5,
                               [15, 14, 13] if cols <= 3 else [13.5, 12.5, 11.5])
            set_run(t_box.text_frame.paragraphs[0].add_run(), t_size,
                    theme["text"], bold=True, font=theme["font"])
            t_box.text_frame.paragraphs[0].runs[0].text = title
            d_box = add_textbox(slide, x + 0.22, y + 1.02, card_w - 0.44,
                                card_h - 1.2)
            d_size = pick_size(desc, card_w - 0.44, card_h - 1.2, desc_sizes)
            tf = d_box.text_frame
            p = tf.paragraphs[0]
            p.line_spacing = 1.25
            set_run(p.add_run(), d_size, theme["muted"], font=theme["font"])
            p.runs[0].text = desc
        else:
            box = add_textbox(slide, x + 0.22, y + 0.55, card_w - 0.44,
                              card_h - 0.75)
            size = pick_size(raw, card_w - 0.44, card_h - 0.75,
                             [14, 13, 12, 11])
            tf = box.text_frame
            p = tf.paragraphs[0]
            p.line_spacing = 1.25
            set_run(p.add_run(), size, theme["text"], font=theme["font"])
            p.runs[0].text = raw


def _layout_timeline(slide: Any, theme: dict[str, Any], item: dict[str, Any],
                     index: int) -> None:
    heading = str(item.get("heading") or item.get("title") or "")
    _chrome(slide, theme, index, heading)
    steps = [str(p) for p in (item.get("points") or []) if str(p).strip()][:10]
    if not steps:
        steps = ["阶段一", "阶段二", "阶段三"]

    track_color = blend(theme["content_bg"], theme["accent"], 0.35)
    if len(steps) <= 5:
        rows = [steps]
        ys = [3.85]
    else:
        mid = math.ceil(len(steps) / 2)
        rows = [steps[:mid], steps[mid:]]
        ys = [2.75, 5.15]

    for row_points, track_y in zip(rows, ys):
        n = len(row_points)
        start_x = MARGIN + 0.35
        end_x = 13.333 - MARGIN - 0.35
        add_rect(slide, start_x, track_y, end_x - start_x, 0.045, track_color)
        span = (end_x - start_x) / n
        for i, raw in enumerate(row_points):
            title, desc = split_title_desc(raw)
            cx = start_x + span * (i + 0.5)
            dot = add_oval(slide, cx - 0.14, track_y - 0.115, 0.3, 0.3,
                           theme["accent"])
            dot.line.color.rgb = rgb(theme["content_bg"])
            dot.line.width = Pt(2)
            box_w = min(span, 2.8)
            t_box = add_textbox(slide, cx - box_w / 2, track_y + 0.32,
                                box_w, 0.55)
            t_size = pick_size(title, box_w, 0.55, [14, 13, 12, 11])
            p = t_box.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER
            set_run(p.add_run(), t_size, theme["text"], bold=True,
                    font=theme["font"])
            p.runs[0].text = title
            if desc:
                d_box = add_textbox(slide, cx - box_w / 2, track_y + 0.88,
                                    box_w, 0.85)
                d_size = pick_size(desc, box_w, 0.85, [11, 10.5, 10])
                p = d_box.text_frame.paragraphs[0]
                p.alignment = PP_ALIGN.CENTER
                p.line_spacing = 1.2
                set_run(p.add_run(), d_size, theme["muted"], font=theme["font"])
                p.runs[0].text = desc


def _layout_columns(slide: Any, theme: dict[str, Any], item: dict[str, Any],
                    index: int) -> None:
    heading = str(item.get("heading") or item.get("title") or "")
    _chrome(slide, theme, index, heading)
    cols = [str(p) for p in (item.get("points") or []) if str(p).strip()]
    if not cols:
        cols = ["第一栏", "第二栏", "第三栏"]
    n = min(max(len(cols), 2), 4)
    gap = 0.35
    col_w = (CONTENT_W - gap * (n - 1)) / n
    col_h = CONTENT_H - 0.2
    border = blend(theme["content_bg"], theme["accent_light"], 0.4)
    for i in range(n):
        x = MARGIN + i * (col_w + gap)
        panel = add_rect(slide, x, CONTENT_TOP, col_w, col_h,
                         theme["accent_light"], rounded=True, radius=0.05)
        panel.line.color.rgb = rgb(border)
        panel.line.width = Pt(1)
        text = cols[i] if i < len(cols) else ""
        box = add_textbox(slide, x + 0.28, CONTENT_TOP + 0.3, col_w - 0.56,
                          col_h - 0.6)
        size = pick_size(text, col_w - 0.56, col_h - 0.6, [13, 12, 11, 10.5])
        tf = box.text_frame
        p = tf.paragraphs[0]
        p.line_spacing = 1.3
        set_run(p.add_run(), size, theme["text"], font=theme["font"])
        p.runs[0].text = text

def _layout_compare(slide: Any, theme: dict[str, Any], item: dict[str, Any],
                    index: int) -> None:
    left = item.get("left") if isinstance(item.get("left"), dict) else None
    right = item.get("right") if isinstance(item.get("right"), dict) else None
    if not left or not right:
        _layout_columns(slide, theme, item, index)
        return
    heading = str(item.get("heading") or item.get("title") or "")
    _chrome(slide, theme, index, heading)

    panel_w = (CONTENT_W - 1.0) / 2
    panel_h = CONTENT_H - 0.15
    border = blend(theme["content_bg"], theme["accent_light"], 0.4)
    for side, spec_obj, tag_color, px in (
        ("left", left, theme["accent"], MARGIN),
        ("right", right, blend(theme["text"], theme["accent"], 0.35),
         MARGIN + panel_w + 1.0),
    ):
        panel = add_rect(slide, px, CONTENT_TOP, panel_w, panel_h,
                         theme["accent_light"], rounded=True, radius=0.05)
        panel.line.color.rgb = rgb(border)
        panel.line.width = Pt(1)
        tag_text = str(spec_obj.get("title") or ("方案 A" if side == "left" else "方案 B"))
        tag = add_rect(slide, px + 0.3, CONTENT_TOP + 0.3, 1.7, 0.44,
                       tag_color, rounded=True, radius=0.5)
        tb = tag.text_frame
        tb.word_wrap = False
        p = tb.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        set_run(p.add_run(), 12, "FFFFFF", bold=True, font=theme["font"])
        p.runs[0].text = tag_text[:6]
        points = [str(pt) for pt in (spec_obj.get("points") or [])][:5]
        box = add_textbox(slide, px + 0.3, CONTENT_TOP + 0.95, panel_w - 0.6,
                          panel_h - 1.3)
        _bullets(box, theme, points, [13.5, 12.5, 11.5], panel_h - 1.3)
    badge = add_oval(slide, 6.667 - 0.36, CONTENT_TOP + panel_h / 2 - 0.36,
                     0.72, 0.72, theme["text"])
    bt = badge.text_frame
    p = bt.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    set_run(p.add_run(), 14, "FFFFFF", bold=True, font=theme["font"])
    p.runs[0].text = "VS"


def _layout_kpi(slide: Any, theme: dict[str, Any], item: dict[str, Any],
                index: int) -> None:
    heading = str(item.get("heading") or item.get("title") or "")
    _chrome(slide, theme, index, heading)
    points = [str(p) for p in (item.get("points") or []) if str(p).strip()][:4]
    if not points:
        points = ["--|待补充"]
    n = len(points)
    gap = 0.3
    card_w = (CONTENT_W - gap * (n - 1)) / n
    card_h = 2.6
    y = CONTENT_TOP + 0.6
    border = blend(theme["content_bg"], theme["accent_light"], 0.4)
    for i, raw in enumerate(points):
        parts = [part.strip() for part in raw.split("|")]
        value = parts[0] or "--"
        label = parts[1] if len(parts) > 1 else ""
        delta = parts[2] if len(parts) > 2 else ""
        x = MARGIN + i * (card_w + gap)
        card = add_rect(slide, x, y, card_w, card_h, theme["accent_light"],
                        rounded=True, radius=0.07)
        card.line.color.rgb = rgb(border)
        card.line.width = Pt(1)
        v_size = pick_size(value, card_w - 0.5, 0.85, [34, 30, 26, 22])
        v_box = add_textbox(slide, x + 0.25, y + 0.4, card_w - 0.5, 0.9)
        set_run(v_box.text_frame.paragraphs[0].add_run(), v_size,
                theme["accent"], bold=True, font=theme["font"])
        v_box.text_frame.paragraphs[0].runs[0].text = value
        if label:
            l_box = add_textbox(slide, x + 0.25, y + 1.38, card_w - 0.5, 0.45)
            l_size = pick_size(label, card_w - 0.5, 0.45, [14, 13, 12])
            set_run(l_box.text_frame.paragraphs[0].add_run(), l_size,
                    theme["text"], bold=True, font=theme["font"])
            l_box.text_frame.paragraphs[0].runs[0].text = label
        if delta:
            d_box = add_textbox(slide, x + 0.25, y + 1.86, card_w - 0.5, 0.4)
            set_run(d_box.text_frame.paragraphs[0].add_run(), 11.5,
                    theme["muted"], font=theme["font"])
            d_box.text_frame.paragraphs[0].runs[0].text = delta


def _layout_quote(slide: Any, theme: dict[str, Any], item: dict[str, Any],
                  index: int) -> None:
    add_rect(slide, 0, 0, 13.333, 7.5, theme["content_bg"])
    mark = add_textbox(slide, 1.1, 0.75, 2.5, 1.6)
    set_run(mark.text_frame.paragraphs[0].add_run(), 88,
            blend(theme["content_bg"], theme["accent"], 0.45),
            bold=True, font="Georgia")
    mark.text_frame.paragraphs[0].runs[0].text = "\u201C"

    quote = str(item.get("heading") or item.get("body") or "").strip()
    size = pick_size(quote, 10.2, 2.3, [24, 21, 18, 16])
    box = add_textbox(slide, 1.55, 2.55, 10.2, 2.4)
    p = box.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    p.line_spacing = 1.45
    set_run(p.add_run(), size, theme["text"], bold=True, font=theme["font"])
    p.runs[0].text = quote or ""

    author = str(item.get("subtitle") or "").strip()
    if author:
        a_box = add_textbox(slide, 1.55, 5.25, 10.2, 0.5)
        p = a_box.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        set_run(p.add_run(), 13, theme["muted"], font=theme["font"])
        p.runs[0].text = f"—— {author}"



def _layout_table(slide: Any, theme: dict[str, Any], item: dict[str, Any],
                  index: int) -> None:
    heading = str(item.get("heading") or item.get("title") or "")
    _chrome(slide, theme, index, heading)
    spec = item.get("table") if isinstance(item.get("table"), dict) else None
    if not spec:
        raise ValueError("table 版式需要 table: {columns, rows} 数据")
    caption = str((item.get("image") or {}).get("caption") or "").strip()
    box_h = CONTENT_H - (0.45 if caption else 0.1)
    tables.add_table(slide, theme, spec, MARGIN, CONTENT_TOP, CONTENT_W, box_h)
    if caption:
        cap = add_textbox(slide, MARGIN, 6.55, CONTENT_W, 0.32)
        set_run(cap.text_frame.paragraphs[0].add_run(), 10.5, theme["muted"],
                font=theme["font"])
        cap.text_frame.paragraphs[0].runs[0].text = caption


def _layout_chart(slide: Any, theme: dict[str, Any], item: dict[str, Any],
                  index: int) -> None:
    heading = str(item.get("heading") or item.get("title") or "")
    _chrome(slide, theme, index, heading)
    spec = item.get("chart") if isinstance(item.get("chart"), dict) else None
    if not spec:
        raise ValueError(
            "chart 版式需要 chart: {type, categories, series} 数据；"
            "复杂图表请用 generate_chart 生成 SVG 后以 image.path 引用"
        )
    points = [str(p) for p in (item.get("points") or []) if str(p).strip()]
    caption = str((item.get("image") or {}).get("caption") or "").strip()

    if points:
        chart_w = CONTENT_W * 0.6
        charts.add_native_chart(slide, theme, spec, MARGIN, CONTENT_TOP,
                                chart_w, CONTENT_H - 0.25)
        box = add_textbox(slide, MARGIN + chart_w + 0.45, CONTENT_TOP + 0.05,
                          CONTENT_W - chart_w - 0.45, CONTENT_H - 0.4)
        _bullets(box, theme, points, [14.5, 13, 12, 11], CONTENT_H - 0.4)
    else:
        charts.add_native_chart(slide, theme, spec, 1.15, CONTENT_TOP,
                                CONTENT_W - 0.9, CONTENT_H - 0.25)
    if caption:
        cap = add_textbox(slide, MARGIN, 6.62, CONTENT_W, 0.32)
        set_run(cap.text_frame.paragraphs[0].add_run(), 10.5, theme["muted"],
                font=theme["font"])
        cap.text_frame.paragraphs[0].runs[0].text = caption


def _layout_end(slide: Any, theme: dict[str, Any], item: dict[str, Any],
                index: int) -> None:
    _cover_bg(slide, theme)
    heading = str(item.get("heading") or item.get("title") or "谢谢观看")
    size = pick_size(heading, 10, 1.2, [42, 38, 32])
    box = add_textbox(slide, 1.6, 2.7, 10.1, 1.3)
    p = box.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    set_run(p.add_run(), size, theme["cover_text"], bold=True, font=theme["font"])
    p.runs[0].text = heading

    sub = str(item.get("subtitle") or "").strip()
    if sub:
        s_box = add_textbox(slide, 1.6, 4.05, 10.1, 0.55)
        p = s_box.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        set_run(p.add_run(), 15, theme["meta"], font=theme["font"])
        p.runs[0].text = sub

    contact = str(item.get("body") or "").strip()
    if contact:
        c_box = add_textbox(slide, 1.6, 4.85, 10.1, 0.5)
        p = c_box.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        set_run(p.add_run(), 12.5, blend(theme["cover_bg"], theme["cover_text"], 0.5),
                font=theme["font"])
        p.runs[0].text = contact



# ---------------------------------------------------------------- 分发

def guess_layout(item: Any) -> str:
    """未显式指定 layout 时的保守推断。"""
    heading = str(item.get("heading") or item.get("title") or "") if isinstance(item, dict) else ""
    lowered = heading.lower()
    if "目录" in heading or "contents" in lowered:
        return "toc"
    if any(word in heading for word in ("时间线", "路线", "里程碑", "阶段")) \
            or any(word in lowered for word in ("timeline", "roadmap")):
        return "timeline"
    points = item.get("points") if isinstance(item, dict) else None
    count = len(points) if isinstance(points, list) else 0
    if count >= 5:
        return "cards"
    if 0 < count <= 3:
        return "columns"
    return "bullets"


def add_slide(prs: Any, item: Any, theme_id: str, index: int,
              resolve_media: Callable[[str], Any] | None = None) -> str:
    """渲染一页内容版式，返回实际使用的 layout 名。"""
    theme = get_ppt_theme(theme_id)
    item = item if isinstance(item, dict) else {"body": str(item)}
    layout = str(item.get("layout") or "").strip().lower()
    if layout not in LAYOUTS:
        layout = guess_layout(item)

    slide = prs.slides.add_slide(prs.slide_layouts[6])
    if layout == "cover":
        _layout_cover(slide, theme, item, index)
    elif layout == "toc":
        _layout_toc(slide, theme, item, index)
    elif layout == "section":
        _layout_section(slide, theme, item, index)
    elif layout == "two_col":
        _layout_two_col(slide, theme, item, index, resolve_media)
    elif layout == "cards":
        _layout_cards(slide, theme, item, index)
    elif layout == "timeline":
        _layout_timeline(slide, theme, item, index)
    elif layout == "columns":
        _layout_columns(slide, theme, item, index)
    elif layout == "compare":
        _layout_compare(slide, theme, item, index)
    elif layout == "kpi":
        _layout_kpi(slide, theme, item, index)
    elif layout == "quote":
        _layout_quote(slide, theme, item, index)
    elif layout == "table":
        _layout_table(slide, theme, item, index)
    elif layout == "chart":
        _layout_chart(slide, theme, item, index)
    elif layout == "end":
        _layout_end(slide, theme, item, index)
    else:
        _layout_bullets(slide, theme, item, index)
    return layout
