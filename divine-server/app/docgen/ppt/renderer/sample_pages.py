"""015/016 样张主题的专属渲染器（keynote / devconf）。

隔离边界：这两套主题带 "sample" 标记，add_slide 入口处整页委托到本模块，
通用版式（layouts.py 的 _layout_* / _chrome）完全不参与，模板之间互不污染。
几何与字号直接从样张 CSS 换算：1280px 画布 → 13.333in（1px = 13.333/1280，
1px = 0.75pt）。

页面构图与样张对应：
- 016 devconf：封面 / 深色品牌宣言 / 数据带 / fcard 功能网格 / 深潜图文 /
  竞品表格 / why 编号行（要点·里程碑）/ 双面板对比 / 陈述金句 / 结尾 CTA
- 015 keynote：左下封面 / 愿景宣言 / 特性三卡（图标块）/ 性能数据带 /
  深黑编号行 / 金句 / 深色结尾
015/016 没有章节页与目录页（脚本层会跳过），渲染器内也做防御处理。
"""

from __future__ import annotations

from typing import Any, Callable

from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from .textfit import pick_size, split_title_desc
from .themes import (
    add_oval, add_pill, add_rect, add_star4, add_textbox, blend,
    is_light, rgb, set_run,
)

PX = 13.333 / 1280.0


def _pt(px: float) -> float:
    return px * 0.75


def _in(px: float) -> float:
    return px * PX


def _mono() -> str:
    return "JetBrains Mono"


def _letters(n: int) -> list[str]:
    return [chr(ord("a") + i) for i in range(min(n, 8))]


def _points_of(item: dict[str, Any], limit: int = 6) -> list[str]:
    return [str(p) for p in (item.get("points") or []) if str(p).strip()][:limit]


def _is_devconf(theme: dict[str, Any]) -> bool:
    return theme.get("sample") == "devconf"


# ---------------------------------------------------------------- 页眉 / 页脚

def _foot_devconf(slide: Any, theme: dict[str, Any], st: dict[str, Any],
                  index: int) -> None:
    pages = int(st.get("_deck_pages") or 0)
    muted = blend(theme["content_bg"], theme["text"], 0.35)
    foot_y = 7.5 - _in(30) - 0.26
    brand = str(st.get("_brand") or "").strip()
    if brand:
        add_rect(slide, _in(72), foot_y + 0.055, 0.08, 0.08, theme["accent"],
                 rounded=True, radius=0.15)
        fb = add_textbox(slide, _in(72) + 0.18, foot_y, 6.0, 0.28)
        fp = fb.text_frame.paragraphs[0]
        set_run(fp.add_run(), _pt(13), theme["text"], bold=True, font=_mono(),
                letter_spacing_pt=_pt(13 * 0.14))
        fp.runs[0].text = brand.upper()
    if pages:
        pb = add_textbox(slide, 6.8, foot_y, 5.77, 0.28)
        pp = pb.text_frame.paragraphs[0]
        pp.alignment = PP_ALIGN.RIGHT
        set_run(pp.add_run(), _pt(13), muted, font=_mono(),
                letter_spacing_pt=_pt(13 * 0.1))
        pp.runs[0].text = f"{index:02d} / {pages:02d}"


def _foot_keynote(slide: Any, theme: dict[str, Any], st: dict[str, Any],
                  index: int) -> None:
    pages = int(st.get("_deck_pages") or 0)
    if not pages:
        return
    mono_c = blend(theme["content_bg"], theme["text"], 0.45)
    pb = add_textbox(slide, 9.5, 7.5 - _in(28) - 0.26, 3.1, 0.28)
    pp = pb.text_frame.paragraphs[0]
    pp.alignment = PP_ALIGN.RIGHT
    set_run(pp.add_run(), _pt(12.5), mono_c, font=_mono(),
            letter_spacing_pt=_pt(12.5 * 0.1))
    pp.runs[0].text = f"{index:02d} / {pages:02d}"
    if 2 <= pages <= 24:
        dot_w, gap, active_w, h, y = 0.075, 0.055, 0.24, 0.075, 7.09
        total = (pages - 1) * (dot_w + gap) + active_w
        x = (13.333 - total) / 2
        idle = blend(theme["content_bg"], theme["text"], 0.14)
        for i in range(pages):
            if i + 1 == index:
                add_rect(slide, x, y, active_w, h, theme["accent"],
                         rounded=True, radius=0.5)
            else:
                add_rect(slide, x, y, dot_w, h, idle, rounded=True, radius=0.5)
            x += (active_w if i + 1 == index else dot_w) + gap


def _head_devconf(slide: Any, theme: dict[str, Any], st: dict[str, Any],
                  item: dict[str, Any], index: int) -> None:
    """016 .head：纸白底 + mono kicker（NN · LABEL）+ 40px/800 h2 + 15px sub
    + 页脚（左品牌粗等宽 · 右 mono 页码）。"""
    add_rect(slide, 0, 0, 13.333, 7.5, theme["content_bg"])
    _foot_devconf(slide, theme, st, index)
    label = str(item.get("kicker") or "").strip()
    head_y = _in(64)
    if label:
        kbox = add_textbox(slide, _in(72), head_y, 11.0, 0.3)
        kp = kbox.text_frame.paragraphs[0]
        num = kp.add_run()
        set_run(num, _pt(13.5), theme["accent"], bold=True, font=_mono(),
                letter_spacing_pt=_pt(13.5 * 0.22))
        num.text = f"{index:02d}"
        rest = kp.add_run()
        set_run(rest, _pt(13.5), theme["muted"], font=_mono(),
                letter_spacing_pt=_pt(13.5 * 0.22))
        rest.text = f" · {label.upper()}"
        head_y += 0.21
    heading = str(item.get("heading") or item.get("title") or "")
    if heading:
        h2 = add_textbox(slide, _in(72), head_y + 0.08, 11.89, 0.75)
        hp = h2.text_frame.paragraphs[0]
        set_run(hp.add_run(), _pt(40), theme["text"], bold=True,
                font=theme["font"])
        hp.runs[0].text = heading
        head_y += 0.62
    sub = str(item.get("subtitle") or "").strip()
    if sub:
        sbox = add_textbox(slide, _in(72), head_y + 0.08, 11.0, 0.4)
        sp = sbox.text_frame.paragraphs[0]
        set_run(sp.add_run(), _pt(15), theme["muted"], font=theme["font"])
        sp.runs[0].text = sub


def _head_keynote(slide: Any, theme: dict[str, Any], st: dict[str, Any],
                  item: dict[str, Any], index: int) -> None:
    """015 内容页骨架：纯黑舞台 + 蓝点 mono 眉题 + 46px 标题 + 进度点页脚。"""
    add_rect(slide, 0, 0, 13.333, 7.5, theme["content_bg"])
    _foot_keynote(slide, theme, st, index)
    label = str(item.get("kicker") or "").strip()
    top = _in(70)
    if label:
        add_oval(slide, _in(96), top + 0.09, 0.09, 0.09, theme["accent"])
        kb = add_textbox(slide, _in(96) + 0.2, top, 9.0, 0.3)
        kp = kb.text_frame.paragraphs[0]
        set_run(kp.add_run(), _pt(13), theme["muted"], font=_mono(),
                letter_spacing_pt=_pt(13 * 0.14))
        kp.runs[0].text = label
        top += 0.34
    heading = str(item.get("heading") or item.get("title") or "")
    if heading:
        h2 = add_textbox(slide, _in(96), top, 11.4, 0.72)
        hp = h2.text_frame.paragraphs[0]
        set_run(hp.add_run(), _pt(46), theme["text"], bold=True,
                font=theme["font"])
        hp.runs[0].text = heading


# ---------------------------------------------------------------- 封面

def _cover_devconf(slide: Any, theme: dict[str, Any], item: dict[str, Any]) -> None:
    """016 P1 封面：顶栏品牌/大会 + 垂直居中主区（mono kicker（品牌加粗）+
    88px 标题 + thin 定位句 + 19px 描述段）+ 底部 / 日期 / 地点 / 讲者 元信息行
    + 发丝线。字段：brand/event/kicker/subtitle（定位句）/body（描述）/
    date/place/speaker。"""
    add_rect(slide, 0, 0, 13.333, 7.5, theme["cover_bg"])
    dark_ink = theme["cover_text"]
    muted = blend(theme["cover_bg"], dark_ink, 0.5)
    # —— 顶栏：品牌（左） · 大会名（右）——
    brand = str(item.get("brand") or "").strip()
    conf = str(item.get("event") or "").strip()
    if brand:
        add_rect(slide, _in(72), _in(52) + 0.03, 0.11, 0.11, theme["accent"])
        bb = add_textbox(slide, _in(72) + 0.2, _in(52), 5.5, 0.3)
        bp = bb.text_frame.paragraphs[0]
        set_run(bp.add_run(), _pt(15), dark_ink, bold=True, font=theme["font"],
                letter_spacing_pt=_pt(15 * 0.26))
        bp.runs[0].text = brand.upper()
    if conf:
        cf = add_textbox(slide, 6.8, _in(52), 5.75, 0.3)
        cp = cf.text_frame.paragraphs[0]
        cp.alignment = PP_ALIGN.RIGHT
        set_run(cp.add_run(), _pt(12.5), muted, font=_mono(),
                letter_spacing_pt=_pt(12.5 * 0.14))
        cp.runs[0].text = conf.upper()
    # —— 主区（垂直居中）：mono kicker（品牌加粗）→ 88px 标题 → thin 定位句
    #     → 19px 描述段 ——
    kicker_label = str(item.get("kicker") or "Product Keynote").strip()
    kb = add_textbox(slide, _in(96), 2.42, 10.8, 0.32)
    kp = kb.text_frame.paragraphs[0]
    if brand:
        b_run = kp.add_run()
        set_run(b_run, _pt(14), dark_ink, bold=True, font=_mono(),
                letter_spacing_pt=_pt(14 * 0.14))
        b_run.text = brand.upper()
        k_rest = kp.add_run()
        set_run(k_rest, _pt(14), muted, font=_mono(),
                letter_spacing_pt=_pt(14 * 0.14))
        k_rest.text = f" · {kicker_label}"
    else:
        set_run(kp.add_run(), _pt(14), muted, font=_mono(),
                letter_spacing_pt=_pt(14 * 0.14))
        kp.runs[0].text = kicker_label.upper()
    title = str(item.get("heading") or item.get("title") or "")
    tagline = str(item.get("subtitle") or "").strip()
    desc = str(item.get("body") or "").strip()
    title_size = pick_size(title or " ", 10.9, 1.35, [_pt(88), _pt(76), _pt(66)])
    box = add_textbox(slide, _in(96), 2.82, 10.9, 1.35)
    p = box.text_frame.paragraphs[0]
    p.line_spacing = 1.1
    set_run(p.add_run(), title_size, dark_ink, bold=True, font=theme["font"])
    p.runs[0].text = title
    y = 4.28
    if tagline:
        # .s1-title .thin：标题第二行细体定位句
        thin_size = max(title_size * 0.5, 18)
        tb = add_textbox(slide, _in(96), y, 10.8, 0.75)
        tp = tb.text_frame.paragraphs[0]
        tp.line_spacing = 1.1
        set_run(tp.add_run(), thin_size,
                blend(theme["cover_bg"], dark_ink, 0.62), bold=False,
                font=theme["font"])
        tp.runs[0].text = tagline
        y += 0.92
    if desc:
        db = add_textbox(slide, _in(96), y + (0.28 if not tagline else 0.1),
                         10.6, 0.55)
        dp = db.text_frame.paragraphs[0]
        set_run(dp.add_run(), _pt(19), blend(theme["cover_bg"], dark_ink, 0.72),
                font=theme["font"], letter_spacing_pt=_pt(19 * 0.06))
        dp.runs[0].text = desc
    # —— 底部：/ 日期 / 地点 / 讲者 元信息行 + 发丝线 ——
    meta_bits = [bit for bit in (str(item.get("date") or "").strip(),
                                 str(item.get("place") or "").strip(),
                                 str(item.get("speaker") or "").strip()) if bit]
    line_y = 7.5 - _in(70) - 0.012
    add_rect(slide, _in(96), line_y, 13.333 - 2 * _in(96), 0.012,
             blend(theme["cover_bg"], dark_ink, 0.14))
    if meta_bits:
        mb = add_textbox(slide, _in(96), line_y - 0.42, 11.5, 0.32)
        mp = mb.text_frame.paragraphs[0]
        set_run(mp.add_run(), _pt(13.5), muted, font=_mono(),
                letter_spacing_pt=_pt(13.5 * 0.08))
        mp.runs[0].text = "   ".join(f"/ {bit}" for bit in meta_bits)


def _cover_keynote(slide: Any, theme: dict[str, Any], st: dict[str, Any],
                   item: dict[str, Any]) -> None:
    add_rect(slide, 0, 0, 13.333, 7.5, theme["cover_bg"])
    mono_c = blend(theme["cover_bg"], theme["cover_text"], 0.55)
    event = str(item.get("event") or "").strip()
    brand = str(item.get("brand") or "").strip()
    if event:
        add_oval(slide, 8.6, 2.05, 0.09, 0.09, theme["accent"])
        ev = add_textbox(slide, 8.78, 1.92, 3.7, 0.35)
        ep = ev.text_frame.paragraphs[0]
        set_run(ep.add_run(), 10.5, mono_c, font=_mono(), letter_spacing_pt=1.6)
        ep.runs[0].text = event.upper()
    bx, by = 1.0, 2.55
    if brand:
        add_rect(slide, bx, by, 0.42, 0.42, theme["accent"],
                 rounded=True, radius=0.22)
        add_star4(slide, bx + 0.115, by + 0.115, 0.19, "FFFFFF")
        bn = add_textbox(slide, bx + 0.58, by + 0.02, 5.5, 0.42)
        bp = bn.text_frame.paragraphs[0]
        set_run(bp.add_run(), 13, theme["cover_text"], bold=True,
                font=theme["font"], letter_spacing_pt=0.5)
        bp.runs[0].text = brand
        by += 0.75
    title = str(item.get("heading") or item.get("title") or "")
    size = pick_size(title, 10.6, 2.1, [58, 52, 46, 40])
    box = add_textbox(slide, bx, by, 10.6, 2.1)
    p = box.text_frame.paragraphs[0]
    p.line_spacing = 1.12
    set_run(p.add_run(), size, theme["cover_text"], bold=True,
            font=theme["font"])
    p.runs[0].text = title
    y = by + 1.95
    sub = str(item.get("subtitle") or "").strip()
    if sub:
        sub_box = add_textbox(slide, bx, y, 10.2, 0.5)
        set_run(sub_box.text_frame.paragraphs[0].add_run(), 15,
                theme["muted"], font=theme["font"], letter_spacing_pt=0.4)
        sub_box.text_frame.paragraphs[0].runs[0].text = sub
        y += 0.62
    date_text = str(item.get("date") or "").strip()
    if date_text:
        dt = add_textbox(slide, bx, y, 9.0, 0.35)
        dp = dt.text_frame.paragraphs[0]
        set_run(dp.add_run(), 11, mono_c, font=_mono(), letter_spacing_pt=1.0)
        dp.runs[0].text = date_text
    place = str(item.get("place") or "").strip()
    if place:
        pl = add_textbox(slide, 8.4, 6.35, 4.0, 0.35)
        pp = pl.text_frame.paragraphs[0]
        pp.alignment = PP_ALIGN.RIGHT
        set_run(pp.add_run(), 10.5, theme["muted"], font=theme["font"],
                letter_spacing_pt=0.8)
        pp.runs[0].text = place


# ---------------------------------------------------------------- 深色宣言 / 金句

def _manifesto_devconf(slide: Any, theme: dict[str, Any], st: dict[str, Any],
                       item: dict[str, Any], part_no: int) -> None:
    """016 P2 品牌使命（深色反转）：mono kicker + 58px 陈述句 + 关键词胶囊。"""
    dark_bg = theme.get("dark_bg") or "0E1116"
    dark_ink = theme.get("dark_text") or "F2F3F5"
    add_rect(slide, 0, 0, 13.333, 7.5, dark_bg)
    dark_mut = blend(dark_bg, dark_ink, 0.5)
    label = str(item.get("kicker") or "").strip() or "Brand"
    kh = add_textbox(slide, _in(72), _in(64), 10.5, 0.32)
    kp = kh.text_frame.paragraphs[0]
    num = kp.add_run()
    set_run(num, _pt(13.5), dark_ink, bold=True, font=_mono(),
            letter_spacing_pt=_pt(13.5 * 0.22))
    num.text = f"{part_no:02d}"
    rest = kp.add_run()
    set_run(rest, _pt(13.5), dark_mut, font=_mono(),
            letter_spacing_pt=_pt(13.5 * 0.22))
    rest.text = f" · {label.upper()}"
    heading = str(item.get("heading") or item.get("title") or "")
    size = pick_size(heading, 10.55, 1.9, [_pt(58), _pt(50), _pt(44), _pt(38)])
    box = add_textbox(slide, _in(130), 2.45, 10.55, 2.0)
    p = box.text_frame.paragraphs[0]
    p.line_spacing = 1.42
    set_run(p.add_run(), size, dark_ink, bold=True, font=theme["font"])
    p.runs[0].text = heading
    chips = [split_title_desc(str(raw))[0] for raw in _points_of(item, 4)]
    chips = [chip for chip in chips if chip]
    if chips:
        chip_blue = blend(theme["accent"], "FFFFFF", 0.4)
        cx, cy = _in(130), 4.85
        for i, chip in enumerate(chips):
            w = 0.44 + len(chip) * 0.16
            pill = add_pill(slide, cx, cy, w, 0.5, dark_bg)
            pill.line.color.rgb = rgb(
                chip_blue if i == 0
                else blend(dark_bg, dark_ink, 0.28))
            pill.line.width = Pt(1)
            ptf = pill.text_frame
            ptf.vertical_anchor = MSO_ANCHOR.MIDDLE
            pp = ptf.paragraphs[0]
            pp.alignment = PP_ALIGN.CENTER
            set_run(pp.add_run(), _pt(14.5),
                    chip_blue if i == 0 else dark_ink, font=_mono(),
                    letter_spacing_pt=0.6)
            pp.runs[0].text = chip
            cx += w + _in(14)
    brand = str(item.get("brand") or "").strip()
    foot = add_textbox(slide, _in(72), 7.5 - _in(30) - 0.28, 11.89, 0.3)
    fp = foot.text_frame.paragraphs[0]
    if brand:
        b_run = fp.add_run()
        set_run(b_run, _pt(13), dark_mut, font=theme["font"])
        b_run.text = brand
        sep = fp.add_run()
        set_run(sep, _pt(13), dark_mut, font=theme["font"])
        sep.text = "                                                          "
    m_run = fp.add_run()
    set_run(m_run, _pt(13), dark_mut, font=_mono(),
            letter_spacing_pt=_pt(13 * 0.1))
    m_run.text = f"BRAND MANIFESTO · {part_no:02d}"


def _manifesto_keynote(slide: Any, theme: dict[str, Any], st: dict[str, Any],
                       item: dict[str, Any], part_no: int) -> None:
    """015 P2 愿景宣言：蓝点 mono 眉题 + 64px 陈述句 + 说明段。"""
    add_rect(slide, 0, 0, 13.333, 7.5, theme["cover_bg"])
    muted = theme["muted"]
    label = str(item.get("kicker") or "").strip() or f"Part {part_no:02d}"
    add_oval(slide, _in(150) + 0.02, _in(150) + 0.06, 0.08, 0.08,
             theme["accent"])
    kb = add_textbox(slide, _in(150) + 0.2, _in(150), 9.0, 0.32)
    kp = kb.text_frame.paragraphs[0]
    set_run(kp.add_run(), _pt(13.5), muted, font=_mono(),
            letter_spacing_pt=_pt(13.5 * 0.14))
    kp.runs[0].text = label
    heading = str(item.get("heading") or item.get("title") or "")
    size = pick_size(heading, 10.2, 2.2, [48, 42, 36, 32])
    box = add_textbox(slide, _in(150), 2.45, 10.2, 2.3)
    p = box.text_frame.paragraphs[0]
    p.line_spacing = 1.36
    set_run(p.add_run(), size, theme["cover_text"], bold=True,
            font=theme["font"])
    p.runs[0].text = heading
    sub = str(item.get("subtitle") or item.get("body") or "").strip()
    if sub:
        s_box = add_textbox(slide, _in(150), 4.95, 6.67, 1.2)
        sp = s_box.text_frame.paragraphs[0]
        sp.line_spacing = 2.0
        set_run(sp.add_run(), _pt(16.5), muted, font=theme["font"])
        sp.runs[0].text = sub


def _quote(slide: Any, theme: dict[str, Any], st: dict[str, Any],
           item: dict[str, Any], index: int) -> None:
    if _is_devconf(theme):
        add_rect(slide, 0, 0, 13.333, 7.5, theme["content_bg"])
        _foot_devconf(slide, theme, st, index)
    else:
        add_rect(slide, 0, 0, 13.333, 7.5, theme["content_bg"])
        _foot_keynote(slide, theme, st, index)
    ink, muted = theme["text"], theme["muted"]
    label = str(item.get("kicker") or "Quote").strip()
    add_oval(slide, _in(72) + 0.02, _in(64) + 0.08, 0.09, 0.09, theme["accent"])
    kb = add_textbox(slide, _in(72) + 0.2, _in(64), 9.0, 0.3)
    kp = kb.text_frame.paragraphs[0]
    set_run(kp.add_run(), _pt(13.5), muted, font=_mono(),
            letter_spacing_pt=_pt(13.5 * 0.22))
    kp.runs[0].text = label.upper()
    quote = str(item.get("heading") or item.get("quote") or "")
    size = pick_size(quote, 10.6, 2.2, [_pt(58), _pt(50), _pt(44), _pt(38)])
    box = add_textbox(slide, _in(130), 2.45, 10.6, 2.2)
    p = box.text_frame.paragraphs[0]
    p.line_spacing = 1.42
    set_run(p.add_run(), size, ink, bold=True, font=theme["font"])
    p.runs[0].text = quote
    attribution = str(item.get("subtitle") or "").strip()
    if attribution:
        a_box = add_textbox(slide, _in(130), 5.15, 10.6, 0.4)
        ap = a_box.text_frame.paragraphs[0]
        set_run(ap.add_run(), _pt(14.5), muted, font=_mono(),
                letter_spacing_pt=0.8)
        ap.runs[0].text = f"— {attribution}"


# ---------------------------------------------------------------- 编号行（要点 / 里程碑）

def _why_rows(slide: Any, theme: dict[str, Any], st: dict[str, Any],
              item: dict[str, Any], index: int) -> None:
    """016 P11 why-item：mono 34px 细体蓝编号 + 21px/800 标题 + 14.5px 说明，
    行间发丝线。要点页 / 里程碑页通用（015/016 没有时间轴页）。"""
    if _is_devconf(theme):
        _head_devconf(slide, theme, st, item, index)
        line = blend("FFFFFF", theme["text"], 0.12)
    else:
        _head_keynote(slide, theme, st, item, index)
        line = blend(theme["content_bg"], "FFFFFF", 0.14)
    points = _points_of(item, 5) or ["（本页暂无内容）"]
    top = _in(196)
    bottom = 6.82
    row_h = (bottom - top) / len(points)
    for i, raw in enumerate(points):
        if _is_devconf(theme):
            # 016 P11 三段式：'理由|两句话展开|关键数据胶囊'
            parts = [p.strip() for p in str(raw).split("|")]
            main = parts[0]
            note = parts[1] if len(parts) > 1 else ""
            pill_text = parts[2] if len(parts) > 2 else ""
        else:
            main, note = split_title_desc(raw)
            pill_text = ""
        y = top + i * row_h
        n_box = add_textbox(slide, _in(72), y + 0.08, _in(70) + 0.2, 0.62)
        np_ = n_box.text_frame.paragraphs[0]
        set_run(np_.add_run(), _pt(34), theme["accent"], bold=False,
                font=_mono())
        np_.runs[0].text = f"{i + 1:02d}"
        body_x = _in(72) + _in(70) + 0.28
        body_w = 11.89 - _in(70) - 0.3
        # 固定纵向节奏：标题区 0.42 → 说明区 0.55（≤2 行）→ 胶囊 → 底部净空
        p_box = add_textbox(slide, body_x, y + 0.08, body_w, 0.42)
        pp = p_box.text_frame.paragraphs[0]
        m_run = pp.add_run()
        set_run(m_run, _pt(21), theme["text"], bold=True, font=theme["font"])
        m_run.text = main
        if note:
            n_box = add_textbox(slide, body_x, y + 0.52, body_w, 0.55)
            n_par = n_box.text_frame.paragraphs[0]
            n_par.line_spacing = 1.35
            n_run = n_par.add_run()
            set_run(n_run, _pt(14), theme["muted"], font=theme["font"])
            n_run.text = note
        if pill_text:
            # 016 .w-data：蓝描边 mono 数据胶囊，位于说明下方
            pill_w = 0.5 + len(pill_text) * 0.095
            pill = add_pill(slide, body_x, y + 1.14, pill_w, 0.34,
                            theme["content_bg"])
            pill.line.color.rgb = rgb(theme["accent"])
            pill.line.width = Pt(1)
            ptf = pill.text_frame
            ptf.vertical_anchor = MSO_ANCHOR.MIDDLE
            dpp = ptf.paragraphs[0]
            dpp.alignment = PP_ALIGN.CENTER
            set_run(dpp.add_run(), _pt(12.5), theme["accent"], font=_mono(),
                    letter_spacing_pt=0.3)
            dpp.runs[0].text = pill_text
        if i < len(points) - 1:
            add_rect(slide, _in(72), y + row_h - 0.03, 11.89, 0.01, line)


# ---------------------------------------------------------------- 数据带 / 卡片网格

def _kpi(slide: Any, theme: dict[str, Any], st: dict[str, Any],
         item: dict[str, Any], index: int) -> None:
    if _is_devconf(theme):
        _strip_devconf(slide, theme, st, item, index)
    else:
        _strip_keynote(slide, theme, st, item, index)


def _strip_devconf(slide: Any, theme: dict[str, Any], st: dict[str, Any],
                   item: dict[str, Any], index: int) -> None:
    """016 P3 品牌数据带：2px 近黑顶线 + mono 38px 数值 + 单元分隔线 +
    蓝描边 delta 胶囊 + 可选引用条。"""
    _head_devconf(slide, theme, st,
                  {k: v for k, v in item.items() if k != "subtitle"}, index)
    points = _points_of(item, 4) or ["--|待补充"]
    n = len(points)
    strip_top = _in(212)
    # 底线贴内容（数值+标签 ≈1.45in），竖线随之收缩——原型 .strip 是自适应表格，
    # 固定撑到底会产生超长竖线与大片空块
    strip_bottom = strip_top + 1.45
    add_rect(slide, _in(72), strip_top, 11.89, _in(2), theme["text"])
    add_rect(slide, _in(72), strip_bottom, 11.89, 0.01,
             blend("FFFFFF", theme["text"], 0.12))
    cell_w = 11.89 / n
    for i, raw in enumerate(points):
        parts = [part.strip() for part in raw.split("|")]
        value = parts[0] or "--"
        label = parts[1] if len(parts) > 1 else ""
        delta = parts[2] if len(parts) > 2 else ""
        x = _in(72) + i * cell_w
        if i:
            add_rect(slide, x, strip_top + 0.24, 0.01,
                     strip_bottom - strip_top - 0.48,
                     blend("FFFFFF", theme["text"], 0.1))
        pad_x = x + (0.02 if i == 0 else _in(20))
        v_box = add_textbox(slide, pad_x, strip_top + _in(22), cell_w - _in(28),
                            0.72)
        vp = v_box.text_frame.paragraphs[0]
        # 占位符 {{}} 会破坏数字切分：先剥花括号再找数字前缀，
        # 保证数值永远以 38px 粗体渲染（016 .kv 大+粗）
        clean = value.replace("{{", "").replace("}}", "")
        digits, unit = clean, ""
        for j, ch in enumerate(clean):
            if not ch.isdigit() and ch not in ".,+%":
                digits, unit = clean[:j], clean[j:]
                break
        if digits:
            d_run = vp.add_run()
            set_run(d_run, _pt(38), theme["text"], bold=True, font=_mono(),
                    letter_spacing_pt=-0.2)
            d_run.text = digits
        if unit:
            u_run = vp.add_run()
            set_run(u_run, _pt(15), theme["muted"], bold=True,
                    font=theme["font"])
            u_run.text = unit
        if label:
            l_box = add_textbox(slide, pad_x, strip_top + _in(22) + 0.78,
                                cell_w - _in(28), 0.35)
            lp = l_box.text_frame.paragraphs[0]
            set_run(lp.add_run(), _pt(13.5), theme["muted"], font=theme["font"])
            lp.runs[0].text = label
        if delta:
            pill_w = 0.5 + len(delta) * 0.085
            pill = add_pill(slide, pad_x, strip_top + _in(22) + 1.22, pill_w,
                            0.4, theme["content_bg"])
            pill.line.color.rgb = rgb(theme["accent"])
            pill.line.width = Pt(1)
            ptf = pill.text_frame
            ptf.vertical_anchor = MSO_ANCHOR.MIDDLE
            pp = ptf.paragraphs[0]
            pp.alignment = PP_ALIGN.CENTER
            set_run(pp.add_run(), _pt(13.5), theme["accent"], font=_mono(),
                    letter_spacing_pt=0.5)
            pp.runs[0].text = delta
    sub = str(item.get("subtitle") or "").strip()
    if sub:
        add_rect(slide, _in(72), _in(470), 11.89, 0.01,
                 blend("FFFFFF", theme["text"], 0.12))
        q_box = add_textbox(slide, _in(72), _in(470) + 0.22, 11.89, 0.9)
        qp = q_box.text_frame.paragraphs[0]
        qp.line_spacing = 1.9
        set_run(qp.add_run(), _pt(17), blend("FFFFFF", theme["text"], 0.72),
                font=theme["font"])
        qp.runs[0].text = sub


def _overview_devconf(slide: Any, theme: dict[str, Any], st: dict[str, Any],
                      item: dict[str, Any], index: int,
                      resolve_media: Callable[[str], Any] | None = None) -> None:
    """016 P4 产品全景：head + 通栏架构图占位框（可放真实架构图）+ 底部聚焦 cap 行。"""
    _head_devconf(slide, theme, st, item, index)
    frame_top = _in(196)
    frame_h = 7.5 - 1.35 - frame_top  # bottom:130px
    image = item.get("image")
    if resolve_media is not None and isinstance(image, dict):
        # 有真实架构图：图片直接铺满占位框
        from .layouts import _media_block
        add_rect(slide, _in(72), frame_top, 11.89, frame_h, "FAFBFC")
        _media_block(slide, theme, {}, image, _in(72) + 0.1, frame_top + 0.1,
                     11.89 - 0.2, frame_h - 0.2, resolve_media)
    else:
        frame = add_rect(slide, _in(72), frame_top, 11.89, frame_h,
                         blend("FFFFFF", theme["text"], 0.02))
        frame.line.color.rgb = rgb(blend("FFFFFF", theme["text"], 0.14))
        frame.line.width = Pt(1)
        ptf = frame.text_frame
        ptf.vertical_anchor = MSO_ANCHOR.MIDDLE
        fp = ptf.paragraphs[0]
        fp.alignment = PP_ALIGN.CENTER
        set_run(fp.add_run(), _pt(13.5), theme["muted"], font=_mono(),
                letter_spacing_pt=_pt(13.5 * 0.2))
        fp.runs[0].text = str(item.get("body") or "").strip() \
            or "产品架构图 / 模块全景图位（建议：分层模块图，宽 1136mm）"
    points = _points_of(item, 1)
    if points:
        main, note = split_title_desc(points[0])
        cap = add_textbox(slide, _in(72), 6.42, 11.89, 0.4)
        cp = cap.text_frame.paragraphs[0]
        m_run = cp.add_run()
        set_run(m_run, _pt(14), theme["text"], bold=True, font=theme["font"])
        m_run.text = main
        if note:
            n_run = cp.add_run()
            set_run(n_run, _pt(14), theme["muted"], font=theme["font"])
            n_run.text = f"　{note}"


def _metrics_devconf(slide: Any, theme: dict[str, Any], st: dict[str, Any],
                     item: dict[str, Any], index: int) -> None:
    """016 P9 增长指标：KPI 三栏（数据带同款顶线组件）+ a/b/c 增长引擎列表。
    points 前 3 条为 '数值|标签|涨跌' KPI，其余为 '引擎名|描述' 增长引擎。"""
    _head_devconf(slide, theme, st, item, index)
    points = _points_of(item, 8)
    kpis = points[:3] or ["--|待补充"]
    engines = points[3:6]

    # ── KPI 三栏：2px 近黑顶线 + 单元分隔线 + mono 数值 + 蓝色涨跌行 ──
    strip_top = _in(196)
    strip_bottom = _in(420)
    add_rect(slide, _in(72), strip_top, 11.89, _in(2), theme["text"])
    add_rect(slide, _in(72), strip_bottom, 11.89, 0.01,
             blend("FFFFFF", theme["text"], 0.12))
    cell_w = 11.89 / len(kpis)
    for i, raw in enumerate(kpis):
        parts = [part.strip() for part in raw.split("|")]
        value = parts[0] or "--"
        label = parts[1] if len(parts) > 1 else ""
        delta = parts[2] if len(parts) > 2 else ""
        x = _in(72) + i * cell_w
        if i:
            add_rect(slide, x, strip_top + 0.2, 0.01,
                     strip_bottom - strip_top - 0.4,
                     blend("FFFFFF", theme["text"], 0.1))
        pad_x = x + (0.02 if i == 0 else _in(20))
        digits, unit = value, ""
        for j, ch in enumerate(value):
            if not ch.isdigit() and ch not in ".,+%":
                digits, unit = value[:j], value[j:]
                break
        v_box = add_textbox(slide, pad_x, strip_top + _in(24), cell_w - _in(28), 0.66)
        vp = v_box.text_frame.paragraphs[0]
        if digits:
            d_run = vp.add_run()
            set_run(d_run, _pt(34), theme["text"], bold=True, font=_mono(),
                    letter_spacing_pt=-0.2)
            d_run.text = digits
        if unit:
            u_run = vp.add_run()
            set_run(u_run, _pt(14), theme["muted"], bold=True, font=theme["font"])
            u_run.text = unit
        if delta:
            kd = add_textbox(slide, pad_x, strip_top + _in(24) + 0.6,
                             cell_w - _in(28), 0.32)
            kp = kd.text_frame.paragraphs[0]
            set_run(kp.add_run(), _pt(13), theme["accent"], font=_mono(),
                    letter_spacing_pt=0.4)
            kp.runs[0].text = f"▲ {delta}" if delta and not delta.startswith(("▲", "+")) else delta
        if label:
            l_box = add_textbox(slide, pad_x, strip_top + _in(24) + 0.94,
                                cell_w - _in(28), 0.35)
            lp = l_box.text_frame.paragraphs[0]
            set_run(lp.add_run(), _pt(13.5), theme["muted"], font=theme["font"])
            lp.runs[0].text = label

    # ── a/b/c 增长引擎列表：mono 小写字母编号 + 粗体前缀 + 灰色说明 ──
    if not engines:
        return
    line = blend("FFFFFF", theme["text"], 0.12)
    list_top = _in(452)
    row_h = (6.82 - list_top) / max(len(engines), 1)
    for i, raw in enumerate(engines):
        main, note = split_title_desc(raw)
        y = list_top + i * row_h
        # 行内容垂直居中于行高内，与上下发丝线各留净空
        n_box = add_textbox(slide, _in(72), y + row_h / 2 - 0.18, 0.45, 0.35)
        np_ = n_box.text_frame.paragraphs[0]
        set_run(np_.add_run(), _pt(13), theme["muted"], font=_mono())
        np_.runs[0].text = f"{chr(ord('a') + i)}."
        t_box = add_textbox(slide, _in(72) + 0.55, y + row_h / 2 - 0.22,
                            11.3, row_h - 0.24)
        tp = t_box.text_frame.paragraphs[0]
        tp.line_spacing = 1.3
        m_run = tp.add_run()
        set_run(m_run, _pt(15), theme["text"], bold=True, font=theme["font"])
        m_run.text = main
        if note:
            n_run = tp.add_run()
            set_run(n_run, _pt(14), theme["muted"], font=theme["font"])
            n_run.text = f"　{note}"
        if i < len(engines) - 1:
            add_rect(slide, _in(72), y + row_h - 0.02, 11.89, 0.01, line)


def _strip_keynote(slide: Any, theme: dict[str, Any], st: dict[str, Any],
                   item: dict[str, Any], index: int) -> None:
    """015 P5 性能数据：mono 眉题 + 46px 标题 + 顶部发丝线三列贴底
    （64px 细体数值 + 粗体标签 + 灰色说明）。"""
    _head_keynote(slide, theme, st, item, index)
    points = _points_of(item, 3) or ["--|待补充"]
    n = len(points)
    gap = _in(40)
    stats_top = 7.5 - _in(96) - 2.2
    add_rect(slide, _in(96), stats_top, 13.333 - 2 * _in(96), 0.012,
             blend(theme["content_bg"], "FFFFFF", 0.14))
    col_w = (13.333 - 2 * _in(96) - gap * (n - 1)) / n
    for i, raw in enumerate(points):
        parts = [part.strip() for part in raw.split("|")]
        value = parts[0] or "--"
        label = parts[1] if len(parts) > 1 else ""
        desc = parts[2] if len(parts) > 2 else ""
        x = _in(96) + i * (col_w + gap)
        v_box = add_textbox(slide, x, stats_top + _in(26), col_w, 0.85)
        vp = v_box.text_frame.paragraphs[0]
        digits, unit = value, ""
        for j, ch in enumerate(value):
            if not ch.isdigit() and ch not in ".,+%":
                digits, unit = value[:j], value[j:]
                break
        if digits:
            d_run = vp.add_run()
            set_run(d_run, _pt(64), theme["text"], bold=False,
                    font=theme["font"])
            d_run.text = digits
        if unit:
            u_run = vp.add_run()
            set_run(u_run, _pt(22), theme["text"], bold=True,
                    font=theme["font"])
            u_run.text = unit
        if label:
            l_box = add_textbox(slide, x, stats_top + _in(26) + 0.95, col_w,
                                0.4)
            lp = l_box.text_frame.paragraphs[0]
            set_run(lp.add_run(), _pt(16), theme["text"], bold=True,
                    font=theme["font"])
            lp.runs[0].text = label
        if desc:
            d_box = add_textbox(slide, x, stats_top + _in(26) + 1.38, col_w,
                                0.35)
            dp = d_box.text_frame.paragraphs[0]
            set_run(dp.add_run(), _pt(13.5), theme["muted"], font=theme["font"])
            dp.runs[0].text = desc


def _cards(slide: Any, theme: dict[str, Any], st: dict[str, Any],
           item: dict[str, Any], index: int) -> None:
    if _is_devconf(theme):
        _fcards_devconf(slide, theme, st, item, index)
    else:
        _tcards_keynote(slide, theme, st, item, index)


def _fcards_devconf(slide: Any, theme: dict[str, Any], st: dict[str, Any],
                    item: dict[str, Any], index: int) -> None:
    """016 P5 功能总览：3 列白底发丝边卡（mono FEATURE NN 眉题 +
    19.5px/800 标题 + 13.5px 描述）。"""
    _head_devconf(slide, theme, st, item, index)
    points = _points_of(item, 6) or ["暂无内容"]
    gap = _in(18)
    cols = 3
    card_w = (11.89 - gap * (cols - 1)) / cols
    rows = (len(points) + cols - 1) // cols
    top = _in(196)
    card_h = min((6.75 - top - gap * (rows - 1)) / rows, 2.05)
    line = blend("FFFFFF", theme["text"], 0.1)
    faint = blend("FFFFFF", theme["text"], 0.3)
    for i, raw in enumerate(points):
        title, desc = split_title_desc(raw)
        col, row = i % cols, i // cols
        x = _in(72) + col * (card_w + gap)
        y = top + row * (card_h + gap)
        card = add_rect(slide, x, y, card_w, card_h, "FFFFFF", rounded=True,
                        radius=0.09)
        card.line.color.rgb = rgb(line)
        card.line.width = Pt(1)
        no_box = add_textbox(slide, x + _in(26), y + _in(24), card_w - _in(40),
                             0.26)
        np_ = no_box.text_frame.paragraphs[0]
        set_run(np_.add_run(), _pt(12.5), faint, font=_mono(),
                letter_spacing_pt=_pt(12.5 * 0.18))
        np_.runs[0].text = f"FEATURE {i + 1:02d}"
        t_box = add_textbox(slide, x + _in(26), y + _in(24) + 0.38,
                            card_w - _in(40), 0.42)
        t_size = pick_size(title, card_w - _in(40), 0.42, [_pt(19.5), 13, 12])
        tp = t_box.text_frame.paragraphs[0]
        set_run(tp.add_run(), t_size, theme["text"], bold=True,
                font=theme["font"])
        tp.runs[0].text = title
        if desc:
            d_box = add_textbox(slide, x + _in(26), y + _in(24) + 0.86,
                                card_w - _in(40), card_h - _in(24) - 1.0)
            dp = d_box.text_frame.paragraphs[0]
            dp.line_spacing = 1.65
            d_size = pick_size(desc, card_w - _in(40), card_h - _in(24) - 1.0,
                               [_pt(13.5), 10, 9.5])
            set_run(dp.add_run(), d_size, theme["muted"], font=theme["font"])
            dp.runs[0].text = desc


def _tcards_keynote(slide: Any, theme: dict[str, Any], st: dict[str, Any],
                    item: dict[str, Any], index: int) -> None:
    """015 P4 特性三卡：深灰圆角卡（微光边）+ 蓝色图标块 + 标题 + 描述。"""
    _head_keynote(slide, theme, st, item, index)
    points = _points_of(item, 3) or ["暂无内容"]
    gap = _in(22)
    cards_top = 7.5 - _in(96) - 2.35
    card_w = (13.333 - 2 * _in(96) - gap * (len(points) - 1)) / len(points)
    card_h = 2.35
    line = blend(theme["content_bg"], "FFFFFF", 0.09)
    for i, raw in enumerate(points):
        title, desc = split_title_desc(raw)
        x = _in(96) + i * (card_w + gap)
        card = add_rect(slide, x, cards_top, card_w, card_h,
                        theme["accent_light"], rounded=True, radius=0.12)
        card.line.color.rgb = rgb(line)
        card.line.width = Pt(1)
        add_rect(slide, x + _in(28), cards_top + _in(26), 0.34, 0.34,
                 theme["accent"], rounded=True, radius=0.24)
        add_star4(slide, x + _in(28) + 0.095, cards_top + _in(26) + 0.095,
                  0.15, "FFFFFF")
        ty = cards_top + _in(26) + 0.62
        t_box = add_textbox(slide, x + _in(28), ty, card_w - _in(40), 0.4)
        t_size = pick_size(title, card_w - _in(40), 0.4, [_pt(16), 12])
        tp = t_box.text_frame.paragraphs[0]
        set_run(tp.add_run(), t_size, theme["text"], bold=True,
                font=theme["font"])
        tp.runs[0].text = title
        if desc:
            d_box = add_textbox(slide, x + _in(28), ty + 0.46, card_w - _in(40),
                                card_h - _in(28) - 1.08)
            dp = d_box.text_frame.paragraphs[0]
            dp.line_spacing = 1.75
            d_size = pick_size(desc, card_w - _in(40),
                               card_h - _in(28) - 1.08, [_pt(13.5), 10, 9.5])
            set_run(dp.add_run(), d_size, theme["muted"], font=theme["font"])
            dp.runs[0].text = desc


# ---------------------------------------------------------------- 深潜 / 对比 / 表格 / 图表

def _two_col(slide: Any, theme: dict[str, Any], st: dict[str, Any],
             item: dict[str, Any], index: int,
             resolve_media: Callable[[str], Any] | None) -> None:
    if _is_devconf(theme):
        _deep_dive(slide, theme, st, item, index, resolve_media)
    else:
        # 015 无深潜构图：按编号行呈现（015 页面均为大字排版）
        _why_rows(slide, theme, st, item, index)


def _deep_dive(slide: Any, theme: dict[str, Any], st: dict[str, Any],
               item: dict[str, Any], index: int,
               resolve_media: Callable[[str], Any] | None) -> None:
    """016 P6/P7 深潜页：56% 截图框 + 编号 + 标题 + 字母要点。
    image_side=left（默认，016 P6 图左文右）/ right（016 P7 镜像：图右文左）。"""
    # 原型 P6/P7 的 head 只有 kicker：标题/描述属于下方文案区，不重复渲染
    _head_devconf(slide, theme, st, {"kicker": item.get("kicker") or ""}, index)
    top = _in(196)
    bottom = 6.75
    shot_w = 11.89 * 0.56
    side = str(item.get("image_side") or item.get("side") or "left").strip().lower()
    if side == "right":
        shot_x = _in(72) + 11.89 - shot_w
        copy_x = _in(72)
    else:
        shot_x = _in(72)
        copy_x = _in(72) + shot_w + _in(44)
    copy_w = 11.89 - shot_w - _in(44)
    frame = add_rect(slide, shot_x, top, shot_w, bottom - top, "FAFBFC",
                     rounded=True, radius=0.06)
    frame.line.color.rgb = rgb(blend("FFFFFF", theme["text"], 0.1))
    frame.line.width = Pt(1)
    hint = add_textbox(slide, shot_x, top + (bottom - top) / 2 - 0.15,
                       shot_w, 0.3)
    hint.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    set_run(hint.text_frame.paragraphs[0].add_run(), _pt(13),
            blend("FFFFFF", theme["text"], 0.3), font=_mono(),
            letter_spacing_pt=_pt(13 * 0.18))
    hint.text_frame.paragraphs[0].runs[0].text = "SCREENSHOT / DEMO"
    image = item.get("image")
    if resolve_media is not None and isinstance(image, dict):
        from .layouts import _media_block
        _media_block(slide, theme, {}, image, shot_x + 0.15, top + 0.15,
                     shot_w - 0.3, bottom - top - 0.3, resolve_media)
    feat = str(item.get("feature") or "").strip()
    name = f"FEATURE {max(index - 5, 1):02d}" + (f" · {feat}" if feat else "")
    cy = top + 0.15
    if name:
        n_box = add_textbox(slide, copy_x, cy, copy_w, 0.3)
        np_ = n_box.text_frame.paragraphs[0]
        set_run(np_.add_run(), _pt(13), theme["accent"], font=_mono(),
                letter_spacing_pt=_pt(13 * 0.18))
        np_.runs[0].text = name.upper()
        cy += 0.45
    title = str(item.get("heading") or item.get("title") or "")
    t_size = pick_size(title, copy_w, 0.85, [_pt(26), _pt(22), 15])
    t_box = add_textbox(slide, copy_x, cy, copy_w, 0.9)
    tp = t_box.text_frame.paragraphs[0]
    tp.line_spacing = 1.2
    set_run(tp.add_run(), t_size, theme["text"], bold=True, font=theme["font"])
    tp.runs[0].text = title
    cy += 1.0
    desc = str(item.get("subtitle") or item.get("body") or "").strip()
    if desc:
        d_box = add_textbox(slide, copy_x, cy, copy_w, 0.85)
        dp = d_box.text_frame.paragraphs[0]
        dp.line_spacing = 1.6
        d_size = pick_size(desc, copy_w, 0.85, [_pt(14.5), 11.5, 11])
        set_run(dp.add_run(), d_size, theme["muted"], font=theme["font"])
        dp.runs[0].text = desc
        cy += 1.0
    for i, raw in enumerate(_points_of(item, 3)):
        main, note = split_title_desc(raw)
        py = cy + i * 0.62
        n_box = add_textbox(slide, copy_x, py, 0.4, 0.35)
        np_ = n_box.text_frame.paragraphs[0]
        set_run(np_.add_run(), _pt(13), theme["accent"], bold=True,
                font=_mono())
        np_.runs[0].text = f"{_letters(3)[i]}."
        p_box = add_textbox(slide, copy_x + 0.4, py, copy_w - 0.4, 0.6)
        pp = p_box.text_frame.paragraphs[0]
        m_run = pp.add_run()
        set_run(m_run, _pt(14.5), theme["text"], bold=True, font=theme["font"])
        m_run.text = main
        if note:
            n_run = pp.add_run()
            set_run(n_run, _pt(11), theme["muted"], font=theme["font"])
            n_run.text = f"　{note}"


def _compare(slide: Any, theme: dict[str, Any], st: dict[str, Any],
             item: dict[str, Any], index: int) -> None:
    if _is_devconf(theme):
        _head_devconf(slide, theme, st, item, index)
        panel_fill = "FFFFFF"
        line = blend("FFFFFF", theme["text"], 0.12)
    else:
        _head_keynote(slide, theme, st, item, index)
        panel_fill = theme["accent_light"]
        line = blend(theme["content_bg"], "FFFFFF", 0.09)
    ink, muted = theme["text"], theme["muted"]
    left = item.get("left") if isinstance(item.get("left"), dict) else {}
    right = item.get("right") if isinstance(item.get("right"), dict) else {}
    gap = _in(24)
    panel_w = (11.89 - gap) / 2
    top = _in(196)
    bottom = 6.7
    for i, side in enumerate((left, right)):
        x = _in(72) + i * (panel_w + gap)
        panel = add_rect(slide, x, top, panel_w, bottom - top, panel_fill,
                         rounded=bool(st.get("card_radius")),
                         radius=float(st.get("card_radius") or 0.07))
        border_target = ("FFFFFF" if not is_light(panel_fill)
                         else theme["text"])
        panel.line.color.rgb = rgb(blend(panel_fill, border_target, 0.12))
        panel.line.width = Pt(1)
        title = str(side.get("title") or ("方案 " + "AB"[i]))
        t_box = add_textbox(slide, x + _in(26), top + _in(24), panel_w
                            - _in(90), 0.42)
        tp = t_box.text_frame.paragraphs[0]
        set_run(tp.add_run(), _pt(19.5), ink, bold=True, font=theme["font"])
        tp.runs[0].text = title
        tag = add_textbox(slide, x + panel_w - _in(90), top + _in(28), 0.8,
                          0.3)
        tp2 = tag.text_frame.paragraphs[0]
        tp2.alignment = PP_ALIGN.RIGHT
        set_run(tp2.add_run(), _pt(12), muted, font=_mono(),
                letter_spacing_pt=_pt(12 * 0.18))
        tp2.runs[0].text = ["LEFT", "RIGHT"][i]
        pts = [str(p) for p in (side.get("points") or []) if str(p).strip()][:5]
        py = top + _in(24) + 0.62
        for j, raw in enumerate(pts):
            main, note = split_title_desc(raw)
            n_box = add_textbox(slide, x + _in(26), py, 0.4, 0.35)
            np_ = n_box.text_frame.paragraphs[0]
            set_run(np_.add_run(), _pt(13), theme["accent"], bold=True,
                    font=_mono())
            np_.runs[0].text = f"{_letters(len(pts))[j]}."
            p_box = add_textbox(slide, x + _in(26) + 0.42, py, panel_w
                                - _in(52), 0.42)
            pp = p_box.text_frame.paragraphs[0]
            m_run = pp.add_run()
            set_run(m_run, _pt(13.5), ink, font=theme["font"])
            m_run.text = main
            if note:
                n_run = pp.add_run()
                set_run(n_run, _pt(11), muted, font=theme["font"])
                n_run.text = f"　{note}"
            py += 0.52
            if j < len(pts) - 1:
                add_rect(slide, x + _in(26), py - 0.08, panel_w - _in(52),
                         0.01, line)


def _table(slide: Any, theme: dict[str, Any], st: dict[str, Any],
           item: dict[str, Any], index: int) -> None:
    """016 P10 竞品对比表：第 2 列（本品）表头蓝底反白 + 本品行浅灰底加粗；
    ✓ 蓝色 mono / ✕ 浅灰；顶/底 2px 近黑粗线。自带实现，不依赖通用 tables.py。"""
    head_item = {k: v for k, v in item.items() if k != "subtitle"}
    _head_devconf(slide, theme, st, head_item, index)
    spec = item.get("table") if isinstance(item.get("table"), dict) else {}
    columns = [str(c) for c in (spec.get("columns") or [])][:6]
    rows = [[str(cell) for cell in row] for row in (spec.get("rows") or [])][:8]
    rows = [row[:len(columns)] + [""] * (len(columns) - len(row))
            for row in rows]
    us_col = 1 if len(columns) >= 2 else -1  # 本品列固定第 2 列
    tbl_h = 0.52 + 0.44 * len(rows)
    frame = slide.shapes.add_table(len(rows) + 1, len(columns),
                                   Inches(_in(72)), Inches(_in(230)),
                                   Inches(11.89), Inches(tbl_h))
    table = frame.table
    table.first_row = False
    table.horz_banding = False
    us_body_fill = blend("FFFFFF", theme["text"], 0.04)  # ≈ #F4F5F6
    for c, label in enumerate(columns):
        cell = table.cell(0, c)
        cell.fill.solid()
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = cell.text_frame.paragraphs[0]
        run = p.add_run()
        if c == us_col:
            # 016 th.us：本品列表头蓝底反白
            cell.fill.fore_color.rgb = rgb(theme["accent"])
            set_run(run, _pt(12.5), "FFFFFF", bold=True, font=_mono(),
                    letter_spacing_pt=1.0)
        else:
            cell.fill.fore_color.rgb = rgb(theme["content_bg"])
            set_run(run, _pt(12.5),
                    theme["text"] if c == 0
                    else blend(theme["text"], "FFFFFF", 0.35),
                    bold=True, font=_mono(), letter_spacing_pt=1.0)
        run.text = label.upper()
    for r, row in enumerate(rows, start=1):
        for c, value in enumerate(row):
            cell = table.cell(r, c)
            cell.fill.solid()
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.fore_color.rgb = rgb(
                us_body_fill if c == us_col else theme["content_bg"])
            p = cell.text_frame.paragraphs[0]
            if value.startswith(("✓", "✕")):
                # 016 .yes/.no：符号 mono 粗体（✓ 主题蓝 / ✕ 浅灰）+ 后续说明
                symbol, rest = value[0], value[1:].strip()
                s_run = p.add_run()
                set_run(s_run, _pt(13.5),
                        theme["accent"] if symbol == "✓"
                        else blend(theme["text"], "FFFFFF", 0.45),
                        bold=True, font=_mono())
                s_run.text = f"{symbol} "
                if rest:
                    r_run = p.add_run()
                    set_run(r_run, _pt(13),
                            theme["text"] if c == us_col
                            else blend(theme["text"], "FFFFFF", 0.25),
                            bold=(c == us_col), font=theme["font"])
                    r_run.text = rest
            else:
                run = p.add_run()
                bold = c == us_col
                set_run(run, _pt(13.5),
                        theme["text"] if c in (0, us_col)
                        else blend(theme["text"], "FFFFFF", 0.25),
                        bold=bold, font=theme["font"])
                run.text = value
    # 顶/底 2px 近黑粗线（原型 thead 上下边）
    add_rect(slide, _in(72), _in(230) - 0.03, 11.89, _in(2), theme["text"])
    add_rect(slide, _in(72), _in(230) + tbl_h + 0.01, 11.89, _in(2), theme["text"])
    # 底部注记行（016 .vs-note）
    note = str(item.get("subtitle") or "").strip()
    if note:
        n_box = add_textbox(slide, _in(72), _in(230) + tbl_h + 0.18, 11.89, 0.35)
        np_ = n_box.text_frame.paragraphs[0]
        set_run(np_.add_run(), _pt(12.5), theme["muted"], font=theme["font"])
        np_.runs[0].text = note


def _chart(slide: Any, theme: dict[str, Any], st: dict[str, Any],
           item: dict[str, Any], index: int) -> None:
    from . import charts

    if _is_devconf(theme):
        _head_devconf(slide, theme, st, item, index)
    else:
        _head_keynote(slide, theme, st, item, index)
    spec = item.get("chart") if isinstance(item.get("chart"), dict) else None
    if not spec:
        return
    charts.add_native_chart(slide, theme, spec, _in(72), _in(210),
                            11.89, 4.3)


# ---------------------------------------------------------------- 结尾

def _growth_devconf(slide: Any, theme: dict[str, Any], st: dict[str, Any],
                    item: dict[str, Any], index: int) -> None:
    """016 P8 用户增长：左侧 88px 大数字 + delta 胶囊，右侧圆角图表框
    （有 chart 数据画柱状，否则图表/截图占位提示）。"""
    _head_devconf(slide, theme, st, item, index)
    top = _in(186)
    # ── 左：大数字块（36% 宽）──
    big_w = 11.89 * 0.36
    points = _points_of(item, 1) or ["--|待补充"]
    parts = [p.strip() for p in points[0].split("|")]
    value = parts[0] or "--"
    label = parts[1] if len(parts) > 1 else ""
    delta = parts[2] if len(parts) > 2 else ""
    clean = value.replace("{{", "").replace("}}", "")
    digits, unit = clean, ""
    for j, ch in enumerate(clean):
        if not ch.isdigit() and ch not in ".,+%":
            digits, unit = clean[:j], clean[j:]
            break
    v_box = add_textbox(slide, _in(72), top, big_w, 1.35)
    vp = v_box.text_frame.paragraphs[0]
    if digits:
        d_run = vp.add_run()
        set_run(d_run, _pt(72), theme["text"], bold=True, font=_mono(),
                letter_spacing_pt=-0.6)
        d_run.text = digits
    if unit:
        u_run = vp.add_run()
        set_run(u_run, _pt(28), theme["muted"], bold=False, font=theme["font"])
        u_run.text = unit
    if not digits:
        set_run(vp.add_run(), _pt(48), theme["text"], bold=True, font=_mono())
        vp.runs[0].text = clean
    cy = top + 1.42
    if label:
        k_box = add_textbox(slide, _in(72), cy, big_w, 0.4)
        kp = k_box.text_frame.paragraphs[0]
        set_run(kp.add_run(), _pt(15), theme["muted"], font=theme["font"])
        kp.runs[0].text = label
        cy += 0.5
    if delta:
        pill_w = 0.5 + len(delta) * 0.095
        pill = add_pill(slide, _in(72), cy + 0.05, pill_w, 0.4,
                        theme["content_bg"])
        pill.line.color.rgb = rgb(theme["accent"])
        pill.line.width = Pt(1)
        ptf = pill.text_frame
        ptf.vertical_anchor = MSO_ANCHOR.MIDDLE
        pp = ptf.paragraphs[0]
        pp.alignment = PP_ALIGN.CENTER
        set_run(pp.add_run(), _pt(13.5), theme["accent"], font=_mono(),
                letter_spacing_pt=0.4)
        pp.runs[0].text = delta
    # ── 右：图表框（left:44% → 右边距）──
    chart_x = 0.44 * 13.333
    chart_w = 13.333 - 1.0 - chart_x
    chart_top = top
    chart_h = 7.5 - 1.25 - chart_top
    frame = add_rect(slide, chart_x, chart_top, chart_w, chart_h,
                     blend("FFFFFF", theme["text"], 0.02),
                     rounded=True, radius=0.05)
    frame.line.color.rgb = rgb(blend("FFFFFF", theme["text"], 0.12))
    frame.line.width = Pt(1)
    title = str(item.get("chart_title") or item.get("subtitle") or "").strip()
    chart = item.get("chart") if isinstance(item.get("chart"), dict) else None
    pad = _in(26)
    ty = chart_top + pad
    if title:
        t_box = add_textbox(slide, chart_x + pad, ty, chart_w - 2 * pad, 0.32)
        tp = t_box.text_frame.paragraphs[0]
        set_run(tp.add_run(), _pt(14), theme["text"], bold=True,
                font=theme["font"])
        tp.runs[0].text = title
        ty += 0.34
        unit = str((item.get("chart") or {}).get("unit")
                   or "单位：{{万}} · {{截至本季度}}")
        u_box = add_textbox(slide, chart_x + pad, ty, chart_w - 2 * pad, 0.26)
        up = u_box.text_frame.paragraphs[0]
        set_run(up.add_run(), _pt(11.5), theme["muted"], font=_mono())
        up.runs[0].text = unit
        ty += 0.34
    cats: list[str] = []
    values: list[float] = []
    if chart:
        cats = [str(c) for c in (chart.get("categories") or [])][:8]
        series = chart.get("series") or []
        if series and isinstance(series[0], dict):
            values = [float(v) for v in (series[0].get("values") or [])][:8]
    if values and cats:
        # 柱状：底部对齐，最后一根高亮主题蓝
        area_top = ty + 0.15
        area_h = chart_top + chart_h - pad - 0.5 - area_top
        step = (chart_w - 2 * pad) / len(values)
        bar_w = 0.33
        vmax = max(values) or 1
        base_y = area_top + area_h
        for i, val in enumerate(values):
            bx = chart_x + pad + i * step + (step - bar_w) / 2
            bh = max(0.12, area_h * (val / vmax))
            color = theme["accent"] if i == len(values) - 1 \
                else blend("FFFFFF", theme["accent"], 0.35)
            add_rect(slide, bx, base_y - bh, bar_w, bh, color)
            cv = add_textbox(slide, chart_x + pad + i * step, base_y - bh - 0.28,
                             step, 0.24)
            cvp = cv.text_frame.paragraphs[0]
            cvp.alignment = PP_ALIGN.CENTER
            set_run(cvp.add_run(), _pt(10.5), theme["muted"], font=_mono())
            cvp.runs[0].text = str(int(val)) if float(val).is_integer() else str(val)
            ax = add_textbox(slide, chart_x + pad + i * step, base_y + 0.08,
                             step, 0.24)
            axp = ax.text_frame.paragraphs[0]
            axp.alignment = PP_ALIGN.CENTER
            set_run(axp.add_run(), _pt(10.5), theme["muted"], font=_mono())
            axp.runs[0].text = cats[i] if i < len(cats) else ""
        add_rect(slide, chart_x + pad, base_y, chart_w - 2 * pad, 0.01,
                 blend("FFFFFF", theme["text"], 0.2))
    else:
        ptf = frame.text_frame
        ptf.vertical_anchor = MSO_ANCHOR.MIDDLE
        fp = ptf.paragraphs[0]
        fp.alignment = PP_ALIGN.CENTER
        set_run(fp.add_run(), _pt(13.5), theme["muted"], font=_mono(),
                letter_spacing_pt=_pt(13.5 * 0.16))
        fp.runs[0].text = "{{季度增长柱状图 / 数据截图占位}}"



def _reveal_keynote(slide: Any, theme: dict[str, Any], st: dict[str, Any],
                    item: dict[str, Any], index: int,
                    resolve_media: Callable[[str], Any] | None = None) -> None:
    """015 P3 产品亮相：左上蓝点标签 + 居中产品图占位框 + 左下粗细混排产品名。"""
    _foot_keynote(slide, theme, st, index)
    add_oval(slide, _in(96), _in(72) + 0.07, 0.09, 0.09, theme["accent"])
    tag = add_textbox(slide, _in(96) + 0.2, _in(72) - 0.02, 8.5, 0.3)
    tp = tag.text_frame.paragraphs[0]
    set_run(tp.add_run(), _pt(13), theme["muted"], font=_mono(),
            letter_spacing_pt=_pt(13 * 0.2))
    tp.runs[0].text = str(item.get("kicker") or "NEW · 全新登场")
    # 居中产品框（620×300px）
    fw, fh = 6.46, 3.13
    fx, fy = (13.333 - fw) / 2, _in(150)
    card = add_rect(slide, fx, fy, fw, fh,
                    blend(theme["cover_bg"], "FFFFFF", 0.03),
                    rounded=True, radius=0.14)
    card.line.color.rgb = rgb(blend(theme["cover_bg"], "FFFFFF", 0.12))
    card.line.width = Pt(1)
    image = item.get("image")
    if resolve_media is not None and isinstance(image, dict):
        from .layouts import _media_block
        _media_block(slide, theme, {}, image, fx + 0.12, fy + 0.12,
                     fw - 0.24, fh - 0.24, resolve_media)
    else:
        ptf = card.text_frame
        ptf.vertical_anchor = MSO_ANCHOR.MIDDLE
        fp = ptf.paragraphs[0]
        fp.alignment = PP_ALIGN.CENTER
        set_run(fp.add_run(), _pt(13), blend(theme["cover_bg"], theme["text"], 0.35),
                font=_mono(), letter_spacing_pt=_pt(13 * 0.3))
        fp.runs[0].text = str(item.get("body") or "").strip() or "PRODUCT RENDER / 产品渲染图"
    # 左下名称块：kicker + 粗细混排 h2（heading 用 | 分隔 细|粗）+ slogan
    nx = _in(96)
    ky = 4.92
    kick = str(item.get("feature") or item.get("kicker") or "").strip()
    if kick:
        k_box = add_textbox(slide, nx, ky, 10.0, 0.3)
        kp = k_box.text_frame.paragraphs[0]
        set_run(kp.add_run(), _pt(13.5), theme["muted"], font=_mono(),
                letter_spacing_pt=_pt(13.5 * 0.32))
        kp.runs[0].text = kick.upper()
    heading = str(item.get("heading") or item.get("title") or "")
    h_box = add_textbox(slide, nx, ky + 0.38, 11.4, 0.95)
    hp = h_box.text_frame.paragraphs[0]
    if "|" in heading:
        thin, bold = (seg.strip() for seg in heading.split("|", 1))
    else:
        thin, bold = "", heading
    if thin:
        t_run = hp.add_run()
        set_run(t_run, _pt(46), theme["text"], bold=False, font=theme["font"])
        t_run.text = thin + " "
    b_run = hp.add_run()
    set_run(b_run, _pt(46), theme["text"], bold=True, font=theme["font"])
    b_run.text = bold
    slogan = str(item.get("subtitle") or "").strip()
    if slogan:
        s_box = add_textbox(slide, nx, ky + 1.38, 10.5, 0.4)
        sp = s_box.text_frame.paragraphs[0]
        set_run(sp.add_run(), _pt(12.75), theme["muted"], font=theme["font"])
        sp.runs[0].text = slogan


def _compare_keynote(slide: Any, theme: dict[str, Any], st: dict[str, Any],
                     item: dict[str, Any], index: int) -> None:
    """015 P6 对比：暗色表格——mono 大写表头（本品列 ink 粗）、行发丝线、
    本品列粗体、其余 muted；底部 faint 注记。"""
    _head_keynote(slide, theme, st, item, index)
    spec = item.get("table") if isinstance(item.get("table"), dict) else {}
    columns = [str(c) for c in (spec.get("columns") or [])][:5]
    rows = [[str(cell) for cell in row] for row in (spec.get("rows") or [])][:8]
    rows = [row[:len(columns)] + [""] * (len(columns) - len(row))
            for row in rows]
    us_col = 1 if len(columns) >= 2 else -1
    tbl_h = 0.46 + 0.4 * len(rows)
    frame = slide.shapes.add_table(len(rows) + 1, len(columns),
                                   Inches(_in(96)), Inches(_in(212)),
                                   Inches(13.333 - 2 * _in(96)), Inches(tbl_h))
    table = frame.table
    table.first_row = False
    table.horz_banding = False
    dark = theme["cover_bg"]
    for c, label in enumerate(columns):
        cell = table.cell(0, c)
        cell.fill.solid()
        cell.fill.fore_color.rgb = rgb(dark)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = cell.text_frame.paragraphs[0]
        run = p.add_run()
        set_run(run, _pt(11), theme["text"] if c == us_col
                else theme["muted"], bold=(c == us_col), font=_mono(),
                letter_spacing_pt=_pt(11 * 0.18))
        run.text = label.upper()
    for r, row in enumerate(rows, start=1):
        for c, value in enumerate(row):
            cell = table.cell(r, c)
            cell.fill.solid()
            cell.fill.fore_color.rgb = rgb(dark)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = cell.text_frame.paragraphs[0]
            run = p.add_run()
            if c == us_col:
                set_run(run, _pt(12.5), theme["text"], bold=True,
                        font=theme["font"])
            elif c == 0:
                set_run(run, _pt(11), theme["muted"], font=theme["font"])
            else:
                set_run(run, _pt(12), theme["muted"], font=theme["font"])
            run.text = value
    note = str(item.get("subtitle") or "").strip()
    if note:
        n_box = add_textbox(slide, _in(96), _in(212) + tbl_h + 0.2, 10.67, 0.32)
        np_ = n_box.text_frame.paragraphs[0]
        set_run(np_.add_run(), _pt(12), blend(dark, theme["text"], 0.4),
                font=theme["font"])
        np_.runs[0].text = note


def _ecosystem_keynote(slide: Any, theme: dict[str, Any], st: dict[str, Any],
                       item: dict[str, Any], index: int) -> None:
    """015 P7 生态：mono 眉题 + 大标题 + 副文 + 底部三张深灰卡
    （e-no 编号 + 粗标题 + 灰描述）。"""
    _head_keynote(slide, theme, st, item, index)
    sub = str(item.get("subtitle") or "").strip()
    if sub:
        s_box = add_textbox(slide, _in(96), _in(70) + 1.05, 7.6, 0.6)
        sp = s_box.text_frame.paragraphs[0]
        sp.line_spacing = 1.5
        set_run(sp.add_run(), _pt(12), theme["muted"], font=theme["font"])
        sp.runs[0].text = sub
    points = _points_of(item, 3) or ["{{设备联动}}|{{一句话描述}}"]
    gap = _in(22)
    card_w = (13.333 - 2 * _in(96) - gap * (len(points) - 1)) / len(points)
    card_h = 1.9
    cards_y = 7.5 - 1.33 - card_h
    line = blend(theme["cover_bg"], "FFFFFF", 0.12)
    for i, raw in enumerate(points):
        parts = [seg.strip() for seg in raw.split("|")]
        title = parts[0] or "{{名称}}"
        desc = parts[1] if len(parts) > 1 else ""
        dev = parts[2] if len(parts) > 2 else ""
        x = _in(96) + i * (card_w + gap)
        card = add_rect(slide, x, cards_y, card_w, card_h,
                        blend(theme["cover_bg"], "FFFFFF", 0.06),
                        rounded=True, radius=0.12)
        card.line.color.rgb = rgb(line)
        card.line.width = Pt(1)
        e_box = add_textbox(slide, x + _in(24), cards_y + _in(24),
                            card_w - _in(40), 0.26)
        ep = e_box.text_frame.paragraphs[0]
        set_run(ep.add_run(), _pt(11), blend(theme["cover_bg"], theme["text"], 0.4),
                font=_mono(), letter_spacing_pt=_pt(11 * 0.22))
        ep.runs[0].text = f"{i + 1:02d}" + (f" · {dev}" if dev else "")
        h_box = add_textbox(slide, x + _in(24), cards_y + _in(24) + 0.36,
                            card_w - _in(40), 0.4)
        hp = h_box.text_frame.paragraphs[0]
        set_run(hp.add_run(), _pt(14.25), theme["text"], bold=True,
                font=theme["font"])
        hp.runs[0].text = title
        if desc:
            d_box = add_textbox(slide, x + _in(24), cards_y + _in(24) + 0.82,
                                card_w - _in(40), 0.75)
            dp = d_box.text_frame.paragraphs[0]
            dp.line_spacing = 1.45
            set_run(dp.add_run(), _pt(10), theme["muted"], font=theme["font"])
            dp.runs[0].text = desc


def _pricing_keynote(slide: Any, theme: dict[str, Any], st: dict[str, Any],
                     item: dict[str, Any], index: int) -> None:
    """015 P8 价格·发售：居中眉题 + 大标题 + 三张价格卡（推荐卡蓝描边）
    + 底部发售行。points 每条 '档位|名称|配置|价格'。"""
    _foot_keynote(slide, theme, st, index)
    kick = str(item.get("kicker") or "Pricing · 价格与发售")
    k_box = add_textbox(slide, 1.67, 0.7, 10.0, 0.3)
    kp = k_box.text_frame.paragraphs[0]
    kp.alignment = PP_ALIGN.CENTER
    set_run(kp.add_run(), _pt(13), theme["muted"], font=_mono(),
            letter_spacing_pt=_pt(13 * 0.24))
    kp.runs[0].text = kick.upper()
    heading = str(item.get("heading") or item.get("title") or "")
    h_box = add_textbox(slide, 1.67, 1.06, 10.0, 0.75)
    hp = h_box.text_frame.paragraphs[0]
    hp.alignment = PP_ALIGN.CENTER
    if "|" in heading:
        pre, accent_word = (seg.strip() for seg in heading.split("|", 1))
    else:
        pre, accent_word = heading, ""
    if pre:
        p_run = hp.add_run()
        set_run(p_run, _pt(36), theme["text"], bold=True, font=theme["font"])
        p_run.text = pre
    if accent_word:
        a_run = hp.add_run()
        set_run(a_run, _pt(36), theme["accent"], bold=True, font=theme["font"])
        a_run.text = accent_word
    points = _points_of(item, 3)
    if len(points) < 3:
        points = points + ["{{档位}}|{{版本名}}|{{配置}}|¥{{价格}}"] * (3 - len(points))
    gap = _in(22)
    card_w = (13.333 - 2 * 1.1 - gap * 2) / 3
    cards_y = _in(236)
    card_h = 2.95
    for i, raw in enumerate(points):
        parts = [seg.strip() for seg in raw.split("|")]
        tag = parts[0] if parts else ""
        name = parts[1] if len(parts) > 1 else ""
        desc = parts[2] if len(parts) > 2 else ""
        price = parts[3] if len(parts) > 3 else ""
        reco = i == 1
        x = 1.1 + i * (card_w + gap)
        card = add_rect(slide, x, cards_y, card_w, card_h,
                        blend(theme["cover_bg"], "FFFFFF", 0.05),
                        rounded=True, radius=0.14)
        card.line.color.rgb = rgb(theme["accent"] if reco
                                  else blend(theme["cover_bg"], "FFFFFF", 0.12))
        card.line.width = Pt(1.5 if reco else 1)
        cx = x + card_w / 2 - card_w / 2 + _in(28)
        cw = card_w - _in(56)
        cxc = x + _in(28)
        t_box = add_textbox(slide, cxc, cards_y + _in(28), cw, 0.26)
        tp = t_box.text_frame.paragraphs[0]
        tp.alignment = PP_ALIGN.CENTER
        set_run(tp.add_run(), _pt(11.5), theme["accent"] if reco
                else theme["muted"], font=_mono(),
                letter_spacing_pt=_pt(11.5 * 0.24))
        tp.runs[0].text = tag.upper()
        n_box = add_textbox(slide, cxc, cards_y + _in(28) + 0.38, cw, 0.36)
        np_ = n_box.text_frame.paragraphs[0]
        np_.alignment = PP_ALIGN.CENTER
        set_run(np_.add_run(), _pt(14.25), theme["text"], bold=True,
                font=theme["font"])
        np_.runs[0].text = name
        if desc:
            d_box = add_textbox(slide, cxc, cards_y + _in(28) + 0.76, cw, 0.3)
            dp = d_box.text_frame.paragraphs[0]
            dp.alignment = PP_ALIGN.CENTER
            set_run(dp.add_run(), _pt(9.5), theme["muted"], font=theme["font"])
            dp.runs[0].text = desc
        pr_box = add_textbox(slide, cxc, cards_y + _in(28) + 1.3, cw, 0.85)
        prp = pr_box.text_frame.paragraphs[0]
        prp.alignment = PP_ALIGN.CENTER
        if price:
            currency = price[0] if price[0] in "¥$" else ""
            amount = price[len(currency):]
            if currency:
                c_run = prp.add_run()
                set_run(c_run, _pt(18), theme["muted"], bold=False,
                        font=theme["font"])
                c_run.text = currency
            a_run = prp.add_run()
            set_run(a_run, _pt(39), theme["text"], bold=True, font=theme["font"],
                    letter_spacing_pt=-0.2)
            a_run.text = amount
    sale = str(item.get("subtitle") or "").strip()
    if sale:
        s_box = add_textbox(slide, 1.67, 6.55, 10.0, 0.35)
        sp = s_box.text_frame.paragraphs[0]
        sp.alignment = PP_ALIGN.CENTER
        set_run(sp.add_run(), _pt(10.5), theme["muted"], font=theme["font"])
        sp.runs[0].text = sale


def _end(slide: Any, theme: dict[str, Any], st: dict[str, Any],
         item: dict[str, Any], index: int) -> None:
    if _is_devconf(theme):
        _end_devconf(slide, theme, item)
    else:
        _end_keynote(slide, theme, st, item, index)


def _end_devconf(slide: Any, theme: dict[str, Any], item: dict[str, Any]) -> None:
    """016 P12 结尾 CTA：纸面居中品牌 + 62px 标题 + 双胶囊按钮 + mono 联系行。"""
    add_rect(slide, 0, 0, 13.333, 7.5, theme["content_bg"])
    brand = str(item.get("brand") or "").strip()
    heading = str(item.get("heading") or item.get("title") or "谢谢观看")
    sub = str(item.get("subtitle") or "").strip()
    contact = str(item.get("body") or "").strip()
    y = 1.55
    if brand:
        b_box = add_textbox(slide, 1.6, y, 10.13, 0.55)
        bp = b_box.text_frame.paragraphs[0]
        bp.alignment = PP_ALIGN.CENTER
        set_run(bp.add_run(), _pt(30), theme["text"], bold=True,
                font=theme["font"], letter_spacing_pt=_pt(30 * 0.2))
        bp.runs[0].text = brand.upper()
        y += 0.95
    size = pick_size(heading, 10.4, 1.7, [_pt(62), _pt(52), _pt(44)])
    box = add_textbox(slide, 1.6, y, 10.13, 1.6)
    p = box.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    p.line_spacing = 1.25
    set_run(p.add_run(), size, theme["text"], bold=True, font=theme["font"])
    p.runs[0].text = heading
    y += 1.75
    if sub:
        s_box = add_textbox(slide, 1.6, y, 10.13, 0.45)
        sp = s_box.text_frame.paragraphs[0]
        sp.alignment = PP_ALIGN.CENTER
        set_run(sp.add_run(), _pt(17), theme["muted"], font=theme["font"],
                letter_spacing_pt=_pt(17 * 0.08))
        sp.runs[0].text = sub
        y += 0.75
    buttons = [str(raw).strip() for raw in _points_of(item, 2)]
    if buttons:
        widths = [1.0 + len(text) * 0.16 for text in buttons]
        total = sum(widths) + _in(16)
        bx = (13.333 - total) / 2
        for i, text in enumerate(buttons):
            primary = i == 0
            pill = add_pill(slide, bx, y + 0.2, widths[i], 0.56,
                            theme["accent"] if primary else "FFFFFF")
            if not primary:
                pill.line.color.rgb = rgb(theme["text"])
                pill.line.width = Pt(1)
            ptf = pill.text_frame
            ptf.vertical_anchor = MSO_ANCHOR.MIDDLE
            pp = ptf.paragraphs[0]
            pp.alignment = PP_ALIGN.CENTER
            set_run(pp.add_run(), _pt(14.5), "FFFFFF" if primary
                    else theme["text"], font=_mono(), letter_spacing_pt=0.5)
            pp.runs[0].text = text
            bx += widths[i] + _in(16)
    if contact:
        c_box = add_textbox(slide, 1.6, 6.5, 10.13, 0.35)
        cp = c_box.text_frame.paragraphs[0]
        cp.alignment = PP_ALIGN.CENTER
        set_run(cp.add_run(), _pt(12.5),
                blend("FFFFFF", theme["text"], 0.3), font=_mono(),
                letter_spacing_pt=_pt(12.5 * 0.14))
        cp.runs[0].text = contact


def _end_keynote(slide: Any, theme: dict[str, Any], st: dict[str, Any],
                 item: dict[str, Any], index: int) -> None:
    add_rect(slide, 0, 0, 13.333, 7.5, theme["cover_bg"])
    _foot_keynote(slide, theme, st, index)
    heading = str(item.get("heading") or item.get("title") or "谢谢观看")
    sub = str(item.get("subtitle") or "").strip()
    size = pick_size(heading, 10.2, 1.7, [48, 42, 36])
    box = add_textbox(slide, 1.35, 2.75, 10.6, 1.6)
    p = box.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    p.line_spacing = 1.25
    set_run(p.add_run(), size, theme["cover_text"], bold=True,
            font=theme["font"])
    p.runs[0].text = heading
    if sub:
        s_box = add_textbox(slide, 1.35, 4.55, 10.6, 0.5)
        sp = s_box.text_frame.paragraphs[0]
        sp.alignment = PP_ALIGN.CENTER
        set_run(sp.add_run(), 15, theme["muted"], font=theme["font"])
        sp.runs[0].text = sub


# ---------------------------------------------------------------- 入口

_LAYOUT_PAGE = {
    "cover": "_cover",
    "section": "_manifesto",
    "toc": "_why_rows",
    "bullets": "_why_rows",
    "timeline": "_why_rows",
    "cards": "_cards",
    "columns": "_cards",
    "kpi": "_kpi",
    "kpi_rows": "_metrics",
    "overview": "_overview",
    "growth": "_growth",
    "reveal": "_reveal",
    "ecosystem": "_ecosystem",
    "pricing": "_pricing",
    "two_col": "_two_col",
    "compare": "_compare",
    "quote": "_quote",
    "table": "_table",
    "chart": "_chart",
    "end": "_end",
}


def render_slide(prs: Any, item: Any, theme: dict[str, Any], index: int,
                 resolve_media: Callable[[str], Any] | None = None) -> str:
    """样张主题整页渲染入口：按版式分发到对应样张构图。"""
    item = item if isinstance(item, dict) else {"body": str(item)}
    st = {"_deck_pages": int(item.get("_pages") or 0),
          "_brand": str(item.get("_brand") or "")}
    sample = theme.get("sample")
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    if sample == "keynote":
        # 015 纯黑舞台：所有 keynote 页先铺底色（封面/宣言/结尾自绘全幅底也不冲突）
        add_rect(slide, 0, 0, 13.333, 7.5, theme["cover_bg"])
    layout = str(item.get("layout") or "").strip().lower()
    if layout not in _LAYOUT_PAGE:
        from .layouts import guess_layout
        layout = guess_layout(item)
    if layout not in _LAYOUT_PAGE:
        layout = "bullets"

    if layout == "cover":
        if sample == "devconf":
            _cover_devconf(slide, theme, item)
        else:
            _cover_keynote(slide, theme, st, item)
    elif layout == "section":
        part_no = int(item.get("_section_no") or 1)
        if sample == "devconf":
            _manifesto_devconf(slide, theme, st, item, part_no)
        else:
            _manifesto_keynote(slide, theme, st, item, part_no)
    elif layout in ("bullets", "timeline", "toc"):
        _why_rows(slide, theme, st, item, index)
    elif layout in ("cards", "columns"):
        _cards(slide, theme, st, item, index)
    elif layout == "kpi":
        _kpi(slide, theme, st, item, index)
    elif layout == "kpi_rows":
        if sample == "devconf":
            _metrics_devconf(slide, theme, st, item, index)
        else:
            _kpi(slide, theme, st, item, index)
    elif layout == "overview":
        if sample == "devconf":
            _overview_devconf(slide, theme, st, item, index, resolve_media)
        else:
            _two_col(slide, theme, st, item, index, None)
    elif layout == "growth":
        if sample == "devconf":
            _growth_devconf(slide, theme, st, item, index)
        else:
            _kpi(slide, theme, st, item, index)
    elif layout == "two_col":
        _two_col(slide, theme, st, item, index, resolve_media)
    elif layout in ("compare", "table"):
        if sample == "keynote":
            # 015 P6：暗色表格（本品列粗体），不走 devconf 白底表
            _compare_keynote(slide, theme, st, item, index)
        elif layout == "table":
            _table(slide, theme, st, item, index)
        else:
            _compare(slide, theme, st, item, index)
    elif layout == "quote":
        _quote(slide, theme, st, item, index)
    elif layout == "reveal":
        if sample == "keynote":
            _reveal_keynote(slide, theme, st, item, index, resolve_media)
        else:
            _quote(slide, theme, st, item, index)
    elif layout == "ecosystem":
        if sample == "keynote":
            _ecosystem_keynote(slide, theme, st, item, index)
        else:
            _cards(slide, theme, st, item, index)
    elif layout == "pricing":
        if sample == "keynote":
            _pricing_keynote(slide, theme, st, item, index)
        else:
            _end(slide, theme, st, item, index)
    elif layout == "chart":
        _chart(slide, theme, st, item, index)
    else:  # end
        _end(slide, theme, st, item, index)
    return layout
