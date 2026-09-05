"""模板 06 · 创意设计版 — 作品卡片网格，品牌/视觉/交互设计师。"""

from __future__ import annotations

try:
    from .components import (
        EDITABLE_CSS,
        _esc,
        bold_numbers,
        bullets_html,
        contact_lines_html,
        exp_bullets,
        exp_content_html,
        exp_meta,
        item_hd,
        page_foot,
        skill_kv_pairs,
    )
except ImportError:  # 兼容脚本直接运行
    from components import (  # type: ignore
        EDITABLE_CSS,
        _esc,
        bold_numbers,
        bullets_html,
        contact_lines_html,
        exp_bullets,
        exp_content_html,
        exp_meta,
        item_hd,
        page_foot,
        skill_kv_pairs,
    )

id = "tpl_creative"

CSS = """:root{
  --sans:"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;
  --ink:#111; --sub:#4b4b4b; --mute:#8c8c8c; --line:#e0ddd6;
  --accent:#c94f2c; --paper:#fbfaf7;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:#eceae5;color:var(--ink);font-family:var(--sans);font-size:10.5pt;line-height:1.55;-webkit-font-smoothing:antialiased}

.toolbar{position:fixed;top:0;left:0;right:0;z-index:9;display:flex;align-items:center;gap:14px;
  padding:10px 18px;background:#111;color:#f5f3ee;font-size:12px}
.toolbar b{font-weight:500}
.toolbar button{font:inherit;background:#f5f3ee;color:#111;border:0;border-radius:5px;padding:5px 14px;cursor:pointer}
.toolbar button:hover{background:#fff}
.toolbar .tip{color:#a6a29a}

.page{width:210mm;min-height:297mm;background:var(--paper);margin:52px auto 32px;padding:13mm 15mm 11mm;
  box-shadow:0 1px 5px rgba(0,0,0,.14)}

.hd{display:flex;align-items:flex-end;justify-content:space-between;
  border-bottom:2px solid var(--ink);padding-bottom:10px}
.hd .l h1{font-size:30pt;font-weight:600;letter-spacing:-.02em;line-height:1}
.hd .l .role{margin-top:7px;font-size:10.5pt;color:var(--accent);letter-spacing:.14em}
.hd .r{text-align:right;font-size:9pt;color:var(--sub);line-height:1.72}

h2{font-size:9pt;font-weight:600;letter-spacing:.26em;color:var(--mute);
  margin:13px 0 8px;text-transform:uppercase}
h2::before{content:"";font-size:0;display:inline-block;width:16px;height:1px;background:var(--accent);
  vertical-align:middle;margin-right:9px}

.intro{font-size:10.5pt;color:var(--sub);line-height:1.64;max-width:150mm}
.intro b{color:var(--ink);font-weight:600}

.works{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.work{border:.5px solid var(--line);padding:8px 11px;background:#fff}
.work .no{font-size:8.5pt;color:var(--accent);letter-spacing:.1em;font-variant-numeric:tabular-nums}
.work .t{font-size:11pt;font-weight:600;margin-top:3px}
.work .m{font-size:8.5pt;color:var(--mute);margin-top:2px}
.work .d{font-size:9.4pt;color:var(--sub);margin-top:5px;line-height:1.52}
.work .k{font-size:9.5pt;color:var(--accent);font-weight:600;margin-top:5px}

.item{margin-bottom:12px}
.item-hd{display:flex;align-items:baseline;gap:10px}
.org{font-size:11pt;font-weight:600}
.meta{font-size:9.5pt;color:var(--sub)}
.date{margin-left:auto;font-size:9pt;color:var(--mute);font-variant-numeric:tabular-nums;white-space:nowrap}
ul{list-style:none;margin-top:5px}
li{position:relative;padding-left:13px;margin-bottom:3.5px;font-size:10pt;text-align:justify}
li::before{content:"·";position:absolute;left:2px;color:var(--accent);font-weight:600}
li b{font-weight:600}

.skills{display:flex;gap:24px;flex-wrap:wrap}
.skills .g{min-width:120px}
.skills .g .h{font-size:8.5pt;letter-spacing:.12em;color:var(--mute);margin-bottom:3px}
.skills .g .v{font-size:9.5pt;color:var(--sub);line-height:1.7}

.foot{margin-top:16px;padding-top:9px;border-top:.5px solid var(--line);
  display:flex;justify-content:space-between;font-size:8.5pt;color:var(--mute)}
""" + EDITABLE_CSS

PRINT_SINGLE = """
@media print{
  @page{size:A4;margin:0}
  body{background:#fff}
  .toolbar{display:none!important}
  .page{width:auto;min-height:auto;margin:0;padding:14mm 14mm 12mm;box-shadow:none}
  .work{break-inside:avoid}
  [contenteditable="true"]:hover,[contenteditable="true"]:focus{background:none!important;outline:none!important}
}
"""


def _h2(title: str) -> str:
    return f'<h2 contenteditable="true">{title}</h2>'


def render(r) -> str:
    header = (
        '<header class="hd">'
        '<div class="l">'
        f'<h1 contenteditable="true">{_esc(r.name)}</h1>'
        f'<div class="role" contenteditable="true">{_esc(r.title)}</div>'
        "</div>"
        f'<div class="r" contenteditable="true">{contact_lines_html(r)}</div>'
        "</header>"
    )

    parts: list[str] = [header]

    if r.summary:
        parts.append(_h2(getattr(r, "summary_title", "") or "About"))
        parts.append(f'<p class="intro" contenteditable="true">{bold_numbers(r.summary)}</p>')

    works = r.works or []
    if not works and r.merged_projects():
        works = [
            type(
                "W",
                (),
                {
                    "name": p.name,
                    "role": p.role,
                    "year": p.year,
                    "description": p.description,
                    "result": p.impact or (p.highlights[0] if p.highlights else ""),
                },
            )()
            for p in r.merged_projects()
        ]
    if works:
        parts.append(_h2("Selected Works"))
        cards = []
        for index, w in enumerate(works[:6], 1):
            meta = " · ".join(str(x) for x in (w.role, w.year) if x)
            cards.append(
                '<div class="work">'
                f'<div class="no" contenteditable="true">{index:02d}</div>'
                f'<div class="t" contenteditable="true">{_esc(w.name)}</div>'
                f'<div class="m" contenteditable="true">{_esc(meta)}</div>'
                f'<div class="d" contenteditable="true">{bold_numbers(w.description)}</div>'
                f'<div class="k" contenteditable="true">{bold_numbers(w.result)}</div>'
                "</div>"
            )
        parts.append(f'<div class="works">{"".join(cards)}</div>')

    if r.experiences:
        parts.append(_h2("Experience"))
        for e in r.experiences:
            parts.append(
                '<div class="item">'
                + item_hd(e.company, exp_meta(e), e.period)
                + exp_content_html(e)
                + "</div>"
            )

    pairs, plain = skill_kv_pairs(r)
    if pairs or plain:
        parts.append(_h2("Capabilities"))
        groups = []
        for name, body in pairs:
            groups.append(
                '<div class="g" contenteditable="true">'
                f'<div class="h">{_esc(name)}</div><div class="v">{bold_numbers(body)}</div></div>'
            )
        if plain:
            body_html = "<br>".join(_esc(s) for s in plain)
            groups.append(
                f'<div class="g" contenteditable="true"><div class="h">SKILLS</div><div class="v">{body_html}</div></div>'
            )
        parts.append(f'<div class="skills" contenteditable="true">{"".join(groups)}</div>')

    if r.education or r.honors:
        parts.append(_h2("Education & Awards"))
        for e in r.education:
            parts.append(
                '<div class="item">'
                + item_hd(e.school, e.degree, e.period)
                + "</div>"
            )
        if r.honors:
            lis = "".join(f"<li>{_esc(x)}</li>" for x in r.honors)
            parts.append(f'<ul contenteditable="true">{lis}</ul>')

    foot = page_foot(
        f"{r.name} · {r.title}" if r.title else r.name,
        r.contact.website or r.contact.github or r.contact.linkedin or r.contact.phone,
    )
    parts.append(foot)
    return '<div class="page">' + "".join(parts) + "</div>"
