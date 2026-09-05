"""模板 07 · 产品经理版 — KPI 条 + 产品矩阵表格，B/C 端产品经理。"""

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

id = "tpl_product"

CSS = """:root{
  --sans:"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;
  --ink:#16202b; --sub:#4a5561; --mute:#8b949e; --line:#dfe3e8;
  --brand:#2b5cd9; --brand-soft:#eaf0ff; --band:#f5f7fa;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:#eceae5;color:var(--ink);font-family:var(--sans);font-size:10.5pt;line-height:1.54;-webkit-font-smoothing:antialiased}

.toolbar{position:fixed;top:0;left:0;right:0;z-index:9;display:flex;align-items:center;gap:14px;
  padding:10px 18px;background:#16202b;color:#eef1f5;font-size:12px}
.toolbar b{font-weight:500}
.toolbar button{font:inherit;background:#eef1f5;color:#16202b;border:0;border-radius:5px;padding:5px 14px;cursor:pointer}
.toolbar button:hover{background:#fff}
.toolbar .tip{color:#9aa6b4}

.page{width:210mm;min-height:297mm;background:#fff;margin:52px auto 32px;box-shadow:0 1px 5px rgba(0,0,0,.14)}

.hd{display:flex;align-items:center;gap:16px;padding:10mm 15mm 8mm;border-bottom:2px solid var(--brand)}
.avatar{width:56px;height:56px;flex:none;border-radius:6px;background:var(--brand-soft);
  color:var(--brand);display:flex;align-items:center;justify-content:center;font-size:17pt;font-weight:500}
.hd .l h1{font-size:22pt;font-weight:600;letter-spacing:.02em}
.hd .l .role{margin-top:3px;font-size:10.5pt;color:var(--brand);letter-spacing:.03em}
.hd .r{margin-left:auto;text-align:right;font-size:9pt;color:var(--sub);line-height:1.7}

.body{padding:8mm 15mm 10mm}

h2{font-size:10pt;font-weight:600;letter-spacing:.16em;color:var(--brand);margin:11px 0 6px;
  display:flex;align-items:center;gap:8px}
h2::after{content:"";font-size:0;flex:1;height:.5px;background:var(--line)}
h2:first-child{margin-top:0}

.summary{font-size:10pt;color:var(--sub);text-align:justify;line-height:1.72}
.summary b{color:var(--ink);font-weight:600}

.kpis{display:flex;border:.5px solid var(--line);background:var(--band)}
.kpi{flex:1;padding:9px 10px;text-align:center;border-right:.5px solid var(--line)}
.kpi:last-child{border-right:0}
.kpi .n{font-size:15pt;font-weight:600;color:var(--brand);line-height:1.2;font-variant-numeric:tabular-nums}
.kpi .l{font-size:8.5pt;color:var(--mute);margin-top:2px}

.item{margin-bottom:10px}
.item-hd{display:flex;align-items:baseline;gap:10px}
.org{font-size:11pt;font-weight:600}
.meta{font-size:9.5pt;color:var(--sub)}
.date{margin-left:auto;font-size:9pt;color:var(--mute);font-variant-numeric:tabular-nums;white-space:nowrap}
.scope{display:inline-block;margin-top:3px;font-size:8.5pt;color:var(--sub);
  background:var(--band);border-radius:3px;padding:2px 8px}
ul{list-style:none;margin-top:6px}
li{position:relative;padding-left:14px;margin-bottom:3px;font-size:10pt;text-align:justify}
li::before{content:"▸";position:absolute;left:0;color:var(--brand);font-size:8pt;top:1px}
li b{font-weight:600;color:#1c3f9e}

.products{width:100%;border-collapse:collapse;font-size:9.5pt}
.products th{background:var(--band);color:var(--sub);font-weight:600;text-align:left;
  padding:6px 9px;border-bottom:.5px solid var(--line);font-size:9pt;letter-spacing:.04em}
.products td{padding:5px 9px;border-bottom:.5px solid var(--line);vertical-align:top;line-height:1.5}
.products td:first-child{font-weight:600}
.products .num{color:var(--brand);font-weight:600;font-variant-numeric:tabular-nums;white-space:normal}

.stack{display:flex;gap:22px;flex-wrap:wrap;font-size:9.5pt;color:var(--sub);line-height:1.72}
.stack .g .h{font-size:8.5pt;letter-spacing:.1em;color:var(--mute);margin-bottom:2px}

.foot{margin-top:15px;padding-top:8px;border-top:.5px solid var(--line);
  display:flex;justify-content:space-between;font-size:8.5pt;color:var(--mute)}
""" + EDITABLE_CSS

PRINT_SINGLE = """
@media print{
  @page{size:A4;margin:0}
  body{background:#fff}
  .toolbar{display:none!important}
  .page{width:auto;min-height:auto;margin:0;box-shadow:none}
  .avatar,.kpi,.products th,.scope{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .item{break-inside:avoid}
  [contenteditable="true"]:hover,[contenteditable="true"]:focus{background:none!important;outline:none!important}
}
"""


def _h2(title: str) -> str:
    return f'<h2 contenteditable="true">{title}</h2>'


def _kpis_html(r) -> str:
    if not r.metrics:
        return ""
    cells = []
    for m in r.metrics[:4]:
        cells.append(
            '<div class="kpi">'
            f'<div class="n" contenteditable="true">{_esc(m.value)}</div>'
            f'<div class="l" contenteditable="true">{_esc(m.label)}</div>'
            "</div>"
        )
    return f'<div class="kpis">{"".join(cells)}</div>'


def render(r) -> str:
    avatar = _esc(r.name[:1]) if r.name else ""
    header = (
        '<header class="hd">'
        f'<div class="avatar" contenteditable="true">{avatar}</div>'
        '<div class="l">'
        f'<h1 contenteditable="true">{_esc(r.name)}</h1>'
        f'<div class="role" contenteditable="true">{_esc(r.title)}</div>'
        "</div>"
        f'<div class="r" contenteditable="true">{contact_lines_html(r)}</div>'
        "</header>"
    )

    inner: list[str] = []
    if r.summary:
        inner.append(_h2(getattr(r, "summary_title", "") or "个人简介"))
        inner.append(f'<p class="summary" contenteditable="true">{bold_numbers(r.summary)}</p>')
    kpis = _kpis_html(r)
    if kpis:
        inner.append(kpis)

    if r.experiences:
        inner.append(_h2("工作经历"))
        for e in r.experiences:
            scope = (
                f'<div><span class="scope" contenteditable="true">{_esc(e.dept)}</span></div>'
                if e.dept
                else ""
            )
            inner.append(
                '<div class="item">'
                + item_hd(e.company, exp_meta(e) if e.title else e.title or "", e.period)
                + scope
                + exp_content_html(e)
                + "</div>"
            )

    if r.projects:
        inner.append(_h2("代表产品"))
        rows = []
        for p in r.projects:
            actions = "、".join(str(a) for a in p.actions) if p.actions else p.description
            impact = p.impact or (p.highlights[0] if p.highlights else "")
            rows.append(
                "<tr>"
                f"<td contenteditable=\"true\">{_esc(p.name)}</td>"
                f"<td contenteditable=\"true\">{_esc(p.role)}</td>"
                f"<td contenteditable=\"true\">{bold_numbers(actions)}</td>"
                f'<td class="num" contenteditable="true">{bold_numbers(impact)}</td>'
                "</tr>"
            )
        inner.append(
            '<table class="products"><thead><tr>'
            '<th style="width:26%">产品 / 模块</th><th style="width:14%">角色</th>'
            '<th style="width:30%">关键动作</th><th style="width:30%">结果指标</th>'
            f'</tr></thead><tbody contenteditable="true">{"".join(rows)}</tbody></table>'
        )

    pairs, plain = skill_kv_pairs(r)
    if pairs or plain:
        inner.append(_h2("能力与方法"))
        groups = [
            f'<div class="g" contenteditable="true"><div class="h">{_esc(k)}</div>{bold_numbers(v)}</div>'
            for k, v in pairs
        ]
        if plain:
            groups.append(
                '<div class="g" contenteditable="true"><div class="h">技能</div>'
                + _esc("、".join(plain))
                + "</div>"
            )
        inner.append(f'<div class="stack">{"".join(groups)}</div>')

    if r.education:
        inner.append(_h2("教育背景"))
        for e in r.education[:2]:
            extra = f" · GPA {e.gpa}" if e.gpa else ""
            inner.append(
                '<div class="item" style="margin-bottom:0">'
                + item_hd(e.school, f"{e.degree}{extra}", e.period)
                + "</div>"
            )

    foot = page_foot(
        f"{r.name} · {r.title}" if r.title else r.name,
        r.contact.phone or r.contact.email,
    )
    body = f'<div class="body">{"".join(inner)}{foot}</div>'
    return f'<div class="page">{header}{body}</div>'
