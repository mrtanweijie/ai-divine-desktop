"""
简历渲染引擎
- 支持多套主题：professional / creative / minimal / boss_zhipin / finance / linkedin
- 输入：ResumeData（dataclass）或 JSON dict
- 输出：PDF 文件路径
"""

import json
import os
from dataclasses import dataclass, field, asdict, fields
from typing import Optional
from pathlib import Path

try:
    from .theme_manager import get_theme_manager
except ImportError:
    from theme_manager import get_theme_manager


# ============================================================
# 数据模型
# ============================================================

@dataclass
class Contact:
    """联系方式"""
    email: str = ""
    phone: str = ""
    location: str = ""
    city: str = ""
    address: str = ""
    wechat: str = ""
    website: str = ""
    github: str = ""
    linkedin: str = ""


@dataclass
class Experience:
    """工作经历"""
    title: str = ""
    company: str = ""
    period: str = ""        # 如 "2022.03 - 至今"
    description: str = ""   # 支持多行，用 \n 分隔
    highlights: list[str] = field(default_factory=list)  # bullet points


@dataclass
class Education:
    """教育经历"""
    school: str = ""
    degree: str = ""       # 如 "硕士 · 计算机科学"
    period: str = ""
    description: str = ""  # 可选：GPA、荣誉等


@dataclass
class Project:
    """项目经历"""
    name: str = ""
    description: str = ""
    highlights: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    link: str = ""


@dataclass
class Skill:
    """技能（带熟练度，0-100）"""
    name: str = ""
    level: int = 80  # 百分比


@dataclass
class ResumeData:
    """完整简历数据"""
    name: str = ""
    title: str = ""           # 如 "高级产品经理"
    summary: str = ""         # 自我介绍/摘要
    contact: Contact = field(default_factory=Contact)
    experiences: list[Experience] = field(default_factory=list)
    education: list[Education] = field(default_factory=list)
    projects: list[Project] = field(default_factory=list)
    skills: list[Skill] = field(default_factory=list)
    skill_groups: dict[str, list[str]] = field(default_factory=dict)  # 创意主题用：分组技能标签

    @classmethod
    def from_dict(cls, data: dict) -> "ResumeData":
        """从 dict 构造（方便 JSON 传入）"""
        data = json.loads(json.dumps(data))  # deep copy
        data = _normalize_resume_input(data)
        if "contact" in data and isinstance(data["contact"], dict):
            allowed = {f.name for f in fields(Contact)}
            data["contact"] = Contact(
                **{
                    key: value
                    for key, value in data["contact"].items()
                    if key in allowed
                }
            )
        for key in ["experiences", "education", "projects", "skills"]:
            if key in data and isinstance(data[key], list):
                cls_map = {
                    "experiences": Experience,
                    "education": Education,
                    "projects": Project,
                    "skills": Skill,
                }
                allowed = {f.name for f in fields(cls_map[key])}
                data[key] = [
                    cls_map[key](
                        **{
                            field_name: field_value
                            for field_name, field_value in item.items()
                            if field_name in allowed
                        }
                    )
                    for item in data[key]
                    if isinstance(item, dict)
                ]
        allowed = {f.name for f in fields(cls)}
        return cls(
            **{
                key: value
                for key, value in data.items()
                if key in allowed
            }
        )

    def to_dict(self) -> dict:
        return json.loads(json.dumps(asdict(self), ensure_ascii=False))


def _normalize_resume_input(data: dict) -> dict:
    """兼容 basics/experience/startDate/level 1-5 等常见简历 JSON 结构。"""
    normalized = dict(data)

    basics = normalized.get("basics")
    if isinstance(basics, dict):
        normalized.setdefault("name", basics.get("name") or "")
        normalized.setdefault("title", basics.get("title") or "")
        normalized.setdefault("summary", basics.get("summary") or "")
        contact = dict(normalized.get("contact") or {})
        for key in ("email", "phone", "location", "city", "website", "github", "linkedin"):
            if basics.get(key):
                contact.setdefault(key, basics.get(key))
        normalized["contact"] = contact

    if "experience" in normalized and not normalized.get("experiences"):
        experiences = []
        for item in normalized.get("experience") or []:
            if not isinstance(item, dict):
                continue
            experiences.append(
                {
                    "title": item.get("position") or item.get("title") or "",
                    "company": item.get("company") or "",
                    "period": _resume_period(
                        item.get("startDate"),
                        item.get("endDate"),
                    ),
                    "description": item.get("description") or "",
                    "highlights": item.get("highlights") or [],
                }
            )
        normalized["experiences"] = experiences

    education = []
    for item in normalized.get("education") or []:
        if not isinstance(item, dict):
            continue
        degree = item.get("degree") or ""
        major = item.get("major") or ""
        if major and major not in degree:
            degree = f"{degree} · {major}" if degree else major
        education.append(
            {
                "school": item.get("school") or "",
                "degree": degree,
                "period": item.get("period") or item.get("date") or "",
                "description": item.get("description") or item.get("details") or "",
            }
        )
    normalized["education"] = education

    raw_skill_groups = normalized.get("skill_groups") or {}
    if isinstance(raw_skill_groups, list):
        skill_groups: dict[str, list[str]] = {}
        for group in raw_skill_groups:
            if isinstance(group, dict):
                name = str(group.get("name") or "")
                skills = group.get("skills") or []
                if name and isinstance(skills, list):
                    skill_groups[name] = [str(skill) for skill in skills]
        normalized["skill_groups"] = skill_groups
    elif not isinstance(raw_skill_groups, dict):
        normalized["skill_groups"] = {}

    projects = []
    for item in normalized.get("projects") or []:
        if not isinstance(item, dict):
            continue
        role = item.get("role") or ""
        description = item.get("description") or ""
        if role and role not in description:
            description = f"{role} · {description}"
        highlights = item.get("highlights") or []
        projects.append(
            {
                "name": item.get("name") or "",
                "description": description,
                "highlights": highlights,
                "tags": item.get("tags") or [],
                "link": item.get("link") or "",
            }
        )
    normalized["projects"] = projects

    skills = []
    for item in normalized.get("skills") or []:
        if not isinstance(item, dict):
            continue
        level = item.get("level") or 0
        try:
            level = int(level)
        except (TypeError, ValueError):
            level = 0
        if 0 < level <= 5:
            level = level * 20
        skills.append(
            {
                "name": item.get("name") or "",
                "level": level,
            }
        )
    normalized["skills"] = skills

    return normalized


def _resume_period(start: str | None, end: str | None) -> str:
    if not start and not end:
        return ""
    if start and end:
        return f"{start} - {end}"
    return str(start or end or "")


# ============================================================
# HTML 模板生成
# ============================================================

def _esc(text: str) -> str:
    """HTML 转义"""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _render_professional(resume: ResumeData) -> str:
    """经典商务蓝 — 左深蓝侧边栏 + 右白主内容区"""
    c = resume.contact

    # 侧边栏：联系方式
    contact_html = ""
    if c.email: contact_html += f'<div class="contact-item"><span class="icon">✉</span>{_esc(c.email)}</div>\n'
    if c.phone: contact_html += f'<div class="contact-item"><span class="icon">☎</span>{_esc(c.phone)}</div>\n'
    if c.location or c.city or c.address:
        location = c.location or c.city or c.address
        contact_html += f'<div class="contact-item"><span class="icon">⌂</span>{_esc(location)}</div>\n'
    if c.wechat: contact_html += f'<div class="contact-item"><span class="icon">◈</span>{_esc(c.wechat)}</div>\n'
    if c.website: contact_html += f'<div class="contact-item"><span class="icon">⚐</span>{_esc(c.website)}</div>\n'
    if c.github: contact_html += f'<div class="contact-item"><span class="icon">⎇</span>{_esc(c.github)}</div>\n'
    if c.linkedin: contact_html += f'<div class="contact-item"><span class="icon">in</span>{_esc(c.linkedin)}</div>\n'

    # 侧边栏：技能条
    skills_html = ""
    for s in resume.skills:
        skills_html += f"""
        <div class="skill-item">
          <div class="skill-name"><span>{_esc(s.name)}</span><span>{s.level}%</span></div>
          <div class="skill-bar"><div class="fill" style="width:{s.level}%"></div></div>
        </div>"""

    # 侧边栏：技能分组（标签云）
    skill_groups_html = ""
    for group_name, skills in resume.skill_groups.items():
        tags = "".join(f'<span class="tag">{_esc(s)}</span>' for s in skills)
        skill_groups_html += f"""
        <div class="sidebar-section">
          <h3>{_esc(group_name)}</h3>
          <div style="display:flex;flex-wrap:wrap;gap:3pt;">{tags}</div>
        </div>"""

    # 右侧：摘要
    summary_html = ""
    if resume.summary:
        summary_html = f'<div class="main-section"><div class="summary">{_esc(resume.summary)}</div></div>'

    # 右侧：工作经历
    exp_html = ""
    for e in resume.experiences:
        highlights = "".join(f"<li>{_esc(h)}</li>" for h in e.highlights)
        desc = _esc(e.description).replace("\n", "<br>")
        exp_html += f"""
        <div class="experience-item">
          <div class="exp-header">
            <div><span class="exp-title">{_esc(e.title)}</span> · <span class="exp-company">{_esc(e.company)}</span></div>
            <span class="exp-period">{_esc(e.period)}</span>
          </div>
          <div class="exp-desc">{desc}{f'<ul>{highlights}</ul>' if highlights else ''}</div>
        </div>"""

    # 右侧：项目
    proj_html = ""
    for p in resume.projects:
        tags = "".join(f'<span class="tag">{_esc(t)}</span>' for t in p.tags)
        highlights = "".join(f"<li>{_esc(h)}</li>" for h in p.highlights)
        proj_html += f"""
        <div class="project-item">
          <div class="project-title">{_esc(p.name)}</div>
          <div class="project-desc">{_esc(p.description)}</div>
          {f'<div class="project-highlights"><ul>{highlights}</ul></div>' if highlights else ''}
          <div class="project-tags">{tags}</div>
        </div>"""

    # 右侧：教育
    edu_html = ""
    for e in resume.education:
        edu_html += f"""
        <div class="edu-item">
          <div class="edu-header">
            <span class="edu-degree">{_esc(e.degree)}</span>
            <span class="edu-period">{_esc(e.period)}</span>
          </div>
          <div class="edu-school">{_esc(e.school)}</div>
          {f'<div class="exp-desc" style="font-size:8.5pt;color:#64748b;margin-top:2pt;">{_esc(e.description)}</div>' if e.description else ''}
        </div>"""

    return f"""
    <div class="resume">
      <aside class="sidebar">
        <div class="name">{_esc(resume.name)}</div>
        <div class="title">{_esc(resume.title)}</div>

        <div class="sidebar-section">
          <h3>联系方式</h3>
          {contact_html}
        </div>

        <div class="sidebar-section">
          <h3>专业技能</h3>
          {skills_html}
        </div>

        {skill_groups_html}
      </aside>

      <main class="main">
        {summary_html}

        {('<div class="main-section"><h2>工作经历</h2>' + exp_html + '</div>') if exp_html else ''}
        {('<div class="main-section"><h2>项目经历</h2>' + proj_html + '</div>') if proj_html else ''}
        {('<div class="main-section"><h2>教育背景</h2>' + edu_html + '</div>') if edu_html else ''}
      </main>
    </div>
    """


def _render_creative(resume: ResumeData) -> str:
    """现代创意紫橙 — 顶部渐变 Header + 卡片式布局"""
    c = resume.contact

    contact_items = []
    if c.email: contact_items.append(f'<span>✉ {_esc(c.email)}</span>')
    if c.phone: contact_items.append(f'<span>☎ {_esc(c.phone)}</span>')
    if c.location or c.city or c.address:
        location = c.location or c.city or c.address
        contact_items.append(f'<span>⌂ {_esc(location)}</span>')
    if c.wechat: contact_items.append(f'<span>◈ {_esc(c.wechat)}</span>')
    if c.github: contact_items.append(f'<span>⎇ {_esc(c.github)}</span>')
    if c.linkedin: contact_items.append(f'<span>in {_esc(c.linkedin)}</span>')
    contact_html = "\n".join(contact_items)

    # 左栏：经历卡片
    exp_html = ""
    for e in resume.experiences:
        highlights = "".join(f"<li>{_esc(h)}</li>" for h in e.highlights)
        desc = _esc(e.description).replace("\n", "<br>")
        exp_html += f"""
        <div class="card">
          <div class="card-header">
            <span class="card-title">{_esc(e.title)}</span>
            <span class="card-period">{_esc(e.period)}</span>
          </div>
          <div class="card-subtitle">{_esc(e.company)}</div>
          <div class="card-body">{desc}{f'<ul>{highlights}</ul>' if highlights else ''}</div>
        </div>"""

    # 左栏：项目卡片
    proj_html = ""
    for p in resume.projects:
        highlights = "".join(f"<li>{_esc(h)}</li>" for h in p.highlights)
        proj_html += f"""
        <div class="project-card">
          <div class="name">{_esc(p.name)}</div>
          <div class="desc">{_esc(p.description)}</div>
          {f'<div class="project-highlights"><ul>{highlights}</ul></div>' if highlights else ''}
        </div>"""

    # 右栏：技能分组标签
    skills_html = ""
    if resume.skill_groups:
        for group_name, skills in resume.skill_groups.items():
            tags = "".join(f'<span class="skill-tag">{_esc(s)}</span>' for s in skills)
            skills_html += f"""
            <div class="skill-group">
              <h4>{_esc(group_name)}</h4>
              <div class="skill-tags">{tags}</div>
            </div>"""
    else:
        # 退化：用 skills 列表
        for s in resume.skills:
            skills_html += f"""
            <div class="skill-group">
              <h4>{_esc(s.name)}</h4>
              <div class="skill-tags"><span class="skill-tag">{s.level}%</span></div>
            </div>"""

    # 右栏：教育
    edu_html = ""
    for e in resume.education:
        edu_html += f"""
        <div class="edu-card">
          <div class="degree">{_esc(e.degree)}</div>
          <div class="school">{_esc(e.school)}</div>
          <div class="meta">{_esc(e.period)}{f' · {_esc(e.description)}' if e.description else ''}</div>
        </div>"""

    summary_html = f'<div class="summary">{_esc(resume.summary)}</div>' if resume.summary else ""

    return f"""
    <div class="header">
      <div class="name">{_esc(resume.name)}</div>
      <div class="subtitle">{_esc(resume.title)}</div>
      <div class="contact-row">{contact_html}</div>
    </div>
    <div class="body">
      {('<div class="section">' + summary_html + '</div>') if summary_html else ''}
      <div class="two-col">
        <div class="col-left">
          {('<div class="section"><h2>工作经历</h2>' + exp_html + '</div>') if exp_html else ''}
          {('<div class="section"><h2>项目</h2>' + proj_html + '</div>') if proj_html else ''}
        </div>
        <div class="col-right">
          {('<div class="section"><h2>技能</h2>' + skills_html + '</div>') if skills_html else ''}
          {('<div class="section"><h2>教育</h2>' + edu_html + '</div>') if edu_html else ''}
        </div>
      </div>
    </div>
    """


def _render_minimal(resume: ResumeData) -> str:
    """极简黑白 — 大量留白 + 细线分隔"""
    c = resume.contact

    contact_parts = []
    if c.email: contact_parts.append(f'<span>✉ {_esc(c.email)}</span>')
    if c.phone: contact_parts.append(f'<span>☎ {_esc(c.phone)}</span>')
    if c.location or c.city or c.address:
        location = c.location or c.city or c.address
        contact_parts.append(f'<span>⌂ {_esc(location)}</span>')
    if c.wechat: contact_parts.append(f'<span>◈ {_esc(c.wechat)}</span>')
    if c.github: contact_parts.append(f'<span>⎇ {_esc(c.github)}</span>')
    contact_html = "\n".join(contact_parts)

    # 技能：双栏文字列表
    skills_html = ""
    if resume.skill_groups:
        items = []
        for group_skills in resume.skill_groups.values():
            items.extend(group_skills)
        half = (len(items) + 1) // 2
        left = items[:half]
        right = items[half:]
        skills_html = '<div class="skills-list"><ul>' + "".join(f"<li>{_esc(s)}</li>" for s in left) + '</ul><ul>' + "".join(f"<li>{_esc(s)}</li>" for s in right) + '</ul></div>'
    elif resume.skills:
        half = (len(resume.skills) + 1) // 2
        left = resume.skills[:half]
        right = resume.skills[half:]
        skills_html = '<div class="skills-list"><ul>' + "".join(f"<li>{_esc(s.name)}</li>" for s in left) + '</ul><ul>' + "".join(f"<li>{_esc(s.name)}</li>" for s in right) + '</ul></div>'

    # 经历
    exp_html = ""
    for e in resume.experiences:
        highlights = "".join(f"<li>{_esc(h)}</li>" for h in e.highlights)
        desc = _esc(e.description).replace("\n", "<br>")
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
    for p in resume.projects:
        highlights = "".join(f"<li>{_esc(h)}</li>" for h in p.highlights)
        proj_html += f"""
        <div class="project-item">
          <div class="project-name">{_esc(p.name)}</div>
          <div class="project-desc">{_esc(p.description)}</div>
          {f'<div class="project-highlights"><ul>{highlights}</ul></div>' if highlights else ''}
        </div>"""

    # 教育
    edu_html = ""
    for e in resume.education:
        edu_html += f"""
        <div class="edu-item">
          <div class="edu-row">
            <span class="edu-degree">{_esc(e.degree)}</span>
            <span class="exp-period">{_esc(e.period)}</span>
          </div>
          <div class="edu-school">{_esc(e.school)}</div>
          {f'<div class="exp-body" style="font-size:8.5pt;color:#555;margin-top:2pt;">{_esc(e.description)}</div>' if e.description else ''}
        </div>"""

    summary_html = f'<div class="summary">{_esc(resume.summary)}</div>' if resume.summary else ""

    return f"""
    <div class="header">
      <div class="name">{_esc(resume.name)}</div>
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


def _render_boss_zhipin(resume: ResumeData) -> str:
    """BOSS 直聘风 — 单栏流式、ATS 友好、克制商务蓝"""
    c = resume.contact
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
    if resume.summary:
        summary_html = f"""
        <div class="section">
          <div class="section-title">个人总结</div>
          <p class="summary">{_esc(resume.summary)}</p>
        </div>"""

    exp_html = ""
    if resume.experiences:
        entries = []
        for item in resume.experiences:
            highlights = "".join(
                f"<li>{_esc(highlight)}</li>"
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
          {f'<div class="desc">{_esc(item.description)}</div>' if item.description else ''}
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
    if resume.projects:
        entries = []
        for item in resume.projects:
            highlights = "".join(
                f"<li>{_esc(highlight)}</li>"
                for highlight in item.highlights
            )
            entries.append(
                f"""
        <div class="entry">
          <div class="entry-head">
            <div class="org">{_esc(item.name)}</div>
          </div>
          {f'<div class="desc">{_esc(item.description)}</div>' if item.description else ''}
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
    if resume.education:
        entries = []
        for item in resume.education:
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
          {f'<div class="desc">{_esc(item.description)}</div>' if item.description else ''}
        </div>"""
            )
        education_html = (
            '<div class="section">'
            '<div class="section-title">教育背景</div>'
            + "".join(entries)
            + "</div>"
        )

    skills = []
    if resume.skill_groups:
        for group_skills in resume.skill_groups.values():
            skills.extend(group_skills)
    if not skills:
        skills = [skill.name for skill in resume.skills]
    skills_html = ""
    if skills:
        items = []
        for index, skill in enumerate(skills):
            if index < 3:
                items.append(f"<b>{_esc(skill)}</b>")
            else:
                items.append(_esc(skill))
        skills_html = (
            '<div class="section">'
            '<div class="section-title">专业技能</div>'
            f'<div class="skills-line">{"、".join(items)}</div>'
            "</div>"
        )

    return f"""
    <div class="resume-header">
      <h1>{_esc(resume.name)}</h1>
      {f'<div class="intent">{_esc(resume.title)}</div>' if resume.title else ''}
      {f'<div class="contact">{contact_html}</div>' if contact_html else ''}
    </div>
    {summary_html}
    {exp_html}
    {project_html}
    {education_html}
    {skills_html}
    """


def _compact_contact_items(resume: ResumeData) -> list[str]:
    """简历头部联系方式：电话 | 邮箱 | 网站，左对齐单行展示。"""
    c = resume.contact
    items = []
    if c.phone:
        items.append(f"<span>{_esc(c.phone)}</span>")
    if c.email:
        items.append(f"<span>{_esc(c.email)}</span>")
    website = c.website or c.github or c.linkedin
    if website:
        items.append(f"<span>{_esc(website)}</span>")
    return items


def _render_flat_resume(resume: ResumeData, *, style: str) -> str:
    """单栏克制排版，finance / linkedin 共用同一套 HTML 结构。"""
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

    top_html = ""
    bottom_html = ""
    if style == "linkedin":
        top_html = '<div class="topbar"></div>'
    elif style == "finance":
        bottom_html = '<div class="header-rule"></div>'

    summary_html = ""
    if resume.summary:
        summary_html = f"""
        <div class="section">
          <div class="section-title">个人总结</div>
          <p style="font-size:9pt;color:#333;">{_esc(resume.summary)}</p>
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
            highlights = "".join(
                f"<li>{_esc(highlight)}</li>"
                for highlight in item.highlights
            )
            entries.append(
                f"""
        <div class="entry">
          <div class="entry-head">
            <div class="left">{left_html}</div>
            {f'<div class="right">{_esc(item.period)}</div>' if item.period else ''}
          </div>
          {f'<div class="desc">{_esc(item.description)}</div>' if item.description else ''}
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
    if resume.projects:
        entries = []
        for item in resume.projects:
            highlights = "".join(
                f"<li>{_esc(highlight)}</li>"
                for highlight in item.highlights
            )
            entries.append(
                f"""
        <div class="entry">
          <div class="entry-head">
            <div class="left">{_esc(item.name)}</div>
          </div>
          {f'<div class="desc">{_esc(item.description)}</div>' if item.description else ''}
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
          {f'<div class="meta">{_esc(item.description)}</div>' if item.description else ''}
        </div>"""
            )
        education_html = (
            '<div class="section">'
            '<div class="section-title">教育背景</div>'
            + "".join(entries)
            + "</div>"
        )

    skills = []
    if resume.skill_groups:
        for group_skills in resume.skill_groups.values():
            skills.extend(group_skills)
    if not skills:
        skills = [skill.name for skill in resume.skills]

    skills_html = ""
    if skills:
        if style == "linkedin":
            tags = []
            for index, skill in enumerate(skills):
                cls = "tag strong" if index < 5 else "tag"
                tags.append(f'<span class="{cls}">{_esc(skill)}</span>')
            inner_html = "".join(tags)
        else:
            items = []
            for index, skill in enumerate(skills):
                if index < 3:
                    items.append(f"<b>{_esc(skill)}</b>")
                else:
                    items.append(_esc(skill))
            inner_html = " · ".join(items)
        skills_html = (
            '<div class="section">'
            '<div class="section-title">专业技能</div>'
            f'<div class="skills">{inner_html}</div>'
            "</div>"
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


def _render_finance(resume: ResumeData) -> str:
    return _render_flat_resume(resume, style="finance")


def _render_linkedin(resume: ResumeData) -> str:
    return _render_flat_resume(resume, style="linkedin")


# 主题 → 渲染函数映射
_RENDERERS = {
    "professional": _render_professional,
    "creative": _render_creative,
    "minimal": _render_minimal,
    "boss_zhipin": _render_boss_zhipin,
    "finance": _render_finance,
    "linkedin": _render_linkedin,
}


# ============================================================
# 主入口
# ============================================================

def render_resume(
    resume_data: ResumeData | dict,
    output_path: str,
    theme: str = "professional",
) -> str:
    """
    渲染简历 PDF

    Args:
        resume_data: ResumeData 对象或 dict
        output_path: 输出 PDF 路径
        theme: 主题名 (professional / creative / minimal / boss_zhipin / finance / linkedin)

    Returns:
        输出文件路径
    """
    if isinstance(resume_data, dict):
        resume_data = ResumeData.from_dict(resume_data)

    manager = get_theme_manager()
    css = manager.get_css(theme)

    if theme not in _RENDERERS:
        raise ValueError(f"不支持的主题: {theme}，可选: {list(_RENDERERS.keys())}")

    html_body = _RENDERERS[theme](resume_data)

    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <style>{css}</style>
</head>
<body>
{html_body}
</body>
</html>"""

    # 确保输出目录存在
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    from weasyprint import HTML
    HTML(string=full_html).write_pdf(output_path)
    return output_path


def render_resume_auto(
    resume_data: ResumeData | dict,
    output_path: str,
    theme: str = "professional",
) -> str:
    """自动选主题渲染（和上面一样，兼容接口统一）"""
    return render_resume(resume_data, output_path, theme)
