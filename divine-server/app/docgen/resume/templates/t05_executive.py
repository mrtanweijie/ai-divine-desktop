"""模板 05 · 高管领袖版 — 深色头部 + 核心指标条，CXO/VP。"""

from __future__ import annotations

try:
    from .components import (
        EDITABLE_CSS,
        _esc,
        bold_numbers,
        bullets_html,
        contact_spans_html,
        exp_bullets,
        exp_content_html,
        exp_meta,
        item_hd,
        page_foot,
    )
    from .helpers import _split_value_unit
except ImportError:  # 兼容脚本直接运行
    from components import (  # type: ignore
        EDITABLE_CSS,
        _esc,
        bold_numbers,
        bullets_html,
        contact_spans_html,
        exp_bullets,
        exp_content_html,
        exp_meta,
        item_hd,
        page_foot,
    )
    from .helpers import _split_value_unit

id = "tpl_executive"

CSS = """:root{
  --sans:"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;
  --serif:"Songti SC","STSong","Source Han Serif SC",Georgia,serif;
  --ink:#1a1a1a; --sub:#464646; --mute:#7d7d7d; --line:#d5d2ca;
  --navy:#16233a; --gold:#a8874f;
  --foot-x:16mm; /* 页脚贴底时的左右缩进，对齐 .body 内边距 16mm */
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:#eceae5;color:var(--ink);font-family:var(--sans);font-size:10.5pt;line-height:1.55;-webkit-font-smoothing:antialiased}

.toolbar{position:fixed;top:0;left:0;right:0;z-index:9;display:flex;align-items:center;gap:14px;
  padding:10px 18px;background:#16233a;color:#eef0f4;font-size:12px}
.toolbar b{font-weight:500}
.toolbar button{font:inherit;background:#eef0f4;color:#16233a;border:0;border-radius:5px;padding:5px 14px;cursor:pointer}
.toolbar button:hover{background:#fff}
.toolbar .tip{color:#9aa3b4}

.page{width:210mm;min-height:297mm;background:#fff;margin:52px auto 32px;box-shadow:0 1px 5px rgba(0,0,0,.14)}

.hero{background:var(--navy);color:#fff;padding:11mm 16mm 9mm}
.hero h1{font-family:var(--serif);font-size:27pt;font-weight:600;letter-spacing:.3em;margin-right:-.3em}
.hero .gold{width:54px;height:2px;background:var(--gold);margin:10px 0 8px}
.hero .role{font-size:11.5pt;color:#d9c39a;letter-spacing:.07em}
.hero .contact{margin-top:10px;font-size:9.5pt;color:#a9b2c4}
.hero .contact span::after{content:" ";margin:0 9px;color:#4a5568}
.hero .contact span:last-child::after{content:"";font-size:0}

.body{padding:10mm 16mm 12mm}

h2{font-size:10pt;font-weight:600;letter-spacing:.2em;color:var(--navy);
  padding-bottom:4px;border-bottom:.5px solid var(--line);margin:12px 0 7px}
h2 .en{float:right;font-weight:400;letter-spacing:.08em;color:#a9b2c4;font-size:8.5pt}
h2:first-child{margin-top:0}

.profile{font-size:10pt;color:var(--sub);text-align:justify;line-height:1.74}
.profile b{color:var(--ink);font-weight:600}

.metrics{display:flex;border:.5px solid var(--line);margin:12px 0 4px}
.metrics .m{flex:1;padding:10px 12px;text-align:center;border-right:.5px solid var(--line)}
.metrics .m:last-child{border-right:0}
.metrics .n{font-size:19pt;font-weight:600;color:var(--navy);line-height:1.2;font-variant-numeric:tabular-nums}
.metrics .n small{font-size:10pt;font-weight:400}
.metrics .l{font-size:8.5pt;color:var(--mute);margin-top:3px;line-height:1.4}

.item{margin-bottom:10px}
.item-hd{display:flex;align-items:baseline;gap:10px}
.org{font-size:11pt;font-weight:600}
.meta{font-size:9.5pt;color:var(--sub)}
.date{margin-left:auto;font-size:9pt;color:var(--mute);font-variant-numeric:tabular-nums;white-space:nowrap}
.scale{font-size:8.5pt;color:var(--mute);margin-top:1px;letter-spacing:.02em}
ul{list-style:none;margin-top:5px}
li{position:relative;padding-left:14px;margin-bottom:3px;font-size:10pt;text-align:justify}
li::before{content:"";font-size:0;position:absolute;left:0;top:8.5px;width:5px;height:.5px;background:var(--gold)}
li b{font-weight:600}

.plain li::before{width:4px;height:4px;border-radius:50%;background:#c9c6be;top:7px}

.two{display:flex;gap:30px}
.two .col{flex:1;min-width:0}

.foot{margin-top:15px;padding-top:8px;border-top:.5px solid var(--line);
  display:flex;justify-content:space-between;font-size:8.5pt;color:var(--mute);letter-spacing:.04em}
""" + EDITABLE_CSS

PRINT_SINGLE = """
@media print{
  @page{size:A4;margin:0}
  body{background:#fff}
  .toolbar{display:none!important}
  .page{width:auto;min-height:auto;margin:0;box-shadow:none}
  .hero{padding:12mm 15mm 10mm;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  [contenteditable="true"]:hover,[contenteditable="true"]:focus{background:none!important;outline:none!important}
}
"""


def _h2(title_cn: str, title_en: str = "") -> str:
    en = f'<span class="en">{title_en}</span>' if title_en else ""
    return f'<h2 contenteditable="true">{title_cn}{en}</h2>'


def _metrics_html(r) -> str:
    if not r.metrics:
        return ""
    cells = []
    for m in r.metrics[:4]:
        value, unit = _split_value_unit(m.value)
        unit_html = f"<small>{_esc(unit)}</small>" if unit else ""
        cells.append(
            '<div class="m">'
            f'<div class="n" contenteditable="true">{_esc(value)}{unit_html}</div>'
            f'<div class="l" contenteditable="true">{_esc(m.label)}</div>'
            "</div>"
        )
    return f'<div class="metrics">{"".join(cells)}</div>'


def render(r) -> str:
    hero = (
        '<header class="hero">'
        f'<h1 contenteditable="true">{_esc(r.name)}</h1>'
        '<div class="gold"></div>'
        f'<div class="role" contenteditable="true">{_esc(r.title)}</div>'
        f'<div class="contact" contenteditable="true">{contact_spans_html(r)}</div>'
        "</header>"
    )

    inner: list[str] = []
    if r.summary:
        inner.append(_h2(getattr(r, "summary_title", "") or "个人摘要", "EXECUTIVE PROFILE"))
        inner.append(f'<p class="profile" contenteditable="true">{bold_numbers(r.summary)}</p>')
        metrics_html = _metrics_html(r)
        if metrics_html:
            inner.append(metrics_html)

    if r.experiences:
        inner.append(_h2("职业经历", "EXPERIENCE"))
        for e in r.experiences:
            scale = (
                f'<div class="scale" contenteditable="true">{_esc(e.scale or e.dept)}</div>'
                if (e.scale or e.dept)
                else ""
            )
            inner.append(
                '<div class="item">'
                + item_hd(e.company, exp_meta(e), e.period)
                + scale
                + exp_content_html(e)
                + "</div>"
            )

    if r.projects:
        inner.append(_h2("关键项目", "KEY PROJECTS"))
        for p in r.projects:
            points = [str(h) for h in p.highlights if str(h).strip()]
            if not points and p.impact:
                points = [p.impact]
            inner.append(
                '<div class="item">'
                + item_hd(p.name, p.role, p.year)
                + bullets_html(points)
                + "</div>"
            )

    if r.public_work:
        inner.append(_h2("董事会与社会职务", "BOARD & AFFILIATIONS"))
        lis = "".join(f"<li>{_esc(x)}</li>" for x in r.public_work)
        inner.append(f'<ul class="plain" contenteditable="true">{lis}</ul>')

    if r.education:
        inner.append(_h2("教育背景", "EDUCATION"))
        cols = []
        for e in r.education[:2]:
            cols.append(
                '<div class="col"><div class="item" style="margin-bottom:0">'
                + item_hd(e.school, "", e.period)
                + f'<div class="scale" contenteditable="true">{_esc(e.degree)}</div></div></div>'
            )
        inner.append(f'<div class="two">{"".join(cols)}</div>')

    if r.honors:
        inner.append(_h2("荣誉与媒体", "RECOGNITION"))
        lis = "".join(f"<li>{bold_numbers(x)}</li>" for x in r.honors)
        inner.append(f'<ul class="plain" contenteditable="true">{lis}</ul>')

    foot = page_foot(
        f"{r.name} · {r.title}" if r.title else r.name,
        r.contact.phone or r.contact.email,
    )
    body = f'<div class="body">{"".join(inner)}{foot}</div>'
    return f'<div class="page">{hero}{body}</div>'
