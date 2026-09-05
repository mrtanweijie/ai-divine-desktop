"""模板 04 · 学术科研版 — 学术衬线，教育置顶、论文编号列表。"""

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
        kv_row,
    )
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
        kv_row,
    )

id = "tpl_academic"

CSS = """:root{
  --serif:"Songti SC","STSong","Source Han Serif SC","Noto Serif CJK SC",Georgia,"Times New Roman",serif;
  --sans:"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;
  --ink:#191919; --sub:#3f3f3f; --mute:#757575; --line:#c8c5bd; --accent:#4a2f6b;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:#eceae5;color:var(--ink);font-family:var(--serif);font-size:10pt;line-height:1.55;-webkit-font-smoothing:antialiased}

.toolbar{position:fixed;top:0;left:0;right:0;z-index:9;display:flex;align-items:center;gap:14px;
  padding:10px 18px;background:#191919;color:#f3f1ec;font-size:12px;font-family:var(--sans)}
.toolbar b{font-weight:500}
.toolbar button{font:inherit;background:#f3f1ec;color:#191919;border:0;border-radius:5px;padding:5px 14px;cursor:pointer}
.toolbar button:hover{background:#fff}
.toolbar .tip{color:#a7a29a}

.page{width:210mm;min-height:297mm;background:#fff;margin:52px auto 32px;padding:12mm 16mm;
  box-shadow:0 1px 5px rgba(0,0,0,.14)}

.hd{text-align:left;border-bottom:1.2px solid var(--ink);padding-bottom:9px;margin-bottom:14px}
.hd h1{font-size:22pt;font-weight:600;letter-spacing:.16em}
.hd .affil{margin-top:5px;font-size:10.5pt;color:var(--sub)}
.hd .contact{margin-top:6px;font-size:9pt;color:var(--mute);font-family:var(--sans)}
.hd .contact span{margin:0 8px}

h2{font-size:10.5pt;font-weight:600;letter-spacing:.12em;color:var(--accent);
  margin:11px 0 5px;padding-bottom:2.5px;border-bottom:.5px solid var(--line)}
h2:first-of-type{margin-top:0}

.item{margin-bottom:7px}
.item-hd{display:flex;align-items:baseline;gap:10px}
.org{font-weight:600;font-size:10.5pt}
.meta{font-size:9.5pt;color:var(--sub);font-style:italic}
.date{margin-left:auto;font-size:9pt;color:var(--mute);font-variant-numeric:tabular-nums;white-space:nowrap}
ul{list-style:none;margin-top:3px}
li{position:relative;padding-left:14px;margin-bottom:3px;font-size:10pt;text-align:justify}
li::before{content:"·";position:absolute;left:3px;color:var(--mute)}
li b{font-weight:600}

ol.pubs{list-style:none;counter-reset:p;margin:0;padding:0}
ol.pubs li{counter-increment:p;position:relative;padding-left:26px;margin-bottom:6px;
  font-size:9.8pt;line-height:1.58;text-align:justify}
ol.pubs li::before{content:"[" counter(p) "]";position:absolute;left:0;color:var(--mute);font-family:var(--sans);font-size:9pt}
ol.pubs em{font-style:italic}
ol.pubs .tag{font-family:var(--sans);font-size:8.5pt;color:var(--accent);
  border:.5px solid var(--line);border-radius:3px;padding:0 5px;margin-left:5px;white-space:nowrap}

.kv{display:flex;gap:10px;margin-bottom:5px;font-size:10pt}
.kv .k{flex:0 0 74px;color:var(--accent);font-weight:600}
.kv .v{flex:1;color:var(--sub)}
.kv .v b{color:var(--ink);font-weight:600}
""" + EDITABLE_CSS

PRINT_SINGLE = """
@media print{
  @page{size:A4;margin:0}
  body{background:#fff}
  .toolbar{display:none!important}
  .page{width:auto;min-height:auto;margin:0;padding:13mm 16mm;box-shadow:none}
  [contenteditable="true"]:hover,[contenteditable="true"]:focus{background:none!important;outline:none!important}
}
"""


def _h2(title: str) -> str:
    return f'<h2 contenteditable="true">{title}</h2>'


def render(r) -> str:
    header = (
        '<header class="hd">'
        f'<h1 contenteditable="true">{_esc(r.name)}</h1>'
        f'<div class="affil" contenteditable="true">{_esc(r.title)}</div>'
        f'<div class="contact" contenteditable="true">{contact_spans_html(r)}</div>'
        "</header>"
    )

    parts: list[str] = [header]

    if r.education:
        parts.append(_h2("教育背景"))
        for e in r.education:
            points = [str(x) for x in (e.description, e.gpa and f"GPA {e.gpa}", e.courses) if x]
            parts.append(
                '<div class="item">'
                + item_hd(e.school, e.degree, e.period)
                + (bullets_html(points) if points else "")
                + "</div>"
            )

    if r.summary:
        parts.append(_h2("研究方向"))
        parts.append(
            f'<p style="font-size:10pt;color:var(--sub);text-align:justify" '
            f'contenteditable="true">{bold_numbers(r.summary)}</p>'
        )

    if r.publications:
        parts.append(_h2("发表论文"))
        lis = []
        for pub in r.publications:
            tags = "".join(
                f' <span class="tag">{_esc(t)}</span>' for t in pub.tags
            )
            venue = f", <em>{_esc(pub.venue)}</em>" if pub.venue else ""
            year = f", {pub.year}" if pub.year else ""
            lis.append(
                f"<li><b>{_esc(pub.title)}</b>{venue}{year}.{tags}</li>"
            )
        parts.append(f'<ol class="pubs" contenteditable="true">{"".join(lis)}</ol>')

    if r.merged_projects():
        parts.append(_h2("科研项目"))
        for p in r.merged_projects():
            points = [str(h) for h in p.highlights if str(h).strip()]
            if not points and p.description:
                points = [p.description]
            if not points and p.impact:
                points = [p.impact]
            parts.append(
                '<div class="item">'
                + item_hd(p.name, p.role, p.year)
                + bullets_html(points)
                + "</div>"
            )

    if r.experiences:
        parts.append(_h2("工作经历"))
        for e in r.experiences:
            parts.append(
                '<div class="item">'
                + item_hd(e.company, exp_meta(e), e.period)
                + exp_content_html(e)
                + "</div>"
            )

    if r.honors:
        parts.append(_h2("获奖与荣誉"))
        for item in r.honors:
            key, _, value = str(item).partition("：")
            if not value:
                key, value = "", str(item)
            parts.append(kv_row(key or "荣誉", bold_numbers(value)))

    kv_rows = ""
    if r.certifications:
        kv_rows += kv_row("资质", "、".join(_esc(x) for x in r.certifications))
    if r.languages:
        kv_rows += kv_row("语言", "、".join(_esc(x) for x in r.languages))
    if r.public_work:
        kv_rows += kv_row("学术服务", "；".join(_esc(x) for x in r.public_work))
    if kv_rows:
        parts.append(_h2("学术服务与其他"))
        parts.append(kv_rows)

    return '<div class="page">' + "".join(parts) + "</div>"
