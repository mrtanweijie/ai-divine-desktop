"""模板 15 · BOSS 直聘风（自旧 boss_zhipin 主题迁入）— 单栏流式、ATS 友好。"""

from __future__ import annotations

from .helpers import _esc, bold_resume_line

id = "boss_zhipin"

CSS = """@page {
  size: A4;
  margin: 1.8cm 1.8cm 1.6cm 1.8cm;
}

:root {
  --ink: #1f2329;
  --muted: #6b7280;
  --line: #e3e6eb;
  --brand: #1a3d6e;
}

* { box-sizing: border-box; }

body {
  font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", Arial, sans-serif;
  font-size: 10pt;
  line-height: 1.5;
  color: var(--ink);
  margin: 0;
}

.resume-header {
  text-align: left;
  margin-bottom: 6pt;
}

.resume-header h1 {
  font-size: 21pt;
  font-weight: 700;
  margin: 0 0 2pt 0;
  color: var(--ink);
  letter-spacing: 0.5pt;
}

.resume-header .intent {
  font-size: 10.5pt;
  color: var(--brand);
  font-weight: 600;
  margin-bottom: 3pt;
}

.resume-header .contact {
  font-size: 8.5pt;
  color: var(--muted);
}

.resume-header .contact span {
  margin-right: 10pt;
}

.section {
  margin-top: 10pt;
  page-break-inside: auto;
}

.section-title {
  font-size: 11pt;
  font-weight: 700;
  color: var(--brand);
  border-bottom: 0.75pt solid var(--line);
  padding-bottom: 2pt;
  margin-bottom: 5pt;
  break-after: avoid;
}

.summary {
  font-size: 9.5pt;
  color: #333;
  margin: 0 0 2pt 0;
}

.entry {
  margin-bottom: 7pt;
  page-break-inside: avoid;
}

.entry-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.entry-head .org {
  font-size: 10pt;
  font-weight: 700;
}

.entry-head .org .role {
  font-weight: 600;
  color: #333;
}

.entry-head .period {
  font-size: 8.5pt;
  color: var(--muted);
  white-space: nowrap;
}

.entry .desc {
  font-size: 9pt;
  color: #444;
  margin: 1pt 0 2pt 0;
}

.entry ul {
  margin: 2pt 0 0 0;
  padding-left: 12pt;
}

.entry li {
  font-size: 9pt;
  margin: 1.5pt 0;
  line-height: 1.45;
}

.entry li::marker {
  color: var(--brand);
}

.skills-line {
  font-size: 9.5pt;
  color: #333;
}

.skills-line b {
  color: var(--brand);
  font-weight: 600;
}

/* "分类|内容" 技能行：逐行「分类：内容」，替代原来的整段文字墙 */
.skill-row {
  font-size: 9.5pt;
  color: #333;
  line-height: 1.6;
  margin-bottom: 2.5pt;
}

.skill-row b {
  color: var(--brand);
  font-weight: 600;
}

.edu .school {
  font-weight: 700;
  font-size: 10pt;
}

.edu .meta {
  font-size: 8.5pt;
  color: var(--muted);
}
"""

PRINT_SINGLE = ""


def render(r) -> str:
    c = r.contact
    contact_parts = []
    if c.phone:
        contact_parts.append(f"<span>{_esc(c.phone)}</span>")
    if c.email:
        contact_parts.append(f"<span>{_esc(c.email)}</span>")
    if c.location or c.city or c.address:
        location = c.location or c.city or c.address
        contact_parts.append(f"<span>{_esc(location)}</span>")
    if c.website:
        contact_parts.append(f"<span>{_esc(c.website)}</span>")
    if c.github:
        contact_parts.append(f"<span>{_esc(c.github)}</span>")
    contact_html = "\n".join(contact_parts)

    summary_html = ""
    if r.summary:
        summary_html = f"""
        <div class="section">
          <div class="section-title">个人总结</div>
          <p class="summary">{bold_resume_line(r.summary)}</p>
        </div>"""

    exp_html = ""
    if r.experiences:
        entries = []
        for item in r.experiences:
            highlights = "".join(
                f"<li>{bold_resume_line(highlight)}</li>"
                for highlight in item.highlights
            )
            role_html = (
                f' <span class="role">· {_esc(item.title)}</span>'
                if item.title
                else ""
            )
            entries.append(
                f"""
        <div class="entry">
          <div class="entry-head">
            <div class="org">{_esc(item.company)}{role_html}</div>
            <div class="period">{_esc(item.period)}</div>
          </div>
          {f'<div class="desc">{bold_resume_line(item.description)}</div>' if item.description else ''}
          {f'<ul>{highlights}</ul>' if highlights else ''}
        </div>"""
            )
        exp_html = (
            '<div class="section">'
            '<div class="section-title">工作经历</div>'
            + "".join(entries)
            + "</div>"
        )

    project_html = ""
    if r.projects:
        entries = []
        for item in r.projects:
            highlights = "".join(
                f"<li>{bold_resume_line(highlight)}</li>"
                for highlight in item.highlights
            )
            entries.append(
                f"""
        <div class="entry">
          <div class="entry-head">
            <div class="org">{_esc(item.name)}</div>
          </div>
          {f'<div class="desc">{bold_resume_line(item.description)}</div>' if item.description else ''}
          {f'<ul>{highlights}</ul>' if highlights else ''}
        </div>"""
            )
        project_html = (
            '<div class="section">'
            '<div class="section-title">项目经历</div>'
            + "".join(entries)
            + "</div>"
        )

    education_html = ""
    if r.education:
        entries = []
        for item in r.education:
            role_html = (
                f' <span class="role">· {_esc(item.degree)}</span>'
                if item.degree
                else ""
            )
            entries.append(
                f"""
        <div class="entry edu">
          <div class="entry-head">
            <div class="org">{_esc(item.school)}{role_html}</div>
            <div class="period">{_esc(item.period)}</div>
          </div>
          {f'<div class="desc">{bold_resume_line(item.description)}</div>' if item.description else ''}
        </div>"""
            )
        education_html = (
            '<div class="section">'
            '<div class="section-title">教育背景</div>'
            + "".join(entries)
            + "</div>"
        )

    # 专业技能："分类|内容" 拆为逐行「分类：内容」；散技能顿号连接，不做任意加粗
    from .helpers import skill_pairs_and_plain

    pairs, plain = skill_pairs_and_plain(r)
    skills_html = ""
    if pairs or plain:
        rows = [
            f'<div class="skill-row"><b>{_esc(label)}</b>：{bold_resume_line(body)}</div>'
            for label, body in pairs
        ]
        if plain:
            rows.append(
                f'<div class="skill-row"><b>技能</b>：{_esc("、".join(plain))}</div>'
            )
        skills_html = (
            '<div class="section">'
            '<div class="section-title">专业技能</div>'
            + "".join(rows)
            + "</div>"
        )

    return f"""
    <div class="resume-header">
      <h1>{_esc(r.name)}</h1>
      {f'<div class="intent">{_esc(r.title)}</div>' if r.title else ''}
      {f'<div class="contact">{contact_html}</div>' if contact_html else ''}
    </div>
    {summary_html}
    {exp_html}
    {project_html}
    {education_html}
    {skills_html}
    """
