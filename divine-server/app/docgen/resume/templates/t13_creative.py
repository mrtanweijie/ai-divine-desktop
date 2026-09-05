"""模板 13 · 现代创意紫橙（自旧 creative 主题迁入）— 顶部渐变 Header + 卡片双栏。"""

from __future__ import annotations

from .helpers import _esc, bold_resume_line

id = "creative"

CSS = """:root{
  --sans:"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans SC","Inter","Helvetica Neue",Arial,sans-serif;
  --ink:#1e1e2e; --line:#dfdcd4;
  --brand:#7c3aed; --brand-soft:#e3f2ed;
}
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: var(--sans);
  font-size: 9.5pt;
  line-height: 1.65;
  color: #1e1e2e;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}

@page {
  size: A4;
  margin: 0;
}

/* ===== Header 顶部色块 ===== */
.header {
  background: linear-gradient(135deg, #7c3aed 0%, #a855f7 50%, #ec4899 100%);
  padding: 32pt 30pt 28pt 30pt;
  color: white;
}

.header .name {
  font-size: 30pt;
  font-weight: 800;
  letter-spacing: -0.02em;
  line-height: 1.15;
  margin-bottom: 4pt;
}

.header .subtitle {
  font-size: 11pt;
  font-weight: 300;
  opacity: 0.9;
  margin-bottom: 12pt;
}

.header .contact-row {
  display: flex;
  flex-wrap: wrap;
  gap: 14pt;
}

.header .contact-item {
  font-size: 8.8pt;
  opacity: 0.9;
  display: flex;
  align-items: center;
  gap: 4pt;
}

/* ===== Body 区域 ===== */
.body {
  padding: 22pt 30pt 26pt 30pt;
}

/* ===== 双栏主体 =====
   用 table-cell 而非 flex：WeasyPrint 无法分割 flex 容器，
   内容超页时整块被搬到下一页（曾导致首页大面积空白）；表格单元格可正常跨页。 */
.two-col {
  display: table;
  width: 100%;
  table-layout: fixed;
  border-spacing: 0;
}

.col-left {
  display: table-cell;
  width: 62%;
  vertical-align: top;
  padding-right: 11pt;
}

.col-right {
  display: table-cell;
  width: 38%;
  vertical-align: top;
  padding-left: 11pt;
}

/* ===== Section 标题 ===== */
.section {
  margin-bottom: 16pt;
  page-break-inside: auto;
}

.section h2 {
  font-size: 10.5pt;
  font-weight: 700;
  color: #7c3aed;
  margin-bottom: 8pt;
  display: flex;
  align-items: center;
  gap: 6pt;
  break-after: avoid;
}

.section h2::before {
  content:"";font-size:0;
  display: inline-block;
  width: 12pt;
  height: 3pt;
  background: linear-gradient(90deg, #7c3aed, #ec4899);
  border-radius: 2pt;
}

/* ===== 经历卡片 ===== */
.card {
  background: #faf5ff;
  border-radius: 6pt;
  padding: 10pt 12pt;
  margin-bottom: 10pt;
  border-left: 3pt solid #a855f7;
  page-break-inside: avoid;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 4pt;
}

.card-title {
  font-size: 10pt;
  font-weight: 600;
  color: #2d1b69;
}

.card-subtitle {
  font-size: 9pt;
  color: #6b5b95;
}

.card-period {
  font-size: 8pt;
  color: #a78bfa;
  white-space: nowrap;
}

.card-body {
  font-size: 8.8pt;
  color: #3d2b6e;
  line-height: 1.6;
}

.card-body ul {
  padding-left: 1.1em;
  margin: 3pt 0;
}

.card-body li {
  margin: 2pt 0;
}

/* ===== 技能标签云（右侧栏用） ===== */
.skill-group {
  margin-bottom: 12pt;
}

.skill-group h4 {
  font-size: 9pt;
  font-weight: 600;
  color: #5b21b6;
  margin-bottom: 5pt;
}

.skill-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4pt;
}

/* "分类|内容" 技能行的正文（右栏窄栏内长文本） */
.skill-group .skill-body {
  font-size: 8.3pt;
  color: #5b4a8a;
  line-height: 1.6;
}

.skill-group .skill-body b {
  color: #5b21b6;
  font-weight: 600;
}

.skill-tag {
  font-size: 7.8pt;
  padding: 2pt 7pt;
  background: linear-gradient(135deg, #ede9fe, #fce7f3);
  color: #6b21a8;
  border-radius: 3pt;
  font-weight: 500;
}

/* ===== 项目（带链接感） ===== */
.project-card {
  background: white;
  border: 1pt solid #e9d5ff;
  border-radius: 6pt;
  padding: 10pt 12pt;
  margin-bottom: 10pt;
  page-break-inside: avoid;
}

.project-card .name {
  font-size: 10pt;
  font-weight: 600;
  color: #2d1b69;
  margin-bottom: 3pt;
}

.project-card .desc {
  font-size: 8.8pt;
  color: #4a3a7a;
  line-height: 1.55;
}

.project-card .project-highlights {
  margin-top: 4pt;
}

.project-card .project-highlights ul {
  margin: 0;
  padding-left: 1.2em;
}

.project-card .project-highlights li {
  margin: 1pt 0;
  font-size: 8.3pt;
  color: #5b4a8a;
}

/* ===== 摘要 ===== */
.summary {
  font-size: 9.5pt;
  color: #2d2d3a;
  line-height: 1.75;
  background: linear-gradient(135deg, #faf5ff, #fdf2f8);
  padding: 12pt 14pt;
  border-radius: 6pt;
  margin-bottom: 4pt;
}

/* ===== 教育 ===== */
.edu-card {
  margin-bottom: 10pt;
  page-break-inside: avoid;
}

.edu-card .degree {
  font-size: 10pt;
  font-weight: 600;
  color: #2d1b69;
}

.edu-card .school {
  font-size: 9pt;
  color: #6b5b95;
}

.edu-card .meta {
  font-size: 8.5pt;
  color: #a78bfa;
  margin-top: 2pt;
}
"""

PRINT_SINGLE = ""


def render(r) -> str:
    c = r.contact

    contact_items = []
    if c.email:
        contact_items.append(f'<span>✉ {_esc(c.email)}</span>')
    if c.phone:
        contact_items.append(f'<span>☎ {_esc(c.phone)}</span>')
    if c.location or c.city or c.address:
        location = c.location or c.city or c.address
        contact_items.append(f'<span>⌂ {_esc(location)}</span>')
    if c.wechat:
        contact_items.append(f'<span>◈ {_esc(c.wechat)}</span>')
    if c.github:
        contact_items.append(f'<span>⎇ {_esc(c.github)}</span>')
    if c.linkedin:
        contact_items.append(f'<span>in {_esc(c.linkedin)}</span>')
    contact_html = "\n".join(contact_items)

    # 左栏：经历卡片
    exp_html = ""
    for e in r.experiences:
        highlights = "".join(f"<li>{bold_resume_line(h)}</li>" for h in e.highlights)
        desc = bold_resume_line(e.description).replace("\n", "<br>") if e.description else ""
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
    for p in r.projects:
        highlights = "".join(f"<li>{bold_resume_line(h)}</li>" for h in p.highlights)
        proj_html += f"""
        <div class="project-card">
          <div class="name">{_esc(p.name)}{f' · {_esc(p.role)}' if p.role else ''}</div>
          <div class="desc">{bold_resume_line(p.description)}</div>
          {f'<div class="project-highlights"><ul>{highlights}</ul></div>' if highlights else ''}
        </div>"""

    # 右栏：技能分组；"分类|内容" 行拆为 分组标题 + 正文，不再渲染编造的百分比
    from .helpers import skill_pairs_and_plain

    pairs, plain = skill_pairs_and_plain(r)
    skills_html = ""
    for label, body in pairs:
        skills_html += f"""
        <div class="skill-group">
          <h4>{_esc(label)}</h4>
          <div class="skill-body">{bold_resume_line(body)}</div>
        </div>"""
    if plain:
        tags = "".join(f'<span class="skill-tag">{_esc(s)}</span>' for s in plain)
        skills_html += f"""<div class="skill-group"><div class="skill-tags">{tags}</div></div>"""

    # 右栏：教育
    edu_html = ""
    for e in r.education:
        edu_html += f"""
        <div class="edu-card">
          <div class="degree">{_esc(e.degree)}</div>
          <div class="school">{_esc(e.school)}</div>
          <div class="meta">{_esc(e.period)}{f' · {_esc(e.description)}' if e.description else ''}</div>
        </div>"""

    summary_html = f'<div class="summary">{bold_resume_line(r.summary)}</div>' if r.summary else ""

    return f"""
    <div class="header">
      <div class="name">{_esc(r.name)}</div>
      <div class="subtitle">{_esc(r.title)}</div>
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
