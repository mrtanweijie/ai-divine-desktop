"""模板 14 · 极简黑白留白版（自旧 minimal 主题迁入）— 大量留白 + 细线分隔。"""

from __future__ import annotations

from .helpers import _esc, bold_resume_line

id = "minimal"

CSS = """:root{
  --sans:"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans SC","Inter","Helvetica Neue",Arial,sans-serif;
  --ink:#1a1a1a; --mute:#777;
}
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: var(--sans);
  font-size: 9.5pt;
  line-height: 1.7;
  color: #1a1a1a;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}

@page {
  size: A4;
  margin: 0;
}

/* ===== Header ===== */
.header {
  padding: 36pt 34pt 20pt 34pt;
  border-bottom: 0.5pt solid #1a1a1a;
}

.header .name {
  font-size: 26pt;
  font-weight: 700;
  color: #000;
  letter-spacing: -0.01em;
  line-height: 1.2;
  margin-bottom: 6pt;
}

.header .contact-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16pt;
  font-size: 8.8pt;
  color: #444;
}

.header .contact-row span {
  display: flex;
  align-items: center;
  gap: 3pt;
}

/* ===== Body ===== */
.body {
  padding: 22pt 34pt 28pt 34pt;
}

/* ===== Section ===== */
.section {
  margin-bottom: 18pt;
  page-break-inside: auto;
}

.section h2 {
  font-size: 10pt;
  font-weight: 700;
  color: #000;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  margin-bottom: 10pt;
  padding-bottom: 4pt;
  border-bottom: 0.5pt solid #1a1a1a;
  break-after: avoid;
}

/* ===== 经历 ===== */
.exp-item {
  margin-bottom: 14pt;
  page-break-inside: avoid;
}

.exp-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 3pt;
}

.exp-position {
  font-size: 10pt;
  font-weight: 600;
  color: #000;
}

.exp-company {
  font-size: 9.5pt;
  color: #333;
  font-weight: 400;
}

.exp-period {
  font-size: 8.5pt;
  color: #777;
  white-space: nowrap;
}

.exp-body {
  font-size: 9pt;
  color: #2a2a2a;
  line-height: 1.65;
}

.exp-body ul {
  padding-left: 1.2em;
  margin: 3pt 0;
}

.exp-body li {
  margin: 2.5pt 0;
}

/* ===== 技能（极简文字列表） ===== */
.skills-list {
  columns: 2;
  column-gap: 20pt;
  font-size: 9pt;
  color: #2a2a2a;
}

.skills-list ul {
  padding-left: 1em;
  list-style: none;
}

.skills-list li {
  margin: 3pt 0;
  position: relative;
  padding-left: 8pt;
}

.skills-list li::before {
  content: "—";
  position: absolute;
  left: -4pt;
  color: #999;
}

.skills-list li b {
  color: #000;
  font-weight: 600;
}

/* ===== 教育 ===== */
.edu-item {
  margin-bottom: 10pt;
  page-break-inside: avoid;
}

.edu-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.edu-degree {
  font-size: 10pt;
  font-weight: 600;
  color: #000;
}

.edu-school {
  font-size: 9.5pt;
  color: #333;
}

/* ===== 摘要 ===== */
.summary {
  font-size: 9.5pt;
  color: #1a1a1a;
  line-height: 1.8;
  margin-bottom: 4pt;
}

/* ===== 项目 ===== */
.project-item {
  margin-bottom: 12pt;
  page-break-inside: avoid;
}

.project-name {
  font-size: 10pt;
  font-weight: 600;
  color: #000;
  margin-bottom: 2pt;
}

.project-desc {
  font-size: 9pt;
  color: #2a2a2a;
  line-height: 1.6;
}

.project-highlights {
  margin-top: 3pt;
}

.project-highlights ul {
  margin: 0;
  padding-left: 1.2em;
}

.project-highlights li {
  margin: 1pt 0;
  font-size: 8.5pt;
  color: #444;
}
"""

PRINT_SINGLE = ""


def render(r) -> str:
    c = r.contact

    contact_parts = []
    if c.email:
        contact_parts.append(f'<span>✉ {_esc(c.email)}</span>')
    if c.phone:
        contact_parts.append(f'<span>☎ {_esc(c.phone)}</span>')
    if c.location or c.city or c.address:
        location = c.location or c.city or c.address
        contact_parts.append(f'<span>⌂ {_esc(location)}</span>')
    if c.wechat:
        contact_parts.append(f'<span>◈ {_esc(c.wechat)}</span>')
    if c.github:
        contact_parts.append(f'<span>⎇ {_esc(c.github)}</span>')
    contact_html = "\n".join(contact_parts)

    # 技能：双栏文字列表；"分类|内容" 拆为「分类：内容」条目
    from .helpers import skill_pairs_and_plain

    pairs, plain = skill_pairs_and_plain(r)
    items = [f"<b>{_esc(label)}</b>：{bold_resume_line(body)}" for label, body in pairs]
    items.extend(_esc(s) for s in plain)
    skills_html = ""
    if items:
        half = (len(items) + 1) // 2
        left, right = items[:half], items[half:]
        skills_html = (
            '<div class="skills-list"><ul>'
            + "".join(f"<li>{s}</li>" for s in left)
            + "</ul><ul>"
            + "".join(f"<li>{s}</li>" for s in right)
            + "</ul></div>"
        )

    # 经历
    exp_html = ""
    for e in r.experiences:
        highlights = "".join(f"<li>{bold_resume_line(h)}</li>" for h in e.highlights)
        desc = bold_resume_line(e.description).replace("\n", "<br>") if e.description else ""
        exp_html += f"""
        <div class="exp-item">
          <div class="exp-row">
            <div><span class="exp-position">{_esc(e.title)}</span> · <span class="exp-company">{_esc(e.company)}</span></div>
            <span class="exp-period">{_esc(e.period)}</span>
          </div>
          <div class="exp-body">{desc}{f'<ul>{highlights}</ul>' if highlights else ''}</div>
        </div>"""

    # 项目
    proj_html = ""
    for p in r.projects:
        highlights = "".join(f"<li>{bold_resume_line(h)}</li>" for h in p.highlights)
        proj_html += f"""
        <div class="project-item">
          <div class="project-name">{_esc(p.name)}{f' · {_esc(p.role)}' if p.role else ''}</div>
          <div class="project-desc">{bold_resume_line(p.description)}</div>
          {f'<div class="project-highlights"><ul>{highlights}</ul></div>' if highlights else ''}
        </div>"""

    # 教育
    edu_html = ""
    for e in r.education:
        edu_html += f"""
        <div class="edu-item">
          <div class="edu-row">
            <span class="edu-degree">{_esc(e.degree)}</span>
            <span class="exp-period">{_esc(e.period)}</span>
          </div>
          <div class="edu-school">{_esc(e.school)}</div>
          {f'<div class="exp-body" style="font-size:8.5pt;color:#555;margin-top:2pt;">{bold_resume_line(e.description)}</div>' if e.description else ''}
        </div>"""

    summary_html = f'<div class="summary">{bold_resume_line(r.summary)}</div>' if r.summary else ""

    return f"""
    <div class="header">
      <div class="name">{_esc(r.name)}</div>
      <div class="contact-row">{contact_html}</div>
    </div>
    <div class="body">
      {('<div class="section">' + summary_html + '</div>') if summary_html else ''}
      {('<div class="section"><h2>Experience</h2>' + exp_html + '</div>') if exp_html else ''}
      {('<div class="section"><h2>Projects</h2>' + proj_html + '</div>') if proj_html else ''}
      {('<div class="section"><h2>Skills</h2>' + skills_html + '</div>') if skills_html else ''}
      {('<div class="section"><h2>Education</h2>' + edu_html + '</div>') if edu_html else ''}
    </div>
    """
