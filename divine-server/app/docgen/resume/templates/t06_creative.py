"""模板 06 · 创意设计版（v2）— 暖纸底 + 赭橙品牌色 + ✦ 星形 bullet。

设计母版：外部模板库 v2/06-creative-创意设计版-v2.html（1:1 转写）。
"""

from __future__ import annotations

try:
    from .components import (
        EDITABLE_CSS,
        _esc,
        bold_numbers,
        contact_lines_html,
        exp_content_html,
        page_foot,
    )
except ImportError:  # 兼容脚本直接运行
    from components import (  # type: ignore
        EDITABLE_CSS,
        _esc,
        bold_numbers,
        contact_lines_html,
        exp_content_html,
        page_foot,
    )

id = "tpl_creative"

CSS = """:root{
  --paper:#fdfbf8; --bg:#ece9e3; --ink:#23201c; --sub:#55504a; --muted:#97907f;
  --line:#e2dcd1; --brand:#b3542f; --brand2:#d98e4a; --soft:#f6ede3;
  --f-d:"PingFang SC","Hiragino Sans GB","Microsoft YaHei",Helvetica,Arial,sans-serif;
  --f-b:"PingFang SC","Hiragino Sans GB","Microsoft YaHei",Helvetica,Arial,sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--ink);font-family:var(--f-b);font-size:10pt;line-height:1.6;-webkit-font-smoothing:antialiased}

.toolbar{position:fixed;top:0;left:0;right:0;z-index:99;display:flex;align-items:center;gap:12px;padding:9px 18px;background:#3a2a20;color:#f6efe8;font-size:12px}
.toolbar b{font-weight:550}.toolbar .tip{margin-left:auto;color:#c2a890;font-size:11px}
.toolbar button{font:inherit;border:0;border-radius:999px;padding:5px 14px;cursor:pointer;background:#f6efe8;color:#3a2a20}

.page{width:210mm;min-height:297mm;background:var(--paper);margin:56px auto 38px;box-shadow:0 2px 18px rgba(40,30,20,.10)}

.hd{padding:14mm 15mm 7mm;display:flex;justify-content:space-between;align-items:flex-start;border-bottom:1px solid var(--ink)}
.hd .l h1{font-size:30pt;font-weight:800;letter-spacing:-.02em;line-height:1.04}
.hd .l .role{margin-top:5px;font-size:11pt;color:var(--brand);font-weight:550}
.hd .r{text-align:right;font-size:8.8pt;color:var(--sub);line-height:1.9}

main{padding:4mm 15mm 11mm}

h2{display:flex;align-items:baseline;gap:8px;font-size:11pt;font-weight:800;letter-spacing:.1em;margin-top:11px;break-after:avoid}
h2 i{font-size:7.6pt;font-weight:600;letter-spacing:.2em;color:var(--brand2)}
h2::after{content:"";flex:1;height:0;border-bottom:1px solid var(--line);transform:translateY(-3px);font-size:0}
section:first-child h2{margin-top:0}

.summary{font-size:9.9pt;line-height:1.76;color:var(--sub);margin-top:6px;max-width:170mm}
.summary b{color:var(--ink);font-weight:650}

.item{margin-top:7px}
.item-hd{display:flex;align-items:baseline;gap:10px}
.item-hd .org{font-size:10.8pt;font-weight:700}
.item-hd .meta{color:var(--brand);font-size:9.3pt}
.item-hd .date{margin-left:auto;color:var(--muted);font-size:8.7pt;font-variant-numeric:tabular-nums;white-space:nowrap}

ul{list-style:none;margin-top:4px}
li{position:relative;padding-left:16px;margin-bottom:2.6px;font-size:9.7pt;line-height:1.66;color:var(--sub)}
li::before{content:"✦";position:absolute;left:0;top:.1em;font-size:8pt;color:var(--brand2)}
li b{color:var(--ink);font-weight:650}

.works{display:grid;grid-template-columns:1fr 1fr;gap:3.5mm;margin-top:3.5mm}
.work{border:1px solid var(--line);background:#fff;padding:4mm 4.5mm;break-inside:avoid}
.work .name{font-size:10.3pt;font-weight:700}
.work .meta{font-size:8.4pt;color:var(--brand);margin-top:1px}
.work .r{margin-top:2.5mm;font-size:9.2pt;color:var(--sub);line-height:1.6}
.work .r b{color:var(--ink)}

.chips{display:flex;flex-wrap:wrap;gap:2mm;margin-top:3.5mm}
.chip{background:var(--soft);border:0;padding:2.6px 11px;font-size:8.8pt;color:var(--sub)}

.foot{display:flex;justify-content:space-between;margin-top:8mm;padding-top:5px;border-top:1px solid var(--line);font-size:8.2pt;color:var(--muted)}
""" + EDITABLE_CSS

PRINT_SINGLE = """
@media print{
  @page{size:A4;margin:0}
  body{background:#fff}
  .toolbar{display:none!important}
  .page{width:auto;min-height:auto;margin:0;box-shadow:none}
  .hd,.work{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .item,.work{break-inside:avoid}
  h2{break-after:avoid}
  [contenteditable="true"]:hover,[contenteditable="true"]:focus{background:none!important;outline:none!important}
}
"""


def _h2(cn: str, en: str) -> str:
    """双字体标题：中文 800 字重 + 英文小字标注（brand2 色）。"""
    return f'<h2 contenteditable="true">{cn} <i>{en}</i></h2>'


def _works_html(r) -> str:
    """作品卡 2×2 网格：works 优先，缺省时由 projects 降级。"""
    works = list(r.works) or [
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
        for p in r.projects
    ]
    if not works:
        return ""
    cards = []
    for w in works[:4]:
        meta = " · ".join(str(x) for x in (w.role, w.year) if x)
        result = f"<b>{bold_numbers(w.result)}</b>" if w.result else ""
        desc = bold_numbers(w.description) if w.description else ""
        body = ""
        if desc and w.result:
            body = f"{desc}，{result}"
        else:
            body = desc or result
        cards.append(
            '<div class="work">'
            f'<div class="name" contenteditable="true">{_esc(w.name)}</div>'
            f'<div class="meta" contenteditable="true">{_esc(meta)}</div>'
            f'<div class="r" contenteditable="true">{body}</div>'
            "</div>"
        )
    return f'<div class="works">{"".join(cards)}</div>'


def _projects_html(r) -> str:
    """项目经历（item 条目式）：merged_projects 合并顶层与经历内嵌套项目。"""
    merged = r.merged_projects()
    if not merged:
        return ""
    items = []
    for p in merged[:6]:
        points = [str(h) for h in p.highlights if str(h).strip()]
        if not points and p.description:
            points = [line.strip() for line in p.description.splitlines() if line.strip()]
        if not points and p.impact:
            points = [p.impact]
        meta = " · ".join(str(x) for x in (p.role, p.year) if x)
        bullets = (
            f'<ul>{"".join(f"<li>{bold_numbers(x)}</li>" for x in points)}</ul>'
            if points
            else ""
        )
        items.append(
            '<div class="item">'
            '<div class="item-hd">'
            f'<span class="org" contenteditable="true">{_esc(p.name)}</span>'
            f'<span class="meta" contenteditable="true">{_esc(meta)}</span>'
            "</div>"
            + bullets
            + "</div>"
        )
    return "".join(items)


def _chips_html(r) -> str:
    """能力 chips：skill_groups 展开为散标签，其次 skills 拆分类名。"""
    labels: list[str] = []
    if r.skill_groups:
        for values in r.skill_groups.values():
            labels.extend(str(v) for v in values)
    else:
        for s in r.skills:
            name = s.name.strip()
            if not name:
                continue
            if "|" in name:
                labels.append(name.split("|", 1)[0].strip())
            else:
                labels.append(name)
    if not labels and r.core_skills:
        labels = list(r.core_skills)
    chips = "".join(
        f'<span class="chip" contenteditable="true">{_esc(x)}</span>' for x in labels if x
    )
    return f'<div class="chips">{chips}</div>' if chips else ""


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

    sections: list[str] = []
    if r.summary:
        sections.append(
            "<section>"
            + _h2("简介", "ABOUT")
            + f'<p class="summary" contenteditable="true">{bold_numbers(r.summary)}</p>'
            + "</section>"
        )

    works_html = _works_html(r)
    if works_html:
        sections.append("<section>" + _h2("精选作品", "SELECTED WORKS") + works_html + "</section>")

    # 顶层 projects（含 work[].projects 合并结果）作为独立项目经历板块；
    # 已被作品卡展示的 projects 数据在上面消费，此处仍输出避免信息丢失
    projects_html = _projects_html(r)
    if projects_html:
        sections.append("<section>" + _h2("项目经历", "PROJECTS") + projects_html + "</section>")

    if r.experiences:
        items = []
        for e in r.experiences:
            meta = " · ".join(str(x) for x in (e.title, e.dept) if x)
            items.append(
                '<div class="item">'
                '<div class="item-hd">'
                f'<span class="org" contenteditable="true">{_esc(e.company)}</span>'
                f'<span class="meta" contenteditable="true">{_esc(meta)}</span>'
                f'<span class="date" contenteditable="true">{_esc(e.period)}</span>'
                "</div>"
                + exp_content_html(e)
                + "</div>"
            )
        sections.append("<section>" + _h2("工作经历", "EXPERIENCE") + "".join(items) + "</section>")

    chips_html = _chips_html(r)
    if chips_html:
        sections.append("<section>" + _h2("能力与方法", "CAPABILITIES") + chips_html + "</section>")

    if r.education:
        items = []
        for e in r.education:
            detail = " · ".join(
                str(x) for x in (e.degree, e.gpa and f"GPA {e.gpa}", e.description) if x
            )
            items.append(
                '<div class="item">'
                '<div class="item-hd">'
                f'<span class="org" contenteditable="true">{_esc(e.school)}</span>'
                f'<span class="meta" contenteditable="true">{_esc(e.degree)}</span>'
                f'<span class="date" contenteditable="true">{_esc(e.period)}</span>'
                "</div>"
                + (f'<ul><li>{bold_numbers(detail)}</li></ul>' if detail else "")
                + "</div>"
            )
        sections.append("<section>" + _h2("教育背景", "EDUCATION") + "".join(items) + "</section>")

    if r.honors:
        lis = "".join(f"<li>{bold_numbers(x)}</li>" for x in r.honors)
        sections.append("<section>" + _h2("荣誉", "HONORS") + f"<ul>{lis}</ul></section>")

    foot = page_foot(
        f"{r.name} · {r.title}" if r.title else r.name,
        r.contact.email or r.contact.phone,
    )
    body = "<main>" + "".join(sections) + foot + "</main>"
    return f'<div class="page">{header}{body}</div>'
