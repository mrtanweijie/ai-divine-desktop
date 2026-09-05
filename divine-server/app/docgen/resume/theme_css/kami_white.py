"""Kami pure-white resume theme CSS."""

from __future__ import annotations

KAMI_WHITE_CSS = r"""
/* ============================================================
   Kami Resume Theme — 纯白投递版
   适用：社招技术岗、投递前定制、一页简历
   特点：纯白背景、章节标题左侧品牌色竖线、克制高密度
   ============================================================ */

@page {
  size: A4;
  margin: 18mm 20mm 16mm 20mm;
  background: #ffffff;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: "Source Han Serif CN", "Noto Serif SC", "Songti SC", "SimSun", serif;
  font-size: 9.5pt;
  line-height: 1.6;
  color: #1f2329;
  background: #ffffff;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 24pt;
  margin-bottom: 5mm;
}

.header h1 {
  font-size: 23pt;
  font-weight: 700;
  color: #111827;
  letter-spacing: 0.5pt;
  margin-bottom: 2mm;
  line-height: 1.15;
}

.header-side {
  text-align: right;
  padding-top: 2mm;
}

.header .subtitle {
  font-size: 10pt;
  color: #203b61;
  font-weight: 600;
  margin-bottom: 2mm;
}

.header .contact {
  font-size: 8.5pt;
  color: #6b7280;
  line-height: 1.8;
}

.header .contact .sep {
  color: #d8d5c9;
  margin: 0 5px;
}

.section {
  margin-top: 5mm;
}

.section-title {
  font-size: 11pt;
  font-weight: 700;
  color: #203b61;
  border-left: 3pt solid #203b61;
  padding-left: 8pt;
  margin-bottom: 2.5mm;
  line-height: 1.3;
  break-after: avoid;
}

.entry {
  margin-bottom: 3.5mm;
  page-break-inside: avoid;
}

.entry:last-child {
  margin-bottom: 0;
}

.entry-head {
  display: table;
  width: 100%;
  margin-bottom: 0.8mm;
}

.entry-head .left {
  display: table-cell;
  font-size: 9.8pt;
  font-weight: 700;
  color: #1f2329;
}

.entry-head .left .sep {
  color: #d8d5c9;
  margin: 0 4px;
}

.entry-head .left .role {
  font-weight: 500;
  color: #4b5563;
}

.entry-head .right {
  display: table-cell;
  text-align: right;
  font-size: 8.3pt;
  color: #6b7280;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.entry .desc {
  font-size: 9pt;
  color: #4b5563;
  margin-bottom: 0.8mm;
}

.entry ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.entry li {
  font-size: 9pt;
  color: #2b2f36;
  padding-left: 12px;
  position: relative;
  line-height: 1.55;
  margin-bottom: 0.3mm;
}

.entry li::before {
  content: "–";
  position: absolute;
  left: 0;
  top: 0;
  color: #203b61;
  font-weight: 700;
}

.skills {
  font-size: 9pt;
  color: #374151;
  line-height: 1.8;
}

.skills b {
  font-weight: 700;
  color: #203b61;
}

/* "分类|内容" 技能行：逐行「分类：内容」 */
.skill-row {
  font-size: 9pt;
  color: #374151;
  line-height: 1.7;
  margin-bottom: 1.2mm;
}

.skill-row b {
  font-weight: 700;
  color: #203b61;
}

.edu .school {
  font-weight: 700;
  font-size: 9.8pt;
}

.edu .meta {
  font-size: 8.3pt;
  color: #6b7280;
  margin-top: 0.3mm;
}
"""
