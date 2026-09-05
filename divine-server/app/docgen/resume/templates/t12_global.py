"""模板 12 · 国际通用版 — 中英双语对照，外企/出海/国际组织。

双语条目依赖 en_* 扩展字段；未提供英文行时仅渲染中文，结构不变形。
"""

from __future__ import annotations

try:
    from .components import (
        EDITABLE_CSS,
        _esc,
        bold_numbers,
        bullets_html,
        contact_lines_html,
        exp_bullets,
        item_hd,
        page_foot,
    )
except ImportError:  # 兼容脚本直接运行
    from components import (  # type: ignore
        EDITABLE_CSS,
        _esc,
        bold_numbers,
        bullets_html,
        contact_lines_html,
        exp_bullets,
        item_hd,
        page_foot,
    )

id = "tpl_global"

CSS = """:root{
  --sans:"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;
  --ink:#1a1a1a; --sub:#454545; --mute:#7c7c7c; --line:#d2d2d2;
  --eu:#0b3d91; --eu-soft:#e8eef8; --band:#f6f7f9;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:#eceae5;color:var(--ink);font-family:var(--sans);font-size:10pt;line-height:1.6;-webkit-font-smoothing:antialiased}

.toolbar{position:fixed;top:0;left:0;right:0;z-index:9;display:flex;align-items:center;gap:14px;
  padding:10px 18px;background:#0b3d91;color:#eaf0fa;font-size:12px}
.toolbar b{font-weight:500}
.toolbar button{font:inherit;background:#eaf0fa;color:#0b3d91;border:0;border-radius:5px;padding:5px 14px;cursor:pointer}
.toolbar button:hover{background:#fff}
.toolbar .tip{color:#a8bcd8}

.page{width:210mm;min-height:297mm;background:#fff;margin:52px auto 32px;padding:12mm 15mm;
  box-shadow:0 1px 5px rgba(0,0,0,.14)}

.hd{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;
  border-bottom:2px solid var(--eu);padding-bottom:9px}
.hd h1{font-size:21pt;font-weight:600;letter-spacing:.02em}
.hd .en{font-size:11pt;color:var(--eu);letter-spacing:.06em;margin-top:2px}
.hd .role{margin-top:5px;font-size:10pt;color:var(--sub)}
.hd .role i{font-style:normal;color:var(--mute);font-size:9pt}
.hd .r{text-align:right;font-size:8.8pt;color:var(--sub);line-height:1.7;flex:none}

h2{font-size:9pt;font-weight:600;letter-spacing:.14em;color:var(--eu);margin:14px 0 7px;
  padding-bottom:3px;border-bottom:.5px solid var(--line);display:flex;align-items:baseline;gap:8px}
h2 .cn{font-weight:600;letter-spacing:.14em}
h2 .enx{font-weight:400;letter-spacing:.06em;color:#8fa8cc;font-size:8.5pt}
h2 .sp{flex:1}
h2:first-of-type{margin-top:12px}

.summary{font-size:9.8pt;color:var(--sub);text-align:justify;line-height:1.7}
.summary b{color:var(--ink);font-weight:600}

.item{margin-bottom:10px}
.item-hd{display:flex;align-items:baseline;gap:9px}
.org{font-size:10pt;font-weight:600}
.meta{font-size:9pt;color:var(--sub)}
.meta i{font-style:normal;color:var(--mute);font-size:8.5pt}
.date{margin-left:auto;font-size:8.8pt;color:var(--mute);font-variant-numeric:tabular-nums;white-space:nowrap}
ul{list-style:none;margin-top:4px}
li{position:relative;padding-left:13px;margin-bottom:3.5px;font-size:9.6pt;line-height:1.6;text-align:justify}
li::before{content:"–";position:absolute;left:1px;color:var(--eu)}
li b{font-weight:600}
li .en{display:block;color:var(--mute);font-size:8.8pt;line-height:1.5;margin-top:1px}

.grid{display:flex;gap:22px;flex-wrap:wrap}
.grid .g{min-width:150px;font-size:9.4pt;color:var(--sub);line-height:1.7}
.grid .g .h{font-size:8.4pt;letter-spacing:.1em;color:var(--mute);margin-bottom:2px}

.lang{display:flex;gap:20px;flex-wrap:wrap;font-size:9.4pt;color:var(--sub)}
.lang .l{display:flex;align-items:baseline;gap:7px}
.lang .l b{color:var(--ink);font-weight:600;min-width:52px}
.lang .l .lv{font-size:8.6pt;color:var(--mute)}

.foot{margin-top:14px;padding-top:8px;border-top:.5px solid var(--line);
  display:flex;justify-content:space-between;font-size:8.4pt;color:var(--mute)}
""" + EDITABLE_CSS

PRINT_SINGLE = """
@media print{
  @page{size:A4;margin:0}
  body{background:#fff}
  .toolbar{display:none!important}
  .page{width:auto;min-height:auto;margin:0;padding:11mm 14mm;box-shadow:none}
  .item{break-inside:avoid}
  [contenteditable="true"]:hover,[contenteditable="true"]:focus{background:none!important;outline:none!important}
}
"""


def _h2(cn: str, en: str) -> str:
    return (
        f'<h2 contenteditable="true"><span class="cn">{cn}</span>'
        f'<span class="enx">{en}</span><span class="sp"></span></h2>'
    )


def _bilingual_li(zh: str, en: str) -> str:
    en_html = f'<span class="en">{_esc(en)}</span>' if en else ""
    return f"<li>{bold_numbers(zh)}{en_html}</li>"


def render(r) -> str:
    role_en = f' <i>{_esc(r.en_title)}</i>' if r.en_title else ""
    header = (
        '<header class="hd"><div>'
        f'<h1 contenteditable="true">{_esc(r.name)}</h1>'
        + (f'<div class="en" contenteditable="true">{_esc(r.en_name)}</div>' if r.en_name else "")
        + f'<div class="role" contenteditable="true">{_esc(r.title)}{role_en}</div>'
        "</div>"
        f'<div class="r" contenteditable="true">{contact_lines_html(r)}</div>'
        "</header>"
    )

    parts: list[str] = [header]

    if r.summary:
        en_summary = (
            f'<span class="en" contenteditable="true">{_esc(r.en_summary)}</span>'
            if r.en_summary
            else ""
        )
        parts.append(_h2("个人简介", "PROFILE"))
        parts.append(
            f'<p class="summary" contenteditable="true">{bold_numbers(r.summary)}{en_summary}</p>'
        )

    if r.experiences:
        parts.append(_h2("工作经历", "WORK EXPERIENCE"))
        for e in r.experiences:
            title_en = f" <i>{_esc(e.en_title)}</i>" if e.en_title else ""
            company_en = f" <i>{_esc(e.en_company)}</i>" if e.en_company else ""
            org_html = f'<span class="org" contenteditable="true">{_esc(e.company)}{company_en}</span>'
            meta_html = (
                f'<span class="meta" contenteditable="true">{_esc(e.title)}{title_en}</span>'
                if e.title
                else ""
            )
            date_html = f'<span class="date">{_esc(e.period)}</span>' if e.period else ""
            zh_points = exp_bullets(e)
            lis = "".join(
                _bilingual_li(zh, e.en_highlights[i] if i < len(e.en_highlights) else "")
                for i, zh in enumerate(zh_points)
            )
            ul_html = f'<ul contenteditable="true">{lis}</ul>' if lis else ""
            parts.append(
                '<div class="item">'
                f'<div class="item-hd">{org_html}{meta_html}{date_html}</div>'
                + ul_html
                + "</div>"
            )

    if r.projects:
        parts.append(_h2("项目经历", "PROJECTS"))
        for p in r.projects:
            name_en = f" <i>{_esc(p.en_name)}</i>" if p.en_name else ""
            points = [str(h) for h in p.highlights if str(h).strip()]
            lis = "".join(
                _bilingual_li(zh, p.en_highlights[i] if i < len(p.en_highlights) else "")
                for i, zh in enumerate(points)
            )
            parts.append(
                '<div class="item">'
                f'<div class="item-hd"><span class="org" contenteditable="true">{_esc(p.name)}{name_en}</span>'
                f'<span class="meta" contenteditable="true">{_esc(p.role)}</span>'
                f'<span class="date">{_esc(p.year)}</span></div>'
                + (f'<ul contenteditable="true">{lis}</ul>' if lis else "")
                + "</div>"
            )

    if r.education:
        parts.append(_h2("教育背景", "EDUCATION"))
        for e in r.education:
            degree_en = f" <i>{_esc(e.en_degree)}</i>" if e.en_degree else ""
            school_en = f" <i>{_esc(e.en_school)}</i>" if e.en_school else ""
            detail = "；".join(str(x) for x in (e.description, e.gpa and f"GPA {e.gpa}") if x)
            parts.append(
                '<div class="item">'
                f'<div class="item-hd"><span class="org" contenteditable="true">{_esc(e.school)}{school_en}</span>'
                f'<span class="meta" contenteditable="true">{_esc(e.degree)}{degree_en}</span>'
                f'<span class="date">{_esc(e.period)}</span></div>'
                + (f'<ul><li>{bold_numbers(detail)}</li></ul>' if detail else "")
                + "</div>"
            )

    if r.skill_groups:
        parts.append(_h2("专业技能", "SKILLS"))
        groups = []
        for name, values in r.skill_groups.items():
            body_html = "<br>".join(_esc(v) for v in values)
            groups.append(
                f'<div class="g" contenteditable="true"><div class="h">{_esc(name)}</div>{body_html}</div>'
            )
        parts.append(f'<div class="grid">{"".join(groups)}</div>')
    elif r.skills:
        pairs = []
        plain = []
        for s in r.skills:
            if "|" in s.name:
                label, body = s.name.split("|", 1)
                pairs.append((label.strip(), body.strip()))
            else:
                plain.append(s.name)
        if pairs or plain:
            parts.append(_h2("专业技能", "SKILLS"))
            groups = [
                f'<div class="g" contenteditable="true"><div class="h">{_esc(k)}</div>{bold_numbers(v)}</div>'
                for k, v in pairs
            ]
            if plain:
                groups.append(
                    '<div class="g" contenteditable="true"><div class="h">SKILLS</div>'
                    + _esc("、".join(plain))
                    + "</div>"
                )
            parts.append(f'<div class="grid">{"".join(groups)}</div>')

    if r.certifications:
        parts.append(_h2("资质认证", "CERTIFICATION"))
        lis = "".join(f"<li>{_esc(x)}</li>" for x in r.certifications)
        parts.append(f'<ul contenteditable="true">{lis}</ul>')

    if r.languages:
        parts.append(_h2("语言能力", "LANGUAGES"))
        items = []
        for text in r.languages:
            label, _, rest = str(text).partition("（")
            items.append(
                '<div class="l" contenteditable="true">'
                f"<b>{_esc(label)}</b> {_esc(rest.strip('）'))}</div>"
            )
        parts.append(f'<div class="lang">{"".join(items)}</div>')

    foot = page_foot(
        f"{r.name}{' / ' + r.en_name if r.en_name else ''} · {r.title}".strip(" ·"),
        r.contact.phone or r.contact.email,
    )
    parts.append(foot)
    return '<div class="page">' + "".join(parts) + "</div>"
