"""Resume data models and JSON normalization helpers."""

from __future__ import annotations

import json
import re
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
    scale: str = ""         # 公司/团队规模标注（高管模板），如 "年营收 86 亿元 · 员工 3,400 人"
    en_company: str = ""    # 国际通用版：英文公司名
    en_title: str = ""      # 英文职位
    en_highlights: list[str] = field(default_factory=list)  # 英文 bullet，与 highlights 一一对应

@dataclass
class Education:
    """教育经历"""
    school: str = ""
    degree: str = ""       # 如 "硕士 · 计算机科学"
    period: str = ""
    description: str = ""
    gpa: str = ""          # 如 "3.8/4.0"
    courses: str = ""      # 核心课程，一段文本
    en_school: str = ""
    en_degree: str = ""

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
    year: str = ""          # 如 "2024"
    en_name: str = ""
    en_highlights: list[str] = field(default_factory=list)

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
    # 模板库（tpl_*）扩展字段，缺省时对应板块整体隐藏
    pivot: str = ""                                            # 转型一句话定位（跨界模板头部）
    en_name: str = ""                                          # 英文姓名（国际版）
    en_title: str = ""
    en_summary: str = ""                                       # 英文摘要
    summary_title: str = ""                                    # 摘要板块自定义标题；缺省用模板默认（如"高管摘要"/"个人简介"）
    certifications: list[str] = field(default_factory=list)    # 资质证书
    languages: list[str] = field(default_factory=list)         # 语言能力
    honors: list[str] = field(default_factory=list)            # 荣誉/奖项/媒体报道
    publications: list[Publication] = field(default_factory=list)  # 论文列表
    works: list[WorkItem] = field(default_factory=list)        # 作品/项目卡片
    transferable: list[TransferSkill] = field(default_factory=list)  # 可迁移能力

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
        for key in ["experiences", "education", "projects", "skills", "metrics", "timeline",
                    "publications", "works", "transferable"]:
            if key in data and isinstance(data[key], list):
                cls_map = {
                    "experiences": Experience,
                    "education": Education,
                    "projects": Project,
                    "skills": Skill,
                    "metrics": Metric,
                    "timeline": TimelineStep,
                    "publications": Publication,
                    "works": WorkItem,
                    "transferable": TransferSkill,
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

@dataclass
class Publication:
    """学术论文（学术模板）"""
    title: str = ""
    venue: str = ""         # 期刊/会议名，斜体展示
    year: str = ""
    tags: list[str] = field(default_factory=list)  # 如 ["CCF-A", "Oral"]

@dataclass
class WorkItem:
    """作品卡（创意模板）"""
    name: str = ""
    role: str = ""          # 如 "主创设计师"
    year: str = ""
    description: str = ""
    result: str = ""        # 关键结果，如 "品牌认知度 +19pt"

@dataclass
class TransferSkill:
    """可迁移能力卡（转型模板）"""
    source: str = ""        # 原能力域，如 "教研设计"
    ability: str = ""       # 迁移后能力，如 "需求拆解与结构化"
    description: str = ""
    mapping: str = ""       # 对应目标岗位能力，如 "需求分层 · 信息架构"

def _resume_period(start: str | None, end: str | None) -> str:
    if not start and not end:
        return ""
    if start and end:
        return f"{start} - {end}"
    return str(start or end or "")

def _string_list(value) -> list:
    """把字符串/字符串列表统一成列表（LLM 传入混型字段时的类型收敛）。"""
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


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
                    "highlights": _string_list(item.get("points") or item.get("highlights")),
                    "projects": item.get("projects") or item.get("project_groups") or [],
                    "scale": item.get("scale") or "",
                    "en_company": item.get("en_company") or "",
                    "en_title": item.get("en_title") or "",
                    "en_highlights": _string_list(item.get("en_points") or item.get("en_highlights")),
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
                    "highlights": _string_list(item.get("highlights") or item.get("points")),
                    "projects": item.get("projects") or item.get("project_groups") or [],
                    "scale": item.get("scale") or "",
                    "en_company": item.get("en_company") or "",
                    "en_title": item.get("en_title") or "",
                    "en_highlights": _string_list(item.get("en_points") or item.get("en_highlights")),
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

    for key in ("certifications", "languages", "honors"):
        value = normalized.get(key) or []
        if isinstance(value, str):
            value = [value]
        normalized[key] = [str(item) for item in value if str(item).strip()]

    publications = []
    for item in normalized.get("publications") or []:
        if not isinstance(item, dict):
            continue
        tags = item.get("tags") or []
        if isinstance(tags, str):
            tags = [part.strip() for part in tags.replace("，", ",").split(",") if part.strip()]
        publications.append(
            {
                "title": item.get("title") or "",
                "venue": item.get("venue") or item.get("journal") or "",
                "year": str(item.get("year") or ""),
                "tags": [str(tag) for tag in tags],
            }
        )
    normalized["publications"] = publications

    works = []
    for item in normalized.get("works") or []:
        if not isinstance(item, dict):
            continue
        works.append(
            {
                "name": item.get("name") or item.get("title") or "",
                "role": item.get("role") or "",
                "year": str(item.get("year") or ""),
                "description": item.get("description") or item.get("desc") or "",
                "result": item.get("result") or item.get("impact") or "",
            }
        )
    normalized["works"] = works

    transferable = []
    for item in normalized.get("transferable") or []:
        if not isinstance(item, dict):
            continue
        transferable.append(
            {
                "source": item.get("source") or item.get("from") or "",
                "ability": item.get("ability") or item.get("to") or "",
                "description": item.get("description") or item.get("evidence") or "",
                "mapping": item.get("mapping") or "",
            }
        )
    normalized["transferable"] = transferable

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
                "gpa": str(item.get("gpa") or ""),
                "courses": item.get("courses") or "",
                "en_school": item.get("en_school") or "",
                "en_degree": item.get("en_degree") or "",
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
        if isinstance(actions, str):
            actions = [part.strip() for part in re.split(r"[；;]", actions) if part.strip()]
        impact = item.get("impact") or ""
        highlights = (
            item.get("points")
            or item.get("highlights")
            or actions
            or ([impact] if impact else [])
        )
        if isinstance(highlights, str):
            highlights = [highlights]
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
                "year": str(item.get("year") or ""),
                "en_name": item.get("en_name") or "",
                "en_highlights": _string_list(item.get("en_highlights") or item.get("en_points")),
            }
        )
    normalized["projects"] = projects

    # 直接传 experiences 时的同样类型收敛（不经 work/experience 兼容层）
    direct_experiences = []
    for item in normalized.get("experiences") or []:
        if not isinstance(item, dict):
            continue
        item = dict(item)
        if "highlights" in item:
            item["highlights"] = _string_list(item.get("highlights"))
        item["en_highlights"] = _string_list(item.get("en_highlights") or item.get("en_points"))
        direct_experiences.append(item)
    if direct_experiences:
        normalized["experiences"] = direct_experiences

    raw_skills = normalized.get("skills")
    if isinstance(raw_skills, str):
        # LLM 可能把技能行拼成一个长字符串传入：含竖线/换行时按行拆
        # （"分类|内容" 行），否则按顿号/逗号拆（关键词串）。
        # 不收敛的话 for 循环会逐字迭代，每个字符变成一个技能。
        text = raw_skills.strip()
        if "|" in text or "\n" in text:
            raw_skills = [p.strip() for p in re.split(r"[\n;；]+", text) if p.strip()]
        else:
            raw_skills = [p.strip() for p in re.split(r"[、，,]+", text) if p.strip()]
    skills = []
    for item in raw_skills or []:
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
