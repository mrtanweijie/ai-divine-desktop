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
