"""Shared HTML escaping and resume formatting helpers."""

from __future__ import annotations

import re

from ..models import ResumeData

def _esc(text: str) -> str:
    """HTML 转义"""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

_NUMBER_RE = re.compile(
    r"(\d+(?:\.\d+)?\s*(?:%|ms|s|fps|年|月|天|周|倍|万\+?|亿\+?|\+)?)"
)

def _highlight_numbers(text: str) -> str:
    """把数字/指标包成 Kami 的强调色。"""
    return _NUMBER_RE.sub(r'<span class="hl">\1</span>', _esc(text))

def _format_resume_line(text: str) -> str:
    """加粗 bullet 开头的小标题，并高亮数字指标。"""
    escaped = _esc(text)
    match = re.match(r"^([^：:]{1,14})[：:]", escaped)
    if match:
        label = match.group(1)
        body = escaped[match.end():]
        return f"<b>{label}</b>：" + _NUMBER_RE.sub(
            r'<span class="hl">\1</span>',
            body,
        )
    return _NUMBER_RE.sub(r'<span class="hl">\1</span>', escaped)


def bold_resume_line(text: str) -> str:
    """旧主题通用的成果强调：转义后加粗「导语：」与关键数字。

    与 kami 的 _format_resume_line 同构，但用 <b> 而非 .hl 着色，
    避免旧主题需要为每个颜色方案补 .hl 样式。
    """
    escaped = _esc(text)
    match = re.match(r"^([^：:]{1,14})[：:]", escaped)
    prefix = ""
    if match:
        prefix = f"<b>{match.group(1)}：</b>"
        escaped = escaped[match.end():]
    return prefix + _NUMBER_RE.sub(r"<b>\1</b>", escaped)


def split_labeled_skill(name: str) -> tuple[str, str] | None:
    """拆 "分类|内容" 技能行；无竖线或单侧为空返回 None。"""
    if "|" not in name:
        return None
    label, body = name.split("|", 1)
    label, body = label.strip(), body.strip()
    if label and body:
        return label, body
    return None


def skill_pairs_and_plain(
    resume: ResumeData,
) -> tuple[list[tuple[str, str]], list[str]]:
    """旧主题技能区统一出口，消灭 "分类|内容" 竖线泄漏。

    返回 (pairs, plain)：pairs 为 (分类, 内容) 原文（未转义），
    plain 为散技能名。skill_groups 优先，其次逐条拆分 skills。
    """
    if resume.skill_groups:
        return (
            [
                (name, "、".join(str(v) for v in values))
                for name, values in resume.skill_groups.items()
            ],
            [],
        )
    pairs: list[tuple[str, str]] = []
    plain: list[str] = []
    for s in resume.skills:
        labeled = split_labeled_skill(s.name)
        if labeled:
            pairs.append(labeled)
        elif s.name.strip():
            plain.append(s.name.strip())
    if not pairs and not plain and resume.core_skills:
        plain = list(resume.core_skills)
    return pairs, plain

def _split_value_unit(value: str) -> tuple[str, str]:
    match = re.match(r"^(\d+(?:\.\d+)?)(.*)$", value or "")
    if match:
        return match.group(1), match.group(2)
    return value or "", ""

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
