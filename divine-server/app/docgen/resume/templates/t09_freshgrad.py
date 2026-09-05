"""模板 09 · 应届校招版 — 教育置顶信息框，突出课程/竞赛/实习。"""

from __future__ import annotations

try:
    from .components import (
        EDITABLE_CSS,
        _esc,
        bold_numbers,
        bullets_html,
        chip_item,
        contact_lines_html,
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
        contact_lines_html,
        exp_bullets,
        exp_content_html,
        exp_meta,
        item_hd,
    )

id = "tpl_freshgrad"

CSS = """:root{
  --sans:"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;
  --ink:#1b2430; --sub:#4c5866; --mute:#8b96a5; --line:#e1e6ec;
  --brand:#1d8a7a; --brand-soft:#e4f4f1; --band:#f5f8fa;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:#eceae5;color:var(--ink);font-family:var(--sans);font-size:10.5pt;line-height:1.54;-webkit-font-smoothing:antialiased}

.toolbar{position:fixed;top:0;left:0;right:0;z-index:9;display:flex;align-items:center;gap:14px;
  padding:10px 18px;background:#1b2430;color:#eaf0f5;font-size:12px}
.toolbar b{font-weight:500}
.toolbar button{font:inherit;background:#eaf0f5;color:#1b2430;border:0;border-radius:5px;padding:5px 14px;cursor:pointer}
.toolbar button:hover{background:#fff}
.toolbar .tip{color:#93a4b5}

.page{width:210mm;min-height:297mm;background:#fff;margin:52px auto 32px;box-shadow:0 1px 5px rgba(0,0,0,.14)}

.hd{background:var(--brand);color:#fff;padding:10mm 15mm 8mm;
  display:flex;align-items:center;justify-content:space-between;gap:16px}
.hd h1{font-size:24pt;font-weight:600;letter-spacing:.06em}
.hd .role{margin-top:4px;font-size:10.5pt;color:#bfe5de;letter-spacing:.04em}
.hd .school{margin-top:5px;font-size:9.5pt;color:#d7efeb}
.hd .r{text-align:right;font-size:9pt;color:#d7efeb;line-height:1.75;flex:none}

.body{padding:9mm 15mm 12mm}

h2{font-size:9.5pt;font-weight:600;letter-spacing:.18em;color:var(--brand);margin:15px 0 7px;
  display:flex;align-items:center;gap:8px}
h2::before{content:"";font-size:0;width:3px;height:12px;background:var(--brand);border-radius:1px;flex:none}
h2::after{content:"";font-size:0;flex:1;height:.5px;background:var(--line)}
h2:first-child{margin-top:0}

.item{margin-bottom:11px}
.item-hd{display:flex;align-items:baseline;gap:10px}
.org{font-size:10.5pt;font-weight:600}
.meta{font-size:9.5pt;color:var(--sub)}
.date{margin-left:auto;font-size:9pt;color:var(--mute);font-variant-numeric:tabular-nums;white-space:nowrap}
ul{list-style:none;margin-top:5px}
li{position:relative;padding-left:13px;margin-bottom:3.5px;font-size:10pt;text-align:justify}
li::before{content:"";font-size:0;position:absolute;left:1px;top:8px;width:4px;height:4px;border-radius:50%;background:var(--brand);opacity:.6}
li b{font-weight:600;color:#136b5e}

.edu-box{border:.5px solid var(--line);background:var(--band);padding:10px 13px;margin-bottom:9px}
.edu-box .t{font-size:11pt;font-weight:600}
.edu-box .s{font-size:9.5pt;color:var(--sub);margin-top:2px}
.edu-box .g{display:flex;gap:20px;margin-top:7px;flex-wrap:wrap}
.edu-box .g div{font-size:9.5pt;color:var(--sub)}
.edu-box .g div b{color:var(--ink);font-weight:600}

.courses{font-size:9.5pt;color:var(--sub);line-height:1.75}
.courses b{color:var(--ink);font-weight:600}

.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{font-size:9pt;background:var(--brand-soft);color:#12655a;padding:3px 10px;border-radius:11px}

.two{display:flex;gap:26px}
.two .col{flex:1;min-width:0}

""" + EDITABLE_CSS

PRINT_SINGLE = """
@media print{
  @page{size:A4;margin:0}
  body{background:#fff}
  .toolbar{display:none!important}
  .page{width:auto;min-height:auto;margin:0;box-shadow:none}
  .hd,.chip,.edu-box{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .item{break-inside:avoid}
  [contenteditable="true"]:hover,[contenteditable="true"]:focus{background:none!important;outline:none!important}
}
"""


def _h2(title: str) -> str:
    return f'<h2 contenteditable="true">{title}</h2>'


def render(r) -> str:
    first_edu = r.education[0] if r.education else None
    header = (
        '<header class="hd"><div>'
        f'<h1 contenteditable="true">{_esc(r.name)}</h1>'
        f'<div class="role" contenteditable="true">{_esc(r.title)}</div>'
        + (
            f'<div class="school" contenteditable="true">{_esc(first_edu.school + " · " + first_edu.degree)}</div>'
            if first_edu
            else ""
        )
        + "</div>"
        f'<div class="r" contenteditable="true">{contact_lines_html(r)}</div>'
        "</header>"
    )

    inner: list[str] = []

    if first_edu:
        facts = []
        if first_edu.gpa:
            facts.append(f"GPA <b>{_esc(first_edu.gpa)}</b>")
        if first_edu.description:
            facts.append(bold_numbers(first_edu.description))
        if r.certifications:
            facts.append(_esc("、".join(r.certifications)))
        fact_html = "".join(f"<div contenteditable=\"true\">{f}</div>" for f in facts)
        inner.append(_h2("教育背景"))
        inner.append(
            '<div class="edu-box">'
            f'<div class="t" contenteditable="true">{_esc(first_edu.school)} · {_esc(first_edu.degree)}</div>'
            f'<div class="s" contenteditable="true">{_esc(first_edu.period)}</div>'
            f'<div class="g">{fact_html}</div>'
            "</div>"
        )
        if first_edu.courses:
            inner.append(
                f'<p class="courses" contenteditable="true"><b>核心课程</b>　{bold_numbers(first_edu.courses)}</p>'
            )

    work_label = "工作经历"
    if r.experiences and all("实习" in (e.title or "") for e in r.experiences):
        work_label = "实习经历"
    if r.experiences:
        inner.append(_h2(work_label))
        for e in r.experiences:
            inner.append(
                '<div class="item">'
                + item_hd(e.company, exp_meta(e), e.period)
                + exp_content_html(e)
                + "</div>"
            )

    if r.projects:
        inner.append(_h2("项目经历"))
        for p in r.projects:
            points = [str(h) for h in p.highlights if str(h).strip()]
            if not points and p.description:
                points = [line.strip() for line in p.description.splitlines() if line.strip()]
            if not points and p.impact:
                points = [p.impact]
            inner.append(
                '<div class="item">'
                + item_hd(p.name, p.role, p.year)
                + bullets_html(points)
                + "</div>"
            )

    if r.honors:
        inner.append(_h2("竞赛与荣誉"))
        lis = "".join(f"<li>{bold_numbers(x)}</li>" for x in r.honors)
        inner.append(f'<ul contenteditable="true">{lis}</ul>')

    chips = [chip_item(s.name) for s in r.skills if s.name.strip()]
    if not chips and r.core_skills:
        chips = [f'<span class="chip" contenteditable="true">{_esc(x)}</span>' for x in r.core_skills]
    if chips:
        inner.append(_h2("专业技能"))
        inner.append(f'<div class="chips">{"".join(chips)}</div>')

    if r.highlights:
        inner.append(_h2("校园与自我描述"))
        half = (len(r.highlights) + 1) // 2
        cols = []
        for group in (r.highlights[:half], r.highlights[half:]):
            lis = "".join(f"<li>{bold_numbers(x)}</li>" for x in group)
            cols.append(f'<div class="col"><ul contenteditable="true">{lis}</ul></div>')
        inner.append(f'<div class="two">{"".join(cols)}</div>')

    body = f'<div class="body">{"".join(inner)}</div>'
    return f'<div class="page">{header}{body}</div>'
