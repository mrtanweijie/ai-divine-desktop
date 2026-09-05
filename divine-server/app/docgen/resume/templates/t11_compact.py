"""模板 11 · 双栏紧凑版 — 左深色信息栏 + 右主内容，信息密度最高。

注意：双栏对老旧 ATS 有解析风险（工具条提示中已注明）。多页打印时
侧栏自动转顶部通栏（MULTI_EXTRA），避免第二页大面积空白。
"""

from __future__ import annotations

try:
    from .components import (
        EDITABLE_CSS,
        _esc,
        bold_numbers,
        bullets_html,
        contact_items,
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
        contact_items,
        exp_bullets,
        exp_content_html,
        exp_meta,
        item_hd,
    )

id = "tpl_compact"

CSS = """:root{
  --sans:"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;
  --ink:#1e2733; --sub:#4b5665; --mute:#8792a2; --line:#dfe4ea;
  --brand:#3d5a80; --band:#f4f6f9; --side:#2c3e56;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:#eceae5;color:var(--ink);font-family:var(--sans);font-size:10pt;line-height:1.55;-webkit-font-smoothing:antialiased}

.toolbar{position:fixed;top:0;left:0;right:0;z-index:9;display:flex;align-items:center;gap:14px;
  padding:10px 18px;background:#1e2733;color:#edf1f5;font-size:12px}
.toolbar b{font-weight:500}
.toolbar button{font:inherit;background:#edf1f5;color:#1e2733;border:0;border-radius:5px;padding:5px 14px;cursor:pointer}
.toolbar button:hover{background:#fff}
.toolbar .tip{color:#95a3b5}

.page{width:210mm;min-height:297mm;background:#fff;margin:52px auto 32px;display:flex;
  box-shadow:0 1px 5px rgba(0,0,0,.14)}

.side{width:58mm;flex:none;background:var(--side);color:#e8edf3;padding:11mm 8mm}
.side h1{font-size:20pt;font-weight:600;letter-spacing:.1em;line-height:1.25}
.side .role{margin-top:5px;font-size:9pt;color:#9fb3cd;letter-spacing:.06em;line-height:1.5}
.side .div{height:1px;background:#4a5d78;margin:11px 0}
.side h3{font-size:8.5pt;font-weight:600;letter-spacing:.2em;color:#9fb3cd;margin-bottom:6px}
.side p,.side li{font-size:8.8pt;color:#d5dde7;line-height:1.62}
.side ul{list-style:none}
.side li{margin-bottom:4px}
.side .block{margin-bottom:12px}
.side .bar{height:3px;background:#4a5d78;border-radius:2px;margin-top:3px}
.side .bar i{display:block;height:100%;background:#8fb3dd;border-radius:2px}

.main{flex:1;min-width:0;padding:11mm 10mm 11mm 9mm}
.main h2{font-size:9.5pt;font-weight:600;letter-spacing:.16em;color:var(--brand);
  padding-bottom:3px;border-bottom:1px solid var(--brand);margin:0 0 7px}
.main h2:not(:first-child){margin-top:13px}

.summary{font-size:9.5pt;color:var(--sub);text-align:justify;line-height:1.68}
.summary b{color:var(--ink);font-weight:600}

.item{margin-bottom:10px}
.item-hd{display:flex;align-items:baseline;gap:8px}
.org{font-size:10pt;font-weight:600}
.meta{font-size:8.8pt;color:var(--sub)}
.date{margin-left:auto;font-size:8.5pt;color:var(--mute);font-variant-numeric:tabular-nums;white-space:nowrap}
ul{list-style:none;margin-top:4px}
li{position:relative;padding-left:11px;margin-bottom:3px;font-size:9.3pt;line-height:1.58;text-align:justify}
li::before{content:"";font-size:0;position:absolute;left:0;top:7px;width:4px;height:4px;border-radius:50%;background:var(--brand);opacity:.55}
li b{font-weight:600;color:#2b4468}

.two{display:flex;gap:18px}
.two .col{flex:1;min-width:0}
""" + EDITABLE_CSS

PRINT_SINGLE = """
@media print{
  @page{size:A4;margin:0}
  body{background:#fff}
  .toolbar{display:none!important}
  .page{width:auto;min-height:auto;margin:0;box-shadow:none;display:flex}
  .side,.side .bar i{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .item{break-inside:avoid}
  [contenteditable="true"]:hover,[contenteditable="true"]:focus{background:none!important;outline:none!important}
}
"""

MULTI_EXTRA = """
@media print{.page{display:block}.side{width:auto}}
"""


def _h2(title: str) -> str:
    return f'<h2 contenteditable="true">{title}</h2>'


def _block(title: str, inner: str, last: bool = False) -> str:
    style = ' style="margin-bottom:0"' if last else ""
    return f'<div class="block"{style}><h3>{title}</h3>{inner}</div>'


def render(r) -> str:
    contact_html = "<br>".join(contact_items(r))
    sites = [s for s in (r.contact.linkedin, r.contact.website, r.contact.github) if s]

    side = ['<aside class="side">']
    side.append(f'<h1 contenteditable="true">{_esc(r.name)}</h1>')
    side.append(f'<div class="role" contenteditable="true">{_esc(r.title)}</div>')
    side.append('<div class="div"></div>')
    side.append(_block("联系方式", f'<p contenteditable="true">{contact_html}</p>'))
    if sites:
        side.append(_block("在线主页", f'<p contenteditable="true">{_esc("<br>".join(sites))}</p>'))
    if r.skills:
        lis = "".join(f"<li contenteditable=\"true\">{_esc(s.name.split('|', 1)[0].strip())}</li>" for s in r.skills[:8] if s.name.strip())
        side.append(_block("核心技能", f'<ul contenteditable="true">{lis}</ul>'))
    if r.skill_groups:
        name, values = next(iter(r.skill_groups.items()))
        side.append(_block(name, f'<p contenteditable="true">{_esc("、".join(values))}</p>'))
    if r.certifications:
        side.append(_block("资质", f'<p contenteditable="true">{_esc("、".join(r.certifications))}</p>'))
    if r.languages:
        side.append(_block("语言", f'<p contenteditable="true">{_esc("；".join(r.languages))}</p>'))
    if r.education:
        e = r.education[0]
        side.append(
            _block(
                "教育背景",
                '<p contenteditable="true">'
                f"<b>{_esc(e.school)}</b><br>{_esc(e.degree)}<br>{_esc(e.period)}</p>",
                last=True,
            )
        )
    side.append("</aside>")

    main: list[str] = []
    if r.summary:
        main.append(_h2(getattr(r, "summary_title", "") or "个人简介"))
        main.append(f'<p class="summary" contenteditable="true">{bold_numbers(r.summary)}</p>')

    if r.experiences:
        main.append(_h2("工作经历"))
        for e in r.experiences:
            main.append(
                '<div class="item">'
                + item_hd(e.company, exp_meta(e), e.period)
                + exp_content_html(e)
                + "</div>"
            )

    if r.merged_projects():
        main.append(_h2("代表项目"))
        cols = []
        for p in r.merged_projects()[:2]:
            points = [str(h) for h in p.highlights if str(h).strip()]
            if not points and p.impact:
                points = [p.impact]
            cols.append(
                '<div class="col item" style="margin-bottom:0">'
                + item_hd(p.name, "", p.year)
                + bullets_html(points)
                + "</div>"
            )
        main.append(f'<div class="two">{"".join(cols)}</div>')

    if r.honors or r.certifications:
        main.append(_h2("荣誉与证书"))
        items = [bold_numbers(x) for x in r.honors] + (
            [_esc("｜".join(r.certifications))] if r.certifications else []
        )
        lis = "".join(f"<li>{item}</li>" for item in items)
        main.append(f'<ul contenteditable="true">{lis}</ul>')

    return '<div class="page">' + "".join(side) + f'<main class="main">{"".join(main)}</main></div>'
