"""模板 03 · 极简工程版 — 零色彩零装饰，资深工程师/架构师。"""

from __future__ import annotations

try:
    from .components import (
        EDITABLE_CSS,
        _esc,
        bold_numbers,
        bullets_html,
        exp_bullets,
        exp_content_html,
        exp_meta,
        item_hd,
        kv_row,
        skill_kv_pairs,
    )
    from .helpers import _compact_contact_items
except ImportError:  # 兼容脚本直接运行
    from components import (  # type: ignore
        EDITABLE_CSS,
        _esc,
        bold_numbers,
        bullets_html,
        exp_bullets,
        exp_content_html,
        exp_meta,
        item_hd,
        kv_row,
        skill_kv_pairs,
    )
    from .helpers import _compact_contact_items

id = "tpl_minimal"

CSS = """:root{
  --sans:"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;
  --ink:#141414; --sub:#3d3d3d; --mute:#8a8a8a; --hair:#e2e2e2;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:#eceae5;color:var(--ink);font-family:var(--sans);font-size:10pt;line-height:1.66;-webkit-font-smoothing:antialiased}

.toolbar{position:fixed;top:0;left:0;right:0;z-index:9;display:flex;align-items:center;gap:14px;
  padding:10px 18px;background:#141414;color:#f4f4f4;font-size:12px;font-family:var(--sans)}
.toolbar b{font-weight:500}
.toolbar button{font:inherit;background:#f4f4f4;color:#141414;border:0;border-radius:5px;padding:5px 14px;cursor:pointer}
.toolbar button:hover{background:#fff}
.toolbar .tip{color:#a4a4a4}

.page{width:210mm;min-height:297mm;background:#fff;margin:52px auto 32px;padding:16mm 18mm;
  box-shadow:0 1px 5px rgba(0,0,0,.14)}

.hd{margin-bottom:20px}
.hd h1{font-size:20pt;font-weight:500;letter-spacing:.02em}
.hd .role{margin-top:3px;font-size:10pt;color:var(--mute);letter-spacing:.04em}
.hd .contact{margin-top:9px;font-size:9pt;color:var(--sub)}
.hd .contact span{margin-right:16px}

h2{font-size:8.5pt;font-weight:500;letter-spacing:.22em;color:var(--mute);
  margin:20px 0 9px;text-transform:uppercase}

.summary{font-size:10pt;color:var(--sub);line-height:1.72;text-align:justify;max-width:158mm}
.summary b{color:var(--ink);font-weight:600}

.item{margin-bottom:14px}
.item-hd{display:flex;align-items:baseline;gap:10px}
.org{font-weight:600;font-size:10.5pt}
.meta{font-size:9.5pt;color:var(--mute)}
.date{margin-left:auto;font-size:9pt;color:var(--mute);font-variant-numeric:tabular-nums;white-space:nowrap}
ul{list-style:none;margin-top:5px}
li{position:relative;padding-left:14px;margin-bottom:3.5px;color:var(--sub);text-align:justify}
li::before{content:"";font-size:0;position:absolute;left:2px;top:9px;width:5px;height:.5px;background:var(--mute)}
li b{color:var(--ink);font-weight:600}

.line{display:flex;gap:12px;font-size:9.5pt;margin-bottom:6px}
.line .k{flex:0 0 58px;color:var(--mute)}
.line .v{flex:1;color:var(--sub)}

.stack{font-size:9.5pt;color:var(--sub);line-height:1.8}
.stack b{color:var(--ink);font-weight:600}
""" + EDITABLE_CSS

PRINT_SINGLE = """
@media print{
  @page{size:A4;margin:0}
  body{background:#fff}
  .toolbar{display:none!important}
  .page{width:auto;min-height:auto;margin:0;padding:15mm 17mm;box-shadow:none}
  [contenteditable="true"]:hover,[contenteditable="true"]:focus{background:none!important;outline:none!important}
}
"""


def _h2(title: str) -> str:
    return f'<h2 contenteditable="true">{title}</h2>'


def _line(key: str, value_html: str) -> str:
    return (
        '<div class="line"><div class="k" contenteditable="true">'
        f"{_esc(key)}</div><div class=\"v\" contenteditable=\"true\">{value_html}</div></div>"
    )


def render(r) -> str:
    contact_html = "".join(f"<span>{item}</span>" for item in _compact_contact_items(r))
    header = (
        '<header class="hd">'
        f'<h1 contenteditable="true">{_esc(r.name)}</h1>'
        f'<div class="role" contenteditable="true">{_esc(r.title)}</div>'
        f'<div class="contact" contenteditable="true">{contact_html}</div>'
        "</header>"
    )

    parts: list[str] = [header]
    if r.summary:
        parts.append(_h2(getattr(r, "summary_title", "") or "简介"))
        parts.append(f'<p class="summary" contenteditable="true">{bold_numbers(r.summary)}</p>')

    if r.experiences:
        parts.append(_h2("工作经历"))
        for e in r.experiences:
            parts.append(
                '<div class="item">'
                + item_hd(e.company, exp_meta(e), e.period)
                + exp_content_html(e)
                + "</div>"
            )

    if r.merged_projects():
        parts.append(_h2("项目经历"))
        for p in r.merged_projects():
            points = [str(h) for h in p.highlights if str(h).strip()]
            if not points and p.description:
                points = [line.strip() for line in p.description.splitlines() if line.strip()]
            if not points and p.impact:
                points = [p.impact]
            parts.append(
                '<div class="item">'
                + item_hd(p.name, p.role, p.year)
                + bullets_html(points)
                + "</div>"
            )

    pairs, plain = skill_kv_pairs(r)
    if pairs or plain or r.certifications or r.languages:
        parts.append(_h2("技术栈与其他"))
        for key, value in pairs:
            parts.append(_line(key, bold_numbers(value)))
        if plain:
            parts.append(_line("技能", _esc("、".join(plain))))
        if r.certifications:
            parts.append(_line("资质", _esc("、".join(r.certifications))))
        if r.languages:
            parts.append(_line("语言", _esc("、".join(r.languages))))

    if r.education:
        parts.append(_h2("教育背景"))
        for e in r.education:
            value = " · ".join(str(x) for x in (e.school, e.degree) if x)
            if e.gpa:
                value += f" · GPA {e.gpa}"
            parts.append(_line(e.period, bold_numbers(value)))

    if r.honors or r.publications:
        parts.append(_h2("荣誉与成果"))
        for item in r.honors:
            parts.append(_line("荣誉", bold_numbers(item)))
        for pub in r.publications:
            text = f"{pub.title}. {pub.venue}, {pub.year}." if pub.venue else pub.title
            if pub.tags:
                text += "（" + "、".join(pub.tags) + "）"
            parts.append(_line("论文", _esc(text)))

    return '<div class="page">' + "".join(parts) + "</div>"
