"""模板 10 · 跨界转型版 — 功能型结构，可迁移能力三卡、时间线后置。"""

from __future__ import annotations

try:
    from .components import (
        EDITABLE_CSS,
        _esc,
        allow_bold,
        bold_numbers,
        bullets_html,
        contact_spans_html,
        exp_bullets,
        exp_content_html,
        item_hd,
    )
except ImportError:  # 兼容脚本直接运行
    from components import (  # type: ignore
        EDITABLE_CSS,
        _esc,
        allow_bold,
        bold_numbers,
        bullets_html,
        contact_spans_html,
        exp_bullets,
        exp_content_html,
        item_hd,
    )

id = "tpl_lateral"

CSS = """:root{
  --sans:"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;
  --ink:#241f2e; --sub:#544c63; --mute:#8b8399; --line:#e2dee9;
  --brand:#6b4ba8; --brand-soft:#efe9fb; --band:#f6f4fa;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:#eceae5;color:var(--ink);font-family:var(--sans);font-size:10.5pt;line-height:1.62;-webkit-font-smoothing:antialiased}

.toolbar{position:fixed;top:0;left:0;right:0;z-index:9;display:flex;align-items:center;gap:14px;
  padding:10px 18px;background:#241f2e;color:#efeaf5;font-size:12px}
.toolbar b{font-weight:500}
.toolbar button{font:inherit;background:#efeaf5;color:#241f2e;border:0;border-radius:5px;padding:5px 14px;cursor:pointer}
.toolbar button:hover{background:#fff}
.toolbar .tip{color:#a79db8}

.page{width:210mm;min-height:297mm;background:#fff;margin:52px auto 32px;box-shadow:0 1px 5px rgba(0,0,0,.14)}

.hd{padding:12mm 15mm 10mm;border-bottom:1px solid var(--brand)}
.hd h1{font-size:22pt;font-weight:600;letter-spacing:.04em}
.hd .role{margin-top:4px;font-size:11pt;color:var(--brand);letter-spacing:.02em}
.hd .pivot{margin-top:6px;font-size:9.5pt;color:var(--sub)}
.hd .pivot b{color:var(--ink);font-weight:600}
.hd .contact{margin-top:8px;font-size:9pt;color:var(--sub)}
.hd .contact span{margin-right:15px}

.body{padding:9mm 15mm 12mm}

h2{font-size:9.5pt;font-weight:600;letter-spacing:.18em;color:var(--brand);margin:15px 0 8px;
  display:flex;align-items:center;gap:8px}
h2::after{content:"";font-size:0;flex:1;height:.5px;background:var(--line)}
h2 .note{font-weight:400;font-size:8.5pt;color:var(--mute);letter-spacing:0}
h2:first-child{margin-top:0}

.summary{font-size:10pt;color:var(--sub);text-align:justify;line-height:1.72}
.summary b{color:var(--ink);font-weight:600}

.transfer{display:flex;gap:10px}
.tcard{flex:1;border:.5px solid var(--line);border-top:2px solid var(--brand);padding:10px 12px;background:var(--band)}
.tcard .h{font-size:8.5pt;letter-spacing:.12em;color:var(--mute)}
.tcard .t{font-size:10.5pt;font-weight:600;margin-top:4px}
.tcard .d{font-size:9.5pt;color:var(--sub);margin-top:5px;line-height:1.6}
.tcard .e{font-size:9.5pt;color:var(--brand);font-weight:600;margin-top:6px}

.item{margin-bottom:12px}
.item-hd{display:flex;align-items:baseline;gap:10px}
.org{font-size:10.5pt;font-weight:600}
.meta{font-size:9.5pt;color:var(--sub)}
.date{margin-left:auto;font-size:9pt;color:var(--mute);font-variant-numeric:tabular-nums;white-space:nowrap}
ul{list-style:none;margin-top:5px}
li{position:relative;padding-left:14px;margin-bottom:4px;font-size:10pt;text-align:justify}
li::before{content:"→";position:absolute;left:0;color:var(--brand);font-size:9pt;top:.5px}
li b{font-weight:600;color:#4e3583}

.timeline{border-left:1.5px solid var(--line);padding-left:14px;margin-left:3px}
.tl{position:relative;padding-bottom:11px}
.tl::before{content:"";font-size:0;position:absolute;left:-20px;top:6px;width:7px;height:7px;
  border-radius:50%;background:#fff;border:1.5px solid var(--brand)}
.tl .h{display:flex;align-items:baseline;gap:9px}
.tl .h .o{font-weight:600;font-size:10.5pt}
.tl .h .d{margin-left:auto;font-size:9pt;color:var(--mute);font-variant-numeric:tabular-nums}

.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{font-size:9pt;background:var(--brand-soft);color:#4e3583;padding:3px 10px;border-radius:11px}
.chip.new{background:#e6f4ec;color:#1c6b45}

.two{display:flex;gap:26px}
.two .col{flex:1;min-width:0}
""" + EDITABLE_CSS

PRINT_SINGLE = """
@media print{
  @page{size:A4;margin:0}
  body{background:#fff}
  .toolbar{display:none!important}
  .page{width:auto;min-height:auto;margin:0;box-shadow:none}
  .chip,.tcard{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .item,.tcard{break-inside:avoid}
  [contenteditable="true"]:hover,[contenteditable="true"]:focus{background:none!important;outline:none!important}
}
"""


def _h2(title: str, note: str = "") -> str:
    note_html = f'<span class="note">{note}</span>' if note else ""
    return f'<h2 contenteditable="true">{title}{note_html}</h2>'


def render(r) -> str:
    pivot_html = (
        f'<div class="pivot" contenteditable="true">{allow_bold(r.pivot)}</div>'
        if r.pivot
        else ""
    )
    header = (
        '<header class="hd">'
        f'<h1 contenteditable="true">{_esc(r.name)}</h1>'
        f'<div class="role" contenteditable="true">求职方向：{_esc(r.title)}</div>'
        + pivot_html
        + f'<div class="contact" contenteditable="true">{contact_spans_html(r)}</div>'
        "</header>"
    )

    inner: list[str] = []
    if r.summary:
        inner.append(_h2("转型动机与定位", "为什么是我"))
        inner.append(f'<p class="summary" contenteditable="true">{bold_numbers(r.summary)}</p>')

    if r.transferable:
        inner.append(_h2("可迁移能力", "TRANSFERABLE SKILLS"))
        cards = []
        for t in r.transferable[:3]:
            cards.append(
                '<div class="tcard">'
                f'<div class="h" contenteditable="true">FROM {_esc(t.source)}</div>'
                f'<div class="t" contenteditable="true">{_esc(t.ability)}</div>'
                f'<div class="d" contenteditable="true">{bold_numbers(t.description)}</div>'
                f'<div class="e" contenteditable="true">→ {_esc(t.mapping)}</div>'
                "</div>"
            )
        inner.append(f'<div class="transfer">{"".join(cards)}</div>')

    practice_items: list[str] = []
    for p in r.merged_projects():
        points = [str(h) for h in p.highlights if str(h).strip()]
        if not points and p.description:
            points = [line.strip() for line in p.description.splitlines() if line.strip()]
        if not points and p.impact:
            points = [p.impact]
        meta = " · ".join(str(x) for x in (p.role, p.kind) if x)
        practice_items.append(
            '<div class="item">'
            + item_hd(p.name, meta, p.year)
            + bullets_html(points)
            + "</div>"
        )
    for e in r.experiences:
        if not e.title or "实习" not in e.title:
            continue
        practice_items.append(
            '<div class="item">'
            + item_hd(e.company, e.title, e.period)
            + exp_content_html(e)
            + "</div>"
        )
    if practice_items:
        inner.append(_h2("转型准备与实践", "已完成的证明"))
        inner.extend(practice_items)

    past = [e for e in r.experiences if not (e.title and "实习" in e.title)]
    if past:
        inner.append(_h2("既往经历", "时间线（简版）"))
        rows = []
        for e in past:
            rows.append(
                '<div class="tl">'
                f'<div class="h"><span class="o" contenteditable="true">{_esc(e.company)}</span>'
                f'<span class="d" contenteditable="true">{_esc(e.period)}</span></div>'
                + exp_content_html(e)
                + "</div>"
            )
        inner.append(f'<div class="timeline">{"".join(rows)}</div>')

    chips = []
    for x in r.core_skills[:6]:
        chips.append(f'<span class="chip new" contenteditable="true">{_esc(x)}</span>')
    for s in r.skills:
        name = s.name.split("|", 1)[0].strip() if "|" in s.name else s.name.strip()
        if name:
            chips.append(f'<span class="chip" contenteditable="true">{_esc(name)}</span>')
    if chips:
        inner.append(_h2("技能与工具"))
        inner.append(f'<div class="chips">{"".join(chips)}</div>')

    if r.education:
        inner.append(_h2("教育背景"))
        cols = []
        for e in r.education[:2]:
            detail = " · ".join(str(x) for x in (e.degree, e.gpa and f"GPA {e.gpa}") if x)
            cols.append(
                '<div class="col"><div class="item" style="margin-bottom:0">'
                + item_hd(e.school, "", e.period)
                + f'<ul><li>{_esc(detail)}</li></ul></div></div>'
            )
        inner.append(f'<div class="two">{"".join(cols)}</div>')

    body = f'<div class="body">{"".join(inner)}</div>'
    return f'<div class="page">{header}{body}</div>'
