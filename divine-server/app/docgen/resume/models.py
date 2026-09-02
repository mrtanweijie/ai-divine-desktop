"""Resume data models and JSON normalization helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields


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
    status: str = ""

@dataclass
class Experience:
    """工作经历"""
    title: str = ""
    company: str = ""
    dept: str = ""
    period: str = ""        # 如 "2022.03 - 至今"
    description: str = ""   # 支持多行，用 \n 分隔
    highlights: list[str] = field(default_factory=list)  # bullet points
    projects: list[dict] = field(default_factory=list)

@dataclass
class Education:
    """教育经历"""
    school: str = ""
    degree: str = ""       # 如 "硕士 · 计算机科学"
    period: str = ""
    description: str = ""

@dataclass
class Project:
    """项目经历"""
    name: str = ""
    role: str = ""
    kind: str = ""
    description: str = ""
    highlights: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    impact: str = ""
    tags: list[str] = field(default_factory=list)
    link: str = ""

@dataclass
class Skill:
    """技能（带熟练度，0-100）"""
    name: str = ""
    level: int = 80

@dataclass
class ResumeData:
    """完整简历数据"""
    name: str = ""
    title: str = ""           # 如 "高级产品经理"
    target: str = ""          # 目标岗位，兼容 one-page 结构
    summary: str = ""         # 自我介绍/摘要
    contact: Contact = field(default_factory=Contact)
    experiences: list[Experience] = field(default_factory=list)
    education: list[Education] = field(default_factory=list)
    projects: list[Project] = field(default_factory=list)
    skills: list[Skill] = field(default_factory=list)
    skill_groups: dict[str, list[str]] = field(default_factory=dict)  # 创意主题用：分组技能标签
    core_skills: list[str] = field(default_factory=list)  # 一页简历结构：核心技能关键词
    metrics: list["Metric"] = field(default_factory=list)      # Kami：4 个数字卡片
    timeline: list["TimelineStep"] = field(default_factory=list)  # Kami：3 步演进
    public_work: list[str] = field(default_factory=list)       # Kami：开源/对外产出
    highlights: list[str] = field(default_factory=list)        # 个人亮点
    sections: list[str] = field(default_factory=list)          # 板块顺序，可选

    @classmethod
    def from_dict(cls, data: dict) -> "ResumeData":
        """从 dict 构造（方便 JSON 传入）"""
        data = json.loads(json.dumps(data))  # deep copy
        data = _normalize_resume_input(data)
        if isinstance(data.get("contact"), dict):
            allowed = {f.name for f in fields(Contact)}
            data["contact"] = Contact(
                **{
                    key: value
                    for key, value in data["contact"].items()
                    if key in allowed
                }
            )
        for key in ["experiences", "education", "projects", "skills", "metrics", "timeline"]:
            if key in data and isinstance(data[key], list):
                cls_map = {
                    "experiences": Experience,
                    "education": Education,
                    "projects": Project,
                    "skills": Skill,
                    "metrics": Metric,
                    "timeline": TimelineStep,
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
        if isinstance(data.get("public_work"), list):
            data["public_work"] = [str(item) for item in data["public_work"]]
        allowed = {f.name for f in fields(cls)}
        resume = cls(
            **{key: value for key, value in data.items() if key in allowed}
        )
        if not resume.title and resume.target:
            resume.title = resume.target
        if resume.core_skills and not resume.skills:
            resume.skills = [Skill(name=skill, level=80) for skill in resume.core_skills]
        return resume

    def to_dict(self) -> dict:
        return json.loads(json.dumps(asdict(self), ensure_ascii=False))

@dataclass
class Metric:
    """Kami 数字卡片"""
    value: str = ""
    label: str = ""

@dataclass
class TimelineStep:
    """Kami 演进时间线"""
    period: str = ""
    milestone: str = ""
    head: str = ""
    body: str = ""

def _resume_period(start: str | None, end: str | None) -> str:
    if not start and not end:
        return ""
    if start and end:
        return f"{start} - {end}"
    return str(start or end or "")

def _normalize_resume_input(data: dict) -> dict:
    """兼容 basics/experience/startDate/level 1-5 等常见简历 JSON 结构。"""
    normalized = dict(data)

    if isinstance(normalized.get("contact"), str):
        contact: dict[str, str] = {}
        for part in normalized["contact"].split("|"):
            part = part.strip()
            if not part:
                continue
            if "@" in part and not contact.get("email"):
                contact["email"] = part
            elif any(ch.isdigit() for ch in part) and not contact.get("phone"):
                contact["phone"] = part
            elif not contact.get("website"):
                contact["website"] = part
        normalized["contact"] = contact

    basics = normalized.get("basics")
    if isinstance(basics, dict):
        normalized.setdefault("name", basics.get("name") or "")
        normalized.setdefault("title", basics.get("title") or "")
        normalized.setdefault("target", basics.get("target") or "")
        normalized.setdefault("summary", basics.get("summary") or "")
        normalized.setdefault("highlights", basics.get("highlights") or [])
        contact = dict(normalized.get("contact") or {})
        for key in ("email", "phone", "location", "city", "website", "github", "linkedin", "status"):
            if basics.get(key):
                contact.setdefault(key, basics.get(key))
        normalized["contact"] = contact

    if "work" in normalized and not normalized.get("experiences"):
        work_items = []
        for item in normalized.get("work") or []:
            if not isinstance(item, dict):
                continue
            work_items.append(
                {
                    "title": item.get("position") or item.get("title") or "",
                    "company": item.get("company") or "",
                    "dept": item.get("dept") or item.get("department") or "",
                    "period": item.get("period")
                    or _resume_period(
                        item.get("startDate"),
                        item.get("endDate"),
                    ),
                    "description": item.get("description") or "",
                    "highlights": item.get("points") or item.get("highlights") or [],
                    "projects": item.get("projects") or item.get("project_groups") or [],
                }
            )
        normalized["experiences"] = work_items

    if "experience" in normalized and not normalized.get("experiences"):
        experiences = []
        for item in normalized.get("experience") or []:
            if not isinstance(item, dict):
                continue
            experiences.append(
                {
                    "title": item.get("position") or item.get("title") or "",
                    "company": item.get("company") or "",
                    "dept": item.get("dept") or item.get("department") or "",
                    "period": _resume_period(
                        item.get("startDate"),
                        item.get("endDate"),
                    ),
                    "description": item.get("description") or "",
                    "highlights": item.get("highlights") or item.get("points") or [],
                    "projects": item.get("projects") or item.get("project_groups") or [],
                }
            )
        normalized["experiences"] = experiences

    raw_core_skills = normalized.get("core_skills")
    if isinstance(raw_core_skills, str):
        raw_core_skills = [
            part.strip()
            for part in raw_core_skills.replace("，", ",").split(",")
            if part.strip()
        ]
    if isinstance(raw_core_skills, list):
        normalized["core_skills"] = [str(skill) for skill in raw_core_skills]
    elif not isinstance(raw_core_skills, list):
        normalized["core_skills"] = []

    metrics = []
    for item in normalized.get("metrics") or []:
        if isinstance(item, dict):
            metrics.append(
                {
                    "value": item.get("value") or "",
                    "label": item.get("label") or "",
                }
            )
        elif isinstance(item, str) and "|" in item:
            value, label = item.split("|", 1)
            metrics.append({"value": value.strip(), "label": label.strip()})
    normalized["metrics"] = metrics

    timeline = []
    for item in normalized.get("timeline") or []:
        if not isinstance(item, dict):
            continue
        period = item.get("period") or item.get("year") or ""
        head = item.get("head") or item.get("milestone") or ""
        body = item.get("body") or ""
        timeline.append(
            {
                "period": period,
                "milestone": head,
                "head": head,
                "body": body,
            }
        )
    normalized["timeline"] = timeline

    public_work = normalized.get("public_work") or []
    if isinstance(public_work, str):
        public_work = [public_work]
    normalized["public_work"] = [str(item) for item in public_work]

    sections = normalized.get("sections") or []
    if isinstance(sections, str):
        sections = [sections]
    normalized["sections"] = [str(section).strip() for section in sections if str(section).strip()]

    highlights = normalized.get("highlights") or []
    if isinstance(highlights, str):
        highlights = [highlights]
    normalized["highlights"] = [str(item) for item in highlights]

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
        description = item.get("context") or item.get("description") or ""
        actions = item.get("actions") or item.get("points") or []
        impact = item.get("impact") or ""
        highlights = (
            item.get("points")
            or item.get("highlights")
            or actions
            or ([impact] if impact else [])
        )
        projects.append(
            {
                "name": item.get("name") or "",
                "role": role,
                "kind": item.get("kind") or item.get("type") or "",
                "description": description,
                "highlights": highlights,
                "actions": actions,
                "impact": impact,
                "tags": item.get("tags") or [],
                "link": item.get("link") or "",
            }
        )
    normalized["projects"] = projects

    skills = []
    for item in normalized.get("skills") or []:
        if isinstance(item, str):
            skills.append({"name": item, "level": 80})
            continue
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
    if not skills and normalized.get("core_skills"):
        skills = [
            {"name": skill, "level": 80}
            for skill in normalized["core_skills"]
        ]
    normalized["skills"] = skills

    if normalized.get("target") and not normalized.get("title"):
        normalized["title"] = normalized["target"]

    return normalized
