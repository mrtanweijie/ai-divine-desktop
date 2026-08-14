"""Professional resume theme CSS."""

from __future__ import annotations

PROFESSIONAL_CSS = r"""
/* ============================================================
   Professional Resume Theme — 经典商务蓝
   适用：投传统行业、大厂、外企
   特点：左深蓝侧边栏 + 右白主内容区，双栏经典布局
   ============================================================ */

@page {
  size: A4;
  margin: 0;
  @bottom-center {
    content: "";
  }
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: 'Noto Sans SC', 'Inter', 'Helvetica Neue', Arial, sans-serif;
  font-size: 9.5pt;
  line-height: 1.65;
  color: #2c3e50;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}

/* ===== 双栏布局 ===== */
.resume {
  display: flex;
  min-height: 297mm;
}

/* ===== 左侧边栏 ===== */
.sidebar {
  width: 33%;
  background: #1e3a5f;
  color: #e8edf3;
  padding: 28pt 20pt;
  display: flex;
  flex-direction: column;
}

.sidebar .name {
  font-size: 22pt;
  font-weight: 700;
  color: #ffffff;
  margin-bottom: 2pt;
  line-height: 1.2;
}

.sidebar .title {
  font-size: 10.5pt;
  color: #93c5fd;
  font-weight: 400;
  margin-bottom: 16pt;
}

/* 侧边栏分区 */
.sidebar-section {
  margin-bottom: 16pt;
}

.sidebar-section h3 {
  font-size: 8.5pt;
  font-weight: 600;
  color: #93c5fd;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  margin-bottom: 6pt;
}

.sidebar-section h3::before {
  content: "";
  display: inline-block;
  width: 8pt;
  height: 2pt;
  background: #93c5fd;
  margin-right: 5pt;
  vertical-align: middle;
}

.sidebar-section p,
.sidebar-section a {
  font-size: 8.8pt;
  color: #cbd5e1;
  text-decoration: none;
  line-height: 1.7;
}

.sidebar-section a:hover {
  color: #fff;
}

.contact-item {
  display: flex;
  align-items: center;
  gap: 6pt;
  margin-bottom: 4pt;
  font-size: 8.5pt;
  color: #cbd5e1;
}

.contact-item .icon {
  width: 12pt;
  text-align: center;
  font-size: 9pt;
}

/* 技能条 */
.skill-item {
  margin-bottom: 6pt;
}

.skill-name {
  font-size: 8.5pt;
  color: #e2e8f0;
  margin-bottom: 2pt;
  display: flex;
  justify-content: space-between;
}

.skill-bar {
  height: 2.5pt;
  background: rgba(255,255,255,0.08);
  border-radius: 2pt;
  overflow: hidden;
}

.skill-bar .fill {
  height: 100%;
  background: linear-gradient(90deg, #60a5fa, #7fb0f7);
  border-radius: 2pt;
}

/* ===== 右侧主内容区 ===== */
.main {
  width: 67%;
  padding: 28pt 26pt;
  background: #ffffff;
}

.main-section {
  margin-bottom: 16pt;
}

.main-section h2 {
  font-size: 11pt;
  font-weight: 700;
  color: #1e3a5f;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 8pt;
  padding-bottom: 4pt;
  border-bottom: 1.5pt solid #1e3a5f;
}

/* 经历条目 */
.experience-item {
  margin-bottom: 12pt;
  page-break-inside: avoid;
}

.exp-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 3pt;
}

.exp-title {
  font-size: 10pt;
  font-weight: 600;
  color: #1e293b;
}

.exp-company {
  font-size: 9.5pt;
  color: #475569;
  font-weight: 400;
}

.exp-period {
  font-size: 8.5pt;
  color: #94a3b8;
  white-space: nowrap;
}

.exp-desc {
  font-size: 9pt;
  color: #334155;
  line-height: 1.65;
  margin-top: 3pt;
}

.exp-desc ul {
  padding-left: 1.2em;
  margin: 3pt 0;
}

.exp-desc li {
  margin: 2pt 0;
}

/* 教育 */
.edu-item {
  margin-bottom: 10pt;
  page-break-inside: avoid;
}

.edu-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 2pt;
}

.edu-degree {
  font-size: 10pt;
  font-weight: 600;
  color: #1e293b;
}

.edu-school {
  font-size: 9.5pt;
  color: #475569;
}

.edu-period {
  font-size: 8.5pt;
  color: #94a3b8;
}

/* 项目 */
.project-item {
  margin-bottom: 10pt;
  page-break-inside: avoid;
}

.project-title {
  font-size: 10pt;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 2pt;
}

.project-desc {
  font-size: 9pt;
  color: #334155;
  line-height: 1.6;
}

.project-highlights {
  margin-top: 3pt;
}

.project-highlights ul {
  margin: 0;
  padding-left: 1.2em;
}

.project-highlights li {
  margin: 1pt 0;
  font-size: 8.5pt;
  color: #475569;
}

.project-tags {
  margin-top: 3pt;
}

.tag {
  display: inline-block;
  font-size: 7.5pt;
  padding: 1pt 6pt;
  background: #eff6ff;
  color: #1d4ed8;
  border-radius: 2pt;
  margin-right: 4pt;
  margin-bottom: 2pt;
}

/* 摘要/自我介绍 */
.summary {
  font-size: 9.5pt;
  color: #334155;
  line-height: 1.7;
  margin-bottom: 4pt;
}
"""
