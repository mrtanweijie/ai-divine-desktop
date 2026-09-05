"""模板 01 · 经典专业版 — 衬线经典，金融/咨询/法律/财会。

CSS 转写自外部母版（单文件 HTML），打印块按单页/多页模式拼装。
"""

from __future__ import annotations

try:
    from .components import (
        EDITABLE_CSS,
        _esc,
        bold_numbers,
        bullets_html,
        contact_spans_html,
        exp_content_html,
        exp_meta,
        item_hd,
        kv_row,
        skill_kv_pairs,
    )
except ImportError:  # 兼容脚本直接运行
    from components import (  # type: ignore
        EDITABLE_CSS,
        _esc,
        bold_numbers,
        bullets_html,
        contact_spans_html,
        exp_content_html,
        exp_meta,
        item_hd,
        kv_row,
        skill_kv_pairs,
    )

id = "tpl_professional"

CSS = """:root{
  --sans:"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;
  --serif:"Songti SC","STSong","Source Han Serif SC","Noto Serif CJK SC",Georgia,serif;
  --ink:#1c1c1c; --sub:#4a4a4a; --mute:#6b6b6b; --line:#c9c6be; --accent:#1f3a5f;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:#eceae5;color:var(--ink);font-family:var(--sans);font-size:10.5pt;line-height:1.6;-webkit-font-smoothing:antialiased}

.toolbar{position:fixed;top:0;left:0;right:0;z-index:9;display:flex;align-items:center;gap:14px;
  padding:10px 18px;background:#1c1c1c;color:#f2f0eb;font-size:12px;font-family:var(--sans)}
.toolbar b{font-weight:500}
.toolbar button{font:inherit;background:#f2f0eb;color:#1c1c1c;border:0;border-radius:5px;padding:5px 14px;cursor:pointer}
.toolbar button:hover{background:#fff}
.toolbar .tip{color:#a9a6a0}

.page{width:210mm;min-height:297mm;background:#fff;margin:52px auto 32px;padding:15mm 17mm;
  box-shadow:0 1px 5px rgba(0,0,0,.14)}

.hd{text-align:left;padding-bottom:6px}
.hd h1{font-family:var(--serif);font-size:25pt;font-weight:600;letter-spacing:.28em}
.hd .contact{margin-top:7px;font-size:9.5pt;color:var(--sub);letter-spacing:.02em}
.hd .contact span::after{content:"|";color:var(--line);margin:0 8px}
.hd .contact span:last-child::after{content:"";font-size:0}

h2{font-family:var(--serif);font-size:11.5pt;font-weight:600;letter-spacing:.2em;
  text-align:left;color:var(--accent);margin:16px 0 2px}
.rule{height:0;border-top:1.4px solid var(--accent);border-bottom:.5px solid var(--line);
  padding-bottom:2.5px;margin-bottom:9px}

.summary{font-size:10pt;color:var(--sub);text-align:justify;line-height:1.7}
.summary b{color:var(--ink);font-weight:600}

.item{margin-bottom:11px}
.item-hd{display:flex;align-items:baseline;gap:10px}
.org{font-weight:600;font-size:10.5pt}
.meta{color:var(--sub);font-size:9.5pt}
.date{margin-left:auto;font-size:9.5pt;color:var(--mute);font-variant-numeric:tabular-nums;white-space:nowrap}
ul{list-style:none;margin-top:4px}
li{position:relative;padding-left:13px;margin-bottom:3px;font-size:10pt;line-height:1.62;text-align:justify}
li::before{content:"";position:absolute;left:1px;top:.58em;width:4.5px;height:4.5px;border-radius:50%;background:var(--accent)}
/* 嵌套项目层级：导语（标题）大圆点，成果点小圆点且与标题首字水平对齐 */
li.lead{margin-top:5px}
li.lead::before{width:5.5px;height:5.5px;top:.5em;background:var(--ink)}
li.sub{padding-left:22px}
li.sub::before{left:13px;width:3.5px;height:3.5px;top:.62em;background:var(--mute)}
li b{font-weight:600}

.kv{display:flex;gap:10px;margin-bottom:5px;font-size:10pt;line-height:1.62}
.kv .k{flex:0 0 62px;color:var(--accent);font-weight:600}
.kv .v{flex:1;color:var(--sub)}
.kv .v b{color:var(--ink);font-weight:600}

""" + EDITABLE_CSS

PRINT_SINGLE = """
@media print{
  @page{size:A4;margin:0}
  body{background:#fff}
  .toolbar{display:none!important}
  .page{width:auto;min-height:auto;margin:0;padding:14mm 16mm;box-shadow:none}
  [contenteditable="true"]:hover,[contenteditable="true"]:focus{background:none!important;outline:none!important}
}
"""


def _section(title: str, inner: str) -> str:
    if not inner:
        return ""
    return f'<h2 contenteditable="true">{title}</h2><div class="rule"></div>{inner}'


def render(r) -> str:
    parts: list[str] = []

    header = (
        '<header class="hd">'
        f'<h1 contenteditable="true">{_esc(r.name)}</h1>'
        f'<div class="contact" contenteditable="true">{contact_spans_html(r)}</div>'
        "</header>"
    )

    summary_html = ""
    if r.summary:
        summary_html = (
            f'<p class="summary" contenteditable="true">{bold_numbers(r.summary)}</p>'
        )

    exp_inner = ""
    for e in r.experiences:
        exp_inner += (
            '<div class="item">'
            + item_hd(e.company, exp_meta(e), e.period)
            + exp_content_html(e)
            + "</div>"
        )
    exp_html = _section("职业经历", exp_inner)

    proj_inner = ""
    for p in r.merged_projects():
        points = [str(h) for h in p.highlights if str(h).strip()]
        if not points and p.description:
            points = [line.strip() for line in p.description.splitlines() if line.strip()]
        if not points and p.impact:
            points = [p.impact]
        proj_inner += (
            '<div class="item">'
            + item_hd(p.name, p.role, p.year)
            + bullets_html(points)
            + "</div>"
        )
    # 项目板块非必须：无项目时不渲染标题与空板块
    proj_html = _section("项目经历", proj_inner) if proj_inner else ""

    edu_inner = ""
    for e in r.education:
        details = [part for part in (e.description, e.gpa and f"GPA {e.gpa}", e.courses) if part]
        points = "；".join(str(d) for d in details)
        edu_inner += (
            '<div class="item">'
            + item_hd(e.school, e.degree, e.period)
            + (f'<ul><li>{bold_numbers(points)}</li></ul>' if points else "")
            + "</div>"
        )
    edu_html = _section("教育背景", edu_inner)

    kv_rows = ""
    if r.certifications:
        kv_rows += kv_row("专业资质", "、".join(_esc(x) for x in r.certifications))
    pairs, plain = skill_kv_pairs(r)
    for key, value in pairs:
        kv_rows += kv_row(key, bold_numbers(value))
    if plain:
        kv_rows += kv_row("专业技能", "、".join(_esc(x) for x in plain))
    if r.languages:
        kv_rows += kv_row("语言", "、".join(_esc(x) for x in r.languages))
    skill_html = _section("资质与技能", kv_rows)

    parts.append(header)
    parts.append(_section(getattr(r, "summary_title", "") or "职业概述", summary_html))
    parts.append(exp_html)
    parts.append(proj_html)
    parts.append(edu_html)
    parts.append(skill_html)
    return '<div class="page">' + "".join(parts) + "</div>"
