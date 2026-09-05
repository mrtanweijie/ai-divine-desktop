"""模板 02 · 现代科技版 — 顶部色带 + 技能 chip，互联网/科技公司。"""

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

id = "tpl_modern"

CSS = """:root{
  --sans:"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;
  --ink:#12211c; --sub:#48544f; --mute:#7b8580; --line:#dfdcd4;
  --brand:#0f6e56; --brand-soft:#e3f2ed;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:#eceae5;color:var(--ink);font-family:var(--sans);font-size:10.5pt;line-height:1.62;-webkit-font-smoothing:antialiased}

.toolbar{position:fixed;top:0;left:0;right:0;z-index:9;display:flex;align-items:center;gap:14px;
  padding:10px 18px;background:#12211c;color:#eef2f0;font-size:12px;font-family:var(--sans)}
.toolbar b{font-weight:500}
.toolbar button{font:inherit;background:#eef2f0;color:#12211c;border:0;border-radius:5px;padding:5px 14px;cursor:pointer}
.toolbar button:hover{background:#fff}
.toolbar .tip{color:#9fb0a9}

.page{width:210mm;min-height:297mm;background:#fff;margin:52px auto 32px;box-shadow:0 1px 5px rgba(0,0,0,.14)}

.banner{background:var(--brand);color:#fff;padding:12mm 15mm 10mm}
.banner h1{font-size:26pt;font-weight:500;letter-spacing:.04em;line-height:1.2}
.banner .role{margin-top:5px;font-size:11.5pt;color:#9fd8c6;letter-spacing:.06em}
.banner .contact{margin-top:9px;font-size:9.5pt;color:#cfe6dd}
.banner .contact span::after{content:"·";margin:0 7px;color:#5fae97}
.banner .contact span:last-child::after{content:"";font-size:0}

.body{padding:9mm 15mm 12mm}

h2{display:flex;align-items:center;gap:9px;font-size:11.5pt;font-weight:600;letter-spacing:.06em;
  color:var(--brand);margin:15px 0 7px}
h2::before{content:"";font-size:0;width:4px;height:14px;background:var(--brand);border-radius:1px;flex:none}
h2::after{content:"";font-size:0;flex:1;height:.5px;background:var(--line)}
h2:first-child{margin-top:0}

.summary{font-size:10pt;color:var(--sub);text-align:justify;line-height:1.68}
.summary b{color:var(--ink);font-weight:600}

.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{background:var(--brand-soft);color:#0b5745;font-size:9pt;padding:3px 10px;border-radius:11px;line-height:1.5}
.chip.cat{background:#eef1ef;color:var(--mute)}

.item{margin-bottom:12px}
.item-hd{display:flex;align-items:baseline;gap:9px;margin-bottom:2px}
.org{font-size:11pt;font-weight:600}
.meta{font-size:9.5pt;color:var(--sub)}
.date{margin-left:auto;font-size:9pt;color:var(--mute);font-variant-numeric:tabular-nums;white-space:nowrap}
ul{list-style:none;margin-top:3px}
li{position:relative;padding-left:12px;margin-bottom:3.5px;font-size:10pt;line-height:1.64;text-align:justify}
li::before{content:"";font-size:0;position:absolute;left:0;top:8px;width:4px;height:4px;border-radius:50%;background:var(--brand);opacity:.55}
li b{font-weight:600;color:#0b5745}

.two{display:flex;gap:26px}
.two .col{flex:1;min-width:0}
""" + EDITABLE_CSS

PRINT_SINGLE = """
@media print{
  @page{size:A4;margin:0}
  body{background:#fff}
  .toolbar{display:none!important}
  .page{width:auto;min-height:auto;margin:0;box-shadow:none}
  .banner{padding:11mm 15mm 9mm;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .chip{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  [contenteditable="true"]:hover,[contenteditable="true"]:focus{background:none!important;outline:none!important}
}
"""


def _h2(title: str) -> str:
    return f'<h2 contenteditable="true">{title}</h2>'


def render(r) -> str:
    banner = (
        '<header class="banner">'
        f'<h1 contenteditable="true">{_esc(r.name)}</h1>'
        f'<div class="role" contenteditable="true">{_esc(r.title)}</div>'
        f'<div class="contact" contenteditable="true">{contact_spans_html(r)}</div>'
        "</header>"
    )

    inner: list[str] = []
    if r.summary:
        inner.append(_h2(getattr(r, "summary_title", "") or "个人简介"))
        inner.append(f'<p class="summary" contenteditable="true">{bold_numbers(r.summary)}</p>')

    chips = []
    for s in r.skills:
        name = s.name.strip()
        if not name:
            continue
        cls = "chip cat" if name.startswith(("了解", "熟悉", "关注")) else "chip"
        chips.append(chip_item(name, cls))
    if not chips:
        chips = [f'<span class="chip">{_esc(x)}</span>' for x in r.core_skills]
    if chips:
        inner.append(_h2("专业技能"))
        inner.append(f'<div class="chips" contenteditable="true">{"".join(chips)}</div>')

    if r.experiences:
        inner.append(_h2("工作经历"))
        for e in r.experiences:
            inner.append(
                '<div class="item">'
                + item_hd(e.company, exp_meta(e), e.period)
                + exp_content_html(e)
                + "</div>"
            )

    if r.merged_projects():
        inner.append(_h2("开源与项目"))
        for p in r.merged_projects():
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

    if r.education or r.certifications:
        inner.append(_h2("教育背景"))
        cols: list[str] = []
        for e in r.education[:2]:
            points = [part for part in (e.degree, e.description, e.gpa and f"GPA {e.gpa}") if part]
            cols.append(
                '<div class="col item" style="margin-bottom:0">'
                + item_hd(e.school, "", e.period)
                + f"<ul><li>{_esc(' · '.join(str(x) for x in points))}</li></ul></div>"
            )
        if r.certifications:
            cols.append(
                '<div class="col item" style="margin-bottom:0">'
                + item_hd("补充认证")
                + f"<ul><li>{_esc(' · '.join(r.certifications))}</li></ul></div>"
            )
        inner.append(f'<div class="two">{"".join(cols)}</div>')

    body = f'<div class="body">{"".join(inner)}</div>'
    return f'<div class="page">{banner}{body}</div>'
