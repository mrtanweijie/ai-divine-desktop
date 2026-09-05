"""模板库共享组件：页面外壳、工具条、联系条目、条目块等。

设计母版源自外部 12 套简历模板（单文件 HTML + 内联 CSS + contenteditable），
渲染输出的 HTML 与原模板体验一致：浏览器打开即可点击编辑、⌘P 导出 PDF。
"""

from __future__ import annotations

import re

from ..models import ResumeData
from .helpers import _NUMBER_RE, _esc

# 与原模板一致的编辑态样式提示（悬停淡黄虚线）
EDITABLE_CSS = """
[contenteditable="true"]:hover{background:#fdfbec;outline:1px dashed #d6cb94}
[contenteditable="true"]:focus{outline:1px solid #b9b3a4;background:#fff}
"""

_SAVE_SCRIPT = """
function saveResumeHtml(){
  var html='<!DOCTYPE html>\\n'+document.documentElement.outerHTML;
  var blob=new Blob([html],{type:'text/html;charset=utf-8'});
  var a=document.createElement('a');
  a.href=URL.createObjectURL(blob);
  a.download=(document.title||'resume')+'.html';
  a.click();
}
"""

_LABEL_RE = re.compile(r"^([^：:]{1,14})[：:]")


def bold_numbers(text: str) -> str:
    """HTML 转义后把关键数字与小标题加粗，与模板 <b> 样式一致。"""
    escaped = _esc(text)
    match = _LABEL_RE.match(escaped)
    prefix = ""
    if match:
        prefix = f"<b>{match.group(1)}：</b>"
        escaped = escaped[match.end():]
    return prefix + _NUMBER_RE.sub(r"<b>\1</b>", escaped)


def allow_bold(text: str) -> str:
    """转义后允许内容自带 <b> 强调（用于 pivot 等一句话富文本字段）。"""
    escaped = _esc(text)
    return escaped.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")


def chip_item(name: str, cls: str = "chip") -> str:
    """chip/tag 项："分类|内容" 取分类名做标签，完整内容放 title 提示。"""
    label, _, body = name.partition("|")
    label = label.strip()
    if body and 0 < len(label) <= 12:
        title = f' title="{_esc(body.strip())}"'
        return f'<span class="{cls}"{title}>{_esc(label)}</span>'
    return f'<span class="{cls}">{_esc(name)}</span>'


def contact_items(r: ResumeData) -> list[str]:
    """联系信息条目：城市 电话 邮箱 主页 状态。"""
    c = r.contact
    items: list[str] = []
    location = c.location or c.city or c.address
    if location and c.phone:
        items.append(f"{location} · {c.phone}")
    else:
        if location:
            items.append(location)
        if c.phone:
            items.append(c.phone)
    if c.email:
        items.append(c.email)
    if c.wechat:
        items.append(f"微信 {c.wechat}")
    for site in (c.website, c.github, c.linkedin):
        if site:
            items.append(site)
            break
    if c.status:
        items.append(c.status)
    return [_esc(item) for item in items]


def contact_spans_html(r: ResumeData) -> str:
    """<span> 分隔的联系条（模板用 ::after 添加分隔符）。"""
    return "".join(f"<span>{item}</span>" for item in contact_items(r))


def contact_lines_html(r: ResumeData) -> str:
    """<br> 分行的联系块（右侧栏模板用）。"""
    return "<br>".join(contact_items(r))


def item_hd(org: str, meta: str = "", date: str = "", *,
            org_class: str = "org", meta_class: str = "meta") -> str:
    """标准条目头：组织 · 元信息 ……… 日期（右对齐）。"""
    meta_html = f'<span class="{meta_class}">{_esc(meta)}</span>' if meta else ""
    date_html = f'<span class="date">{_esc(date)}</span>' if date else ""
    return (
        f'<div class="item-hd"><span class="{org_class}">{_esc(org)}</span>'
        f"{meta_html}{date_html}</div>"
    )


def bullets_html(points: list[str], editable: bool = True) -> str:
    """<ul><li> bullet 列表，数字加粗。"""
    if not points:
        return ""
    lis = "".join(f"<li>{bold_numbers(point)}</li>" for point in points if str(point).strip())
    return f"<ul>{lis}</ul>"


def exp_bullets(e) -> list[str]:
    """工作经历 bullet：优先 highlights，其次 description 按行拆分。"""
    points = [str(h) for h in e.highlights if str(h).strip()]
    if not points and e.description:
        points = [line.strip() for line in e.description.splitlines() if line.strip()]
    return points


def exp_content_html(e) -> str:
    """经历内容块：描述/成果 bullet + 嵌套项目（work[].projects）。

    数据规范允许把项目挂在经历条目内（projects[{name,summary,points}]），
    各模板统一在此渲染，避免嵌套项目被静默丢弃。项目渲染为
    「加粗项目名：summary」导语 li + 成果点 li，适配全部模板的 li 样式。
    """
    lis = [
        f"<li>{bold_numbers(point)}</li>"
        for point in exp_bullets(e)
        if str(point).strip()
    ]
    for proj in e.projects or []:
        if not isinstance(proj, dict):
            continue
        name = str(proj.get("name") or "").strip()
        summary = str(proj.get("summary") or proj.get("desc") or "").strip()
        points = [
            str(x).strip()
            for x in (proj.get("points") or proj.get("highlights") or [])
            if str(x).strip()
        ]
        if not name and not points:
            continue
        lead = f"<b>{_esc(name)}</b>" if name else ""
        if summary:
            lead += ("：" if lead else "") + bold_numbers(summary)
        if lead:
            lis.append(f'<li class="lead">{lead}</li>')
        lis.extend(f'<li class="sub">{bold_numbers(p)}</li>' for p in points)
    return f"<ul>{''.join(lis)}</ul>" if lis else ""


def exp_meta(e) -> str:
    """条目元信息：部门 · 职位。"""
    parts = [part for part in (e.dept, e.title) if part]
    return " · ".join(parts)


def skill_kv_pairs(r: ResumeData) -> tuple[list[tuple[str, str]], list[str]]:
    """技能 -> kv 行拆分："分类|内容" 逐条成对，无标签的归入 plain 列表。

    返回 (pairs, plain)：pairs 为 (分类, 内容) 原文（未转义），plain 为散技能名。
    """
    pairs: list[tuple[str, str]] = []
    plain: list[str] = []
    if r.skill_groups:
        for name, values in r.skill_groups.items():
            pairs.append((name, "、".join(str(v) for v in values)))
        return pairs, plain
    for s in r.skills:
        if "|" in s.name:
            label, body = s.name.split("|", 1)
            pairs.append((label.strip(), body.strip()))
        else:
            plain.append(s.name)
    return pairs, plain


def kv_row(key: str, value: str) -> str:
    return (
        '<div class="kv"><div class="k" contenteditable="true">'
        f"{_esc(key)}</div><div class=\"v\" contenteditable=\"true\">{value}</div></div>"
    )


def toolbar_html(display_name: str, tip: str) -> str:
    """固定工具条：模板名 + 提示 + 打印/下载按钮（打印与纯净版自动隐藏/移除）。"""
    return (
        '<div class="toolbar">'
        f"<b>{_esc(display_name)}</b>"
        f'<span class="tip">{_esc(tip)}</span>'
        '<button onclick="window.print()">打印 / 导出 PDF</button>'
        '<button onclick="saveResumeHtml()">下载 HTML</button>'
        "</div>"
    )


def wrap_page(body: str, *, title: str, css: str, editable: bool,
              toolbar: str = "") -> str:
    """组装完整 HTML 文档。

    editable=True：带工具条与 contenteditable（可编辑版，浏览器打开即改，可下载）；
    editable=False：纯净版，去掉工具条、编辑属性与编辑态样式，可直接投递。
    """
    if not editable:
        body = body.replace(' contenteditable="true"', "")
        css = css.replace(EDITABLE_CSS, "\n")
        # 纯净版屏幕预览：无工具栏，纸张顶格、白底、无投影（仅 screen，PDF 走 print 分支不受影响）
        css += "\n@media screen{body{background:#fff}.page{margin:0 auto;box-shadow:none}}"
    toolbar_block = toolbar if editable else ""
    script = f"<script>{_SAVE_SCRIPT}</script>" if editable else ""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{_esc(title)}</title>
<style>{css}</style>
</head>
<body>
{toolbar_block}
{body}
{script}
</body>
</html>"""


def page_foot(left: str, right: str) -> str:
    """页脚：左（姓名·职位）右（联系方式）双栏，打印时固定到每页底部。"""
    return (
        '<div class="foot"><span contenteditable="true">'
        f"{_esc(left)}</span><span contenteditable=\"true\">{_esc(right)}</span></div>"
    )
