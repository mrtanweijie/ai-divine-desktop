"""Minimal resume theme CSS."""

from __future__ import annotations

MINIMAL_CSS = r"""
/* ============================================================
   Minimal Resume Theme — 极简黑白
   适用：学术/咨询/金融/法律/政府
   特点：大量留白 + 细线分隔 + 无装饰 + 衬线可选
   ============================================================ */

@page {
  size: A4;
  margin: 0;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Noto Sans SC', 'Inter', 'Helvetica Neue', Arial, sans-serif;
  font-size: 9.5pt;
  line-height: 1.7;
  color: #1a1a1a;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}

/* ===== Header ===== */
.header {
  padding: 36pt 34pt 20pt 34pt;
  border-bottom: 0.5pt solid #1a1a1a;
}

.header .name {
  font-size: 26pt;
  font-weight: 700;
  color: #000;
  letter-spacing: -0.01em;
  line-height: 1.2;
  margin-bottom: 6pt;
}

.header .contact-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16pt;
  font-size: 8.8pt;
  color: #444;
}

.header .contact-row span {
  display: flex;
  align-items: center;
  gap: 3pt;
}

/* ===== Body ===== */
.body {
  padding: 22pt 34pt 28pt 34pt;
}

/* ===== Section ===== */
.section {
  margin-bottom: 18pt;
  page-break-inside: auto;
}

.section h2 {
  font-size: 10pt;
  font-weight: 700;
  color: #000;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  margin-bottom: 10pt;
  padding-bottom: 4pt;
  border-bottom: 0.5pt solid #1a1a1a;
  break-after: avoid;
}

/* ===== 经历 ===== */
.exp-item {
  margin-bottom: 14pt;
  page-break-inside: avoid;
}

.exp-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 3pt;
}

.exp-position {
  font-size: 10pt;
  font-weight: 600;
  color: #000;
}

.exp-company {
  font-size: 9.5pt;
  color: #333;
  font-weight: 400;
}

.exp-period {
  font-size: 8.5pt;
  color: #777;
  white-space: nowrap;
}

.exp-body {
  font-size: 9pt;
  color: #2a2a2a;
  line-height: 1.65;
}

.exp-body ul {
  padding-left: 1.2em;
  margin: 3pt 0;
}

.exp-body li {
  margin: 2.5pt 0;
}

/* ===== 技能（极简文字列表） ===== */
.skills-list {
  columns: 2;
  column-gap: 20pt;
  font-size: 9pt;
  color: #2a2a2a;
}

.skills-list ul {
  padding-left: 1em;
  list-style: none;
}

.skills-list li {
  margin: 3pt 0;
  position: relative;
  padding-left: 8pt;
}

.skills-list li::before {
  content: "—";
  position: absolute;
  left: -4pt;
  color: #999;
}

.skills-list li b {
  color: #000;
  font-weight: 600;
}

/* ===== 教育 ===== */
.edu-item {
  margin-bottom: 10pt;
  page-break-inside: avoid;
}

.edu-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.edu-degree {
  font-size: 10pt;
  font-weight: 600;
  color: #000;
}

.edu-school {
  font-size: 9.5pt;
  color: #333;
}

.edu-meta {
  font-size: 8.5pt;
  color: #777;
  margin-top: 2pt;
}

/* ===== 摘要 ===== */
.summary {
  font-size: 9.5pt;
  color: #1a1a1a;
  line-height: 1.8;
  margin-bottom: 4pt;
}

/* ===== 项目 ===== */
.project-item {
  margin-bottom: 12pt;
  page-break-inside: avoid;
}

.project-name {
  font-size: 10pt;
  font-weight: 600;
  color: #000;
  margin-bottom: 2pt;
}

.project-desc {
  font-size: 9pt;
  color: #2a2a2a;
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
  color: #444;
}

/* ===== 分割线装饰 ===== */
.divider {
  border: none;
  border-top: 0.5pt solid #e0e0e0;
  margin: 12pt 0;
}
"""
