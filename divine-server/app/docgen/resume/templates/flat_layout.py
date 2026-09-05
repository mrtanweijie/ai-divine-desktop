"""单栏克制排版（原 finance / linkedin 共用布局，自旧 renderers 迁入）。"""

from __future__ import annotations

from .components import exp_content_html
from .helpers import _compact_contact_items, _esc, bold_resume_line


def flat_resume_html(resume, style: str) -> str:
    """style: finance / linkedin。"""
    is_linkedin = style == "linkedin"

    def section_title(zh: str, en: str) -> str:
        # linkedin 面向海外投递，板块标题用英文（CSS 已统一大写）
        return en if is_linkedin else zh

    contact_items = _compact_contact_items(resume)
    contact_html = ""
    for index, item in enumerate(contact_items):
        if index:
            contact_html += '<span class="sep">|</span>'
        contact_html += item

    header_html = f"""
    <div class="header">
      <h1>{_esc(resume.name)}</h1>
      {f'<div class="subtitle">{_esc(resume.title)}</div>' if resume.title else ''}
      {f'<div class="contact">{contact_html}</div>' if contact_html else ''}
    </div>"""

    top_html = '<div class="topbar"></div>' if is_linkedin else ""
    bottom_html = '<div class="header-rule"></div>' if style == "finance" else ""

    summary_html = ""
    if resume.summary:
        summary_html = f"""
        <div class="section">
          <div class="section-title">{section_title("个人总结", "Summary")}</div>
          <p style="font-size:9pt;color:#333;">{bold_resume_line(resume.summary)}</p>
        </div>"""

    exp_html = ""
    if resume.experiences:
        entries = []
        for item in resume.experiences:
            role_html = (
                f'<span class="role">{_esc(item.title)}</span>'
                if item.title
                else ""
            )
            left_html = (
                f'{_esc(item.company)}<span class="sep">|</span>{role_html}'
                if role_html
                else _esc(item.company)
            )
            entries.append(
                f"""
        <div class="entry">
          <div class="entry-head">
            <div class="left">{left_html}</div>
            {f'<div class="right">{_esc(item.period)}</div>' if item.period else ''}
          </div>
          {f'<div class="desc">{bold_resume_line(item.description)}</div>' if item.description else ''}
          {exp_content_html(item)}
        </div>"""
            )
        exp_html = (
            '<div class="section">'
            f'<div class="section-title">{section_title("工作经历", "Work Experience")}</div>'
            + "".join(entries)
            + "</div>"
        )

    project_html = ""
    if resume.projects:
        entries = []
        for item in resume.projects:
            highlights = "".join(
                f"<li>{bold_resume_line(highlight)}</li>"
                for highlight in item.highlights
            )
            role_html = (
                f'<span class="role">{_esc(item.role)}</span>'
                if item.role
                else ""
            )
            left_html = (
                f'{_esc(item.name)}<span class="sep">|</span>{role_html}'
                if role_html
                else _esc(item.name)
            )
            entries.append(
                f"""
        <div class="entry">
          <div class="entry-head">
            <div class="left">{left_html}</div>
          </div>
          {f'<div class="desc">{bold_resume_line(item.description)}</div>' if item.description else ''}
          {f'<ul>{highlights}</ul>' if highlights else ''}
        </div>"""
            )
        project_html = (
            '<div class="section">'
            f'<div class="section-title">{section_title("项目经历", "Projects")}</div>'
            + "".join(entries)
            + "</div>"
        )

    education_html = ""
    if resume.education:
        entries = []
        for item in resume.education:
            role_html = (
                f'<span class="role">{_esc(item.degree)}</span>'
                if item.degree
                else ""
            )
            left_html = (
                f'{_esc(item.school)}<span class="sep">|</span>{role_html}'
                if role_html
                else _esc(item.school)
            )
            entries.append(
                f"""
        <div class="entry edu">
          <div class="entry-head">
            <div class="left">{left_html}</div>
            {f'<div class="right">{_esc(item.period)}</div>' if item.period else ''}
          </div>
          {f'<div class="meta">{bold_resume_line(item.description)}</div>' if item.description else ''}
        </div>"""
            )
        education_html = (
            '<div class="section">'
            f'<div class="section-title">{section_title("教育背景", "Education")}</div>'
            + "".join(entries)
            + "</div>"
        )

    # 专业技能："分类|内容" 拆为逐行「分类：内容」；散技能 linkedin 用标签、其余顿点连接
    from .helpers import skill_pairs_and_plain

    pairs, plain = skill_pairs_and_plain(resume)
    skills_html = ""
    if pairs or plain:
        rows = [
            f'<div class="skill-row"><b>{_esc(label)}</b>：{bold_resume_line(body)}</div>'
            for label, body in pairs
        ]
        if plain:
            if is_linkedin:
                tags = [
                    f'<span class="{"tag strong" if index < 5 else "tag"}">{_esc(skill)}</span>'
                    for index, skill in enumerate(plain)
                ]
                rows.append(f'<div class="skills">{"".join(tags)}</div>')
            else:
                rows.append(f'<div class="skill-row">{_esc(" · ".join(plain))}</div>')
        skills_html = (
            '<div class="section">'
            f'<div class="section-title">{section_title("专业技能", "Skills")}</div>'
            + "".join(rows)
            + "</div>"
        )

    return f"""
    {top_html}
    {header_html}
    {bottom_html}
    {summary_html}
    {exp_html}
    {project_html}
    {education_html}
    {skills_html}
    """
