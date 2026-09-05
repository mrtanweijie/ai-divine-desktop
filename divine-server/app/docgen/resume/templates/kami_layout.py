"""Kami 内容向版式（原 renderers/kami.py 迁入，暖色/纯白共用同一 HTML）。"""

from __future__ import annotations

from .helpers import (
    _esc,
    _format_resume_line,
    _highlight_numbers,
    _split_value_unit,
)


def kami_resume_html(resume) -> str:
    """Kami 视觉 + 内容向简历版式：专业技能 / 工作经历 / 教育背景 / 个人亮点。"""
    c = resume.contact
    role_parts = []
    if resume.title:
        role_parts.append(f'<span class="role">{_esc(resume.title)}</span>')
    website = c.website or c.github or c.linkedin
    if website:
        role_parts.append(_esc(website))
    role_line = (
        '<span class="sep">·</span>'.join(role_parts) + "<br>"
        if role_parts
        else ""
    )

    info_parts = []
    if c.phone:
        info_parts.append(_esc(c.phone))
    if c.email:
        info_parts.append(_esc(c.email))
    if c.location or c.city or c.address:
        location = c.location or c.city or c.address
        info_parts.append(f'<span class="loc">{_esc(location)}</span>')
    info_line = '<span class="sep">·</span>'.join(info_parts)
    status_html = (
        f'<span class="sep">·</span><span class="status">{_esc(c.status)}</span>'
        if c.status
        else ""
    )
    contact_line = info_line + status_html
    contact_html = (
        f'<div class="contact">{role_line}{contact_line}</div>'
        if role_line or contact_line
        else ""
    )

    header_html = f"""
    <div class="header">
      <div>
        <div class="name serif">{_esc(resume.name)}</div>
      </div>
      {contact_html}
    </div>"""

    metrics_html = ""
    if resume.metrics:
        cards = []
        for metric in resume.metrics[:4]:
            value, unit = _split_value_unit(metric.value)
            cards.append(
                f"""
        <div class="metric">
          <span class="metric-value serif">{_esc(value)}<span class="unit">{_esc(unit)}</span></span>
          <span class="metric-label">{_esc(metric.label)}</span>
        </div>"""
            )
        metrics_html = f'<div class="metrics">{"".join(cards)}</div>'

    timeline_html = ""
    if resume.timeline:
        steps = []
        for step in resume.timeline[:3]:
            steps.append(
                f"""
        <div class="tl-step">
          <div class="tl-top">
            <div class="tl-year serif">{_esc(step.period)}</div>
            <div class="tl-head">{_esc(step.head)}</div>
          </div>
          <div class="tl-body">{_esc(step.body)}</div>
        </div>"""
            )
        timeline_html = f'<div class="timeline">{"".join(steps)}</div>'

    jobs_html = ""
    if resume.experiences:
        for item in resume.experiences:
            dept_html = (
                f'<span class="dept"> · {_esc(item.dept)}</span>'
                if item.dept
                else ""
            )
            position_html = (
                f'<span class="position"> · {_esc(item.title)}</span>'
                if item.title
                else ""
            )
            desc_html = (
                f'<div class="job-desc">{_esc(item.description)}</div>'
                if item.description
                else ""
            )
            body_html = ""
            if item.projects:
                for project in item.projects:
                    if not isinstance(project, dict):
                        continue
                    name = project.get("name") or ""
                    points = project.get("points") or project.get("highlights") or []
                    bullet_html = "".join(
                        f"<li>{_format_resume_line(point)}</li>"
                        for point in points
                    )
                    summary = project.get("summary") or project.get("desc") or ""
                    summary_html = (
                        f'<span class="project-summary">：{_esc(summary)}</span>'
                        if summary
                        else ""
                    )
                    body_html += (
                        f'<div class="project-name">{_esc(name)}{summary_html}</div>'
                        f"<ul>{bullet_html}</ul>"
                    )
            elif item.highlights:
                bullet_html = "".join(
                    f"<li>{_format_resume_line(highlight)}</li>"
                    for highlight in item.highlights
                )
                body_html = f"<ul>{bullet_html}</ul>"
            jobs_html += f"""
    <div class="job">
      <div class="job-header">
        <div class="company">{_esc(item.company)}{dept_html}{position_html}</div>
        <div class="period">{_esc(item.period)}</div>
      </div>
      {desc_html}
      {body_html}
    </div>"""
    elif resume.projects:
        for project in resume.projects:
            actions = project.actions or project.highlights
            impact = project.impact or (project.highlights[-1] if project.highlights else "")
            role_row = project.description or project.role
            chip = project.role if project.role and len(project.role) <= 24 else ""
            if not chip and project.kind:
                chip = project.kind
            kind_html = (
                f'<span class="proj-kind">· {_esc(project.kind)}</span>'
                if project.kind
                else ""
            )
            chip_html = (
                f'<span class="proj-role">{_esc(chip)}</span>'
                if chip
                else ""
            )
            rows = ""
            if role_row:
                rows += (
                    '<div class="proj-row">'
                    '<div class="proj-label">角色</div>'
                    f'<div class="proj-text">{_esc(role_row)}</div>'
                    "</div>"
                )
            if actions:
                actions_text = "；".join(_esc(action) for action in actions)
                rows += (
                    '<div class="proj-row">'
                    '<div class="proj-label">动作</div>'
                    f'<div class="proj-text">{actions_text}</div>'
                    "</div>"
                )
            if impact:
                rows += (
                    '<div class="proj-row">'
                    '<div class="proj-label">结果</div>'
                    f'<div class="proj-text">{_highlight_numbers(impact)}</div>'
                    "</div>"
                )
            jobs_html += f"""
    <div class="project">
      <div class="proj-head">
        <span class="proj-name serif">{_esc(project.name)}</span>{kind_html}{chip_html}
      </div>
      <div class="proj-lines">{rows}</div>
    </div>"""

    exp_sub = ""
    if resume.timeline:
        first = resume.timeline[0]
        last = resume.timeline[-1]
        exp_sub = (
            f'<span class="sub">{_esc(first.period)} - {_esc(last.period)}'
            f" · {_esc(last.head)}</span>"
        )
    experience_html = ""
    if resume.timeline or resume.experiences or resume.projects:
        experience_html = f"""
    <section>
      <div class="section-title">工作经历{exp_sub}</div>
      {timeline_html}
      {jobs_html}
    </section>"""

    skills = resume.core_skills or [skill.name for skill in resume.skills]
    skills_html = ""
    if skills:
        rows = []
        for index, skill in enumerate(skills, 1):
            if "：" in skill:
                label, body = skill.split("：", 1)
            elif "|" in skill:
                label, body = skill.split("|", 1)
            else:
                label, body = f"能力 {index:02d}", skill
            rows.append(
                f"""
      <div class="skill-row">
        <div class="skill-label">{_esc(label)}</div>
        <div class="skill-body">{_highlight_numbers(body)}</div>
      </div>"""
            )
        skills_html = (
            '<div class="section-title">专业技能</div>'
            + "".join(rows)
        )

    education_html = ""
    if resume.education:
        rows = []
        for item in resume.education:
            major = f" · {_esc(item.degree)}" if item.degree else ""
            desc_html = (
                f'<div class="edu-desc">{_esc(item.description)}</div>'
                if item.description
                else ""
            )
            rows.append(
                f"""
      <div class="edu-row">
        <span class="school">{_esc(item.school)}</span>
        <span class="major">{major}</span>
        <span class="date">{_esc(item.period)}</span>
      </div>
      {desc_html}"""
            )
        education_html = (
            '<div class="section-title">教育背景</div>'
            + "".join(rows)
        )

    highlights_html = ""
    if resume.highlights:
        items = "".join(
            f"<li>{_format_resume_line(highlight)}</li>"
            for highlight in resume.highlights
        )
        highlights_html = f"""
      <div class="section-title">个人亮点</div>
      <ul class="highlight-list">{items}</ul>"""

    public_html = ""
    if resume.public_work:
        items = []
        for item in resume.public_work:
            parts = item.split("|")
            name = parts[0].strip()
            desc = parts[1].strip() if len(parts) > 1 else ""
            items.append(
                f"""
      <div class="os-item">
        <span class="os-name serif">{_esc(name)}</span>
        <span class="os-desc">{_esc(desc)}</span>
      </div>"""
            )
        public_html = (
            '<div class="section-title">开源与对外产出</div>'
            + "".join(items)
        )

    section_map = {
        "skills": skills_html,
        "highlights": highlights_html,
        "experience": experience_html,
        "public_work": public_html,
        "education": education_html,
    }
    default_order = [
        "skills",
        "highlights",
        "experience",
        "public_work",
        "education",
    ]
    order = [key for key in resume.sections if key in section_map] or list(default_order)
    for key in default_order:
        if key not in order and section_map[key]:
            order.append(key)
    body_html = "".join(section_map[key] for key in order if section_map[key])
    return f"{header_html}\n{metrics_html}\n{body_html}"
