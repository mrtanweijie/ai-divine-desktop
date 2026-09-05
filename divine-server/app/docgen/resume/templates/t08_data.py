"""模板 08 · 数据科学版 — 等宽技术标签，数据/算法/分析岗。"""

from __future__ import annotations

try:
    from .components import (
        EDITABLE_CSS,
        _esc,
        bold_numbers,
        bullets_html,
        chip_item,
        contact_spans_html,
        exp_bullets,
        exp_content_html,
        exp_meta,
        item_hd,
    )
except ImportError:  # 兼容脚本直接运行
    from components import (  # type: ignore
        EDITABLE_CSS,
        _esc,
        bold_numbers,
        bullets_html,
        chip_item,
        contact_spans_html,
        exp_bullets,
        exp_content_html,
        exp_meta,
        item_hd,
    )

id = "tpl_data"

CSS = """:root{
  --sans:"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;
  --mono:"SF Mono","JetBrains Mono","Menlo",Consolas,monospace;
  --ink:#0f1b2d; --sub:#42526b; --mute:#8391a7; --line:#dde3ec;
  --brand:#0b6e99; --brand-soft:#e6f2f7; --band:#f4f7fa;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:#eceae5;color:var(--ink);font-family:var(--sans);font-size:10.5pt;line-height:1.6;-webkit-font-smoothing:antialiased}

.toolbar{position:fixed;top:0;left:0;right:0;z-index:9;display:flex;align-items:center;gap:14px;
  padding:10px 18px;background:#0f1b2d;color:#e9eef5;font-size:12px}
.toolbar b{font-weight:500}
.toolbar button{font:inherit;background:#e9eef5;color:#0f1b2d;border:0;border-radius:5px;padding:5px 14px;cursor:pointer}
.toolbar button:hover{background:#fff}
.toolbar .tip{color:#8ba0b8}

.page{width:210mm;min-height:297mm;background:#fff;margin:52px auto 32px;padding:13mm 15mm 12mm;
  box-shadow:0 1px 5px rgba(0,0,0,.14)}

.hd{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;
  border-left:3px solid var(--brand);padding-left:13px}
.hd h1{font-size:21pt;font-weight:600;letter-spacing:.02em}
.hd .role{margin-top:4px;color:var(--brand);font-family:var(--mono);font-size:9.5pt}
.hd .contact{margin-top:6px;font-size:9pt;color:var(--sub)}
.hd .contact span{margin-right:14px}
.hd .r{text-align:right;font-size:9pt;color:var(--sub);line-height:1.7;flex:none}

h2{font-size:9pt;font-weight:600;letter-spacing:.2em;color:var(--brand);margin:15px 0 8px;
  padding-bottom:3px;border-bottom:.5px solid var(--line)}
h2:first-of-type{margin-top:14px}

.summary{font-size:10pt;color:var(--sub);text-align:justify;line-height:1.7}
.summary b{color:var(--ink);font-weight:600}

.stack{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:2px}
.tag{font-family:var(--mono);font-size:8.5pt;background:var(--brand-soft);color:#075577;
  padding:2.5px 8px;border-radius:3px}
.tag.g{background:var(--band);color:var(--mute)}

.item{margin-bottom:13px}
.item-hd{display:flex;align-items:baseline;gap:10px}
.org{font-size:11pt;font-weight:600}
.meta{font-size:9.5pt;color:var(--sub)}
.date{margin-left:auto;font-size:9pt;color:var(--mute);font-variant-numeric:tabular-nums;white-space:nowrap}
ul{list-style:none;margin-top:5px}
li{position:relative;padding-left:15px;margin-bottom:4px;font-size:10pt;text-align:justify}
li::before{content:"›";position:absolute;left:2px;color:var(--brand);font-weight:600;font-family:var(--mono)}
li b{font-weight:600;color:#075577}
li .tech{font-family:var(--mono);font-size:8.5pt;color:var(--mute)}

.proj{border-left:2px solid var(--line);padding-left:11px;margin-bottom:11px}
.proj .t{font-size:10.5pt;font-weight:600}
.proj .t span{font-weight:400;color:var(--mute);font-size:9pt;margin-left:7px}
.proj .d{font-size:9.5pt;color:var(--sub);margin-top:3px;line-height:1.62;text-align:justify}
.proj .d b{color:var(--ink);font-weight:600}

.two{display:flex;gap:26px}
.two .col{flex:1;min-width:0}
.mini{font-size:9.5pt;color:var(--sub);line-height:1.7}
.mini div span{color:var(--mute);display:inline-block;min-width:52px}
""" + EDITABLE_CSS

PRINT_SINGLE = """
@media print{
  @page{size:A4;margin:0}
  body{background:#fff}
  .toolbar{display:none!important}
  .page{width:auto;min-height:auto;margin:0;padding:12mm 14mm 11mm;box-shadow:none}
  .tag{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .item,.proj{break-inside:avoid}
  [contenteditable="true"]:hover,[contenteditable="true"]:focus{background:none!important;outline:none!important}
}
"""


def _h2(title: str) -> str:
    return f'<h2 contenteditable="true">{title}</h2>'


def render(r) -> str:
    header = (
        '<header class="hd"><div>'
        f'<h1 contenteditable="true">{_esc(r.name)}</h1>'
        f'<div class="role" contenteditable="true">{_esc(r.title)}</div>'
        f'<div class="contact" contenteditable="true">{contact_spans_html(r)}</div>'
        "</div></header>"
    )

    parts: list[str] = [header]

    if r.summary:
        parts.append(_h2(getattr(r, "summary_title", "") or "个人简介"))
        parts.append(f'<p class="summary" contenteditable="true">{bold_numbers(r.summary)}</p>')

    if r.skills or r.core_skills:
        parts.append(_h2("技术栈"))
        tags = []
        for s in r.skills:
            name = s.name.strip()
            if not name:
                continue
            cls = "tag g" if name.startswith(("了解", "熟悉")) else "tag"
            tags.append(chip_item(name, cls))
        if not tags:
            tags = [f'<span class="tag">{_esc(x)}</span>' for x in r.core_skills]
        parts.append(f'<div class="stack" contenteditable="true">{"".join(tags)}</div>')
        if r.skill_groups:
            rows = "".join(
                f"<div><span>{_esc(name)}</span>{_esc('；'.join(values))}</div>"
                for name, values in list(r.skill_groups.items())[:2]
            )
            parts.append(f'<div class="mini" style="margin-top:6px" contenteditable="true">{rows}</div>')

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
        parts.append(_h2("代表项目"))
        for p in r.merged_projects():
            points = [str(h) for h in p.highlights if str(h).strip()]
            if not points and p.impact:
                points = [p.impact]
            sub = " · ".join(str(x) for x in (p.role, p.year) if x)
            sub_html = f"<span>{_esc(sub)}</span>" if sub else ""
            body_html = bold_numbers("；".join(points)) if points else bold_numbers(p.description)
            parts.append(
                '<div class="proj">'
                f'<div class="t" contenteditable="true">{_esc(p.name)}{sub_html}</div>'
                f'<div class="d" contenteditable="true">{body_html}</div>'
                "</div>"
            )

    if r.publications or r.honors:
        parts.append(_h2("论文与荣誉"))
        for pub in r.publications:
            text = f"{pub.title}，{pub.venue}（{pub.year}）" if pub.venue else pub.title
            parts.append(
                '<div class="proj">'
                f'<div class="t" contenteditable="true">论文<span>{_esc(pub.year)}</span></div>'
                f'<div class="d" contenteditable="true">{_esc(text)}</div></div>'
            )
        if r.honors:
            parts.append(f'<div class="mini" contenteditable="true"><div><span>荣誉</span>{_esc("；".join(r.honors))}</div></div>')

    if r.education:
        parts.append(_h2("教育背景"))
        cols = []
        for e in r.education[:2]:
            detail = " · ".join(str(x) for x in (e.degree, e.gpa and f"GPA {e.gpa}") if x)
            cols.append(
                '<div class="col"><div class="mini" contenteditable="true">'
                f"<div><span>{_esc(e.period)}</span><b>{_esc(e.school)}</b></div>"
                f'<div style="color:var(--sub);padding-left:52px">{_esc(detail)}</div></div></div>'
            )
        parts.append(f'<div class="two">{"".join(cols)}</div>')

    return '<div class="page">' + "".join(parts) + "</div>"
