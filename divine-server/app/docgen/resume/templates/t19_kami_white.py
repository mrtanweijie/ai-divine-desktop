"""模板 19 · Kami 纯白（自旧 kami_white 主题迁入）— Kami 纯白投递版、打印零风险"""

from __future__ import annotations

from .kami_layout import kami_resume_html

id = "kami_white"

CSS = r'''
/* ============================================================
   Kami Resume Theme
   暖色纸感底 #f5f4ed / 墨蓝 #1B365D / 衬线承担层级
   ============================================================ */

@page {
  size: A4;
  margin: 11mm 13mm 11mm 13mm;
  background: #ffffff;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --parchment: #ffffff;
  --ivory: #ffffff;
  --border: #dcd9cd;
  --border-soft: #d8d5c9;
  --near-black: #141413;
  --dark-warm: #3d3d3a;
  --olive: #504e49;
  --stone: #6b6a64;
  --brand: #1B365D;
  --brand-tint: #EEF2F7;
  --serif: "TsangerJinKai02", "Source Han Serif SC", "Source Han Serif CN",
           "Noto Serif CJK SC", "Noto Serif SC", "Songti SC", "STSong",
           "SimSun", Georgia, "Times New Roman", serif;
}

html, body { background: var(--parchment); }

body {
  color: var(--near-black);
  font-family: var(--serif);
  font-size: 9.2pt;
  line-height: 1.42;
  letter-spacing: 0.3pt;
  widows: 3;
  orphans: 3;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}

.serif { font-family: var(--serif); }
a { color: var(--brand); text-decoration: none; }

/* ===== Header ===== */
.header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 4.2mm;
  padding-bottom: 2.3mm;
  border-bottom: 0.6pt solid var(--border);
}
.header > div:first-child { flex-shrink: 0; }
.name {
  font-family: var(--serif);
  font-size: 26.5pt;
  font-weight: 500;
  letter-spacing: 0.5pt;
  color: var(--near-black);
  line-height: 1;
  display: flex;
  align-items: baseline;
  gap: 2.2mm;
  white-space: nowrap;
}
.alias {
  font-size: 12.5pt;
  font-weight: 400;
  color: var(--stone);
  letter-spacing: 0.2pt;
}
.tagline {
  font-size: 9.5pt;
  color: var(--olive);
  line-height: 1.3;
  margin-top: 1mm;
}
.tagline .accent { color: var(--brand); font-weight: 500; }
.contact {
  text-align: right;
  font-size: 9pt;
  color: var(--stone);
  line-height: 1.5;
  margin-bottom: -0.5mm;
}
.contact .role { color: var(--brand); font-size: 10.5pt; font-weight: 500; }
.contact .sep { color: var(--border); margin: 0 0.4em; }
.contact .loc { color: var(--olive); font-weight: 500; }
.contact .status { color: var(--brand); font-weight: 500; }

/* ===== 4 个数字卡片 ===== */
.metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  column-gap: 6mm;
  margin-bottom: 3mm;
}
.metric {
  padding: 1mm 0 1.2mm;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.7mm;
  min-width: 0;
  break-inside: avoid;
}
/* 相邻数字卡片之间的极细分隔，强化「卡片组」的视觉分组 */
.metric + .metric {
  border-left: 0.4pt solid var(--border-soft);
  padding-left: 3mm;
}
.metric-value {
  font-family: var(--serif);
  font-size: 13pt;
  font-weight: 500;
  color: var(--brand);
  line-height: 1;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.metric-value .unit {
  font-size: 10.5pt;
  margin-left: 0.3mm;
  font-weight: 500;
  color: var(--brand);
}
.metric-label {
  font-size: 9pt;
  color: var(--olive);
  line-height: 1.2;
  white-space: nowrap;
}

/* ===== Section ===== */
.section-title {
  position: relative;
  font-family: var(--serif);
  font-size: 12.5pt;
  font-weight: 500;
  line-height: 1.15;
  color: var(--near-black);
  padding: 0 0 1mm 2.5mm;
  margin: 8mm 0 1.7mm 0;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 2mm;
}
.section-title::before {
  content:"";font-size:0;
  position: absolute;
  left: 0;
  top: 0.65mm;
  width: 2.5pt;
  height: 3.8mm;
  background: var(--brand);
  border-radius: 0.5pt;
}
.section-title .sub {
  font-family: var(--serif);
  font-weight: 400;
  font-size: 9pt;
  color: var(--stone);
  letter-spacing: 0.3pt;
}
section:first-of-type .section-title { margin-top: 0; }

/* ===== Summary ===== */
.summary {
  font-size: 9.2pt;
  line-height: 1.42;
  color: var(--near-black);
}
.summary .hl { color: var(--brand); }

/* ===== Timeline ===== */
.timeline {
  display: flex;
  gap: 6mm;
  margin-bottom: 2mm;
}
.tl-step { flex: 1; padding: 0.8mm 0; break-inside: avoid; }
.tl-top {
  display: flex;
  align-items: baseline;
  gap: 1.5mm;
  margin-bottom: 0.5mm;
}
.tl-year {
  font-family: var(--serif);
  font-size: 11pt;
  font-weight: 500;
  color: var(--brand);
  line-height: 1;
}
.tl-head {
  font-size: 11pt;
  font-weight: 500;
  color: var(--near-black);
}
.tl-body {
  font-size: 9pt;
  color: var(--olive);
  line-height: 1.4;
  letter-spacing: 0.3pt;
}

/* ===== Projects ===== */
.project {
  padding: 2.6mm 0;
  break-inside: avoid;
}
.project:first-of-type { padding-top: 1.2mm; }
.proj-head {
  display: block;
  margin-bottom: 0.75mm;
}
.proj-name {
  font-family: var(--serif);
  font-size: 11pt;
  font-weight: 500;
  color: var(--near-black);
}
.proj-kind {
  font-size: 11pt;
  color: var(--olive);
  margin-left: 1.5mm;
}
.proj-role {
  font-size: 9pt;
  color: var(--brand);
  font-weight: 500;
  float: right;
  background: var(--brand-tint);
  padding: 0.4mm 1.2mm;
  border-radius: 2pt;
  letter-spacing: 0.05pt;
  white-space: nowrap;
}
.proj-lines { display: table; width: 100%; }
.proj-row { display: table-row; }
.proj-label {
  display: table-cell;
  width: 11mm;
  font-size: 9pt;
  color: var(--brand);
  font-weight: 500;
  letter-spacing: 0.2pt;
  padding: 0.2mm 0 0.4mm 0;
  vertical-align: top;
}
.proj-text {
  display: table-cell;
  font-size: 9pt;
  color: var(--near-black);
  line-height: 1.4;
  letter-spacing: 0.3pt;
  padding: 0 0 0.4mm 0.5mm;
}
.proj-text .hl { color: var(--brand); }

/* ===== 工作经历（内容向） ===== */
.job {
  padding: 2.2mm 0;
  break-inside: auto;
}
.job-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 0.8mm;
  break-after: avoid;
}
.job-header .company {
  font-family: var(--serif);
  font-size: 10.5pt;
  font-weight: 700;
  color: var(--near-black);
}
.job-header .company .dept {
  font-weight: 400;
  color: var(--olive);
  font-size: 9.5pt;
}
.job-header .company .position {
  font-weight: 400;
  color: var(--stone);
  font-size: 8.5pt;
}
.job-header .period {
  font-size: 8.5pt;
  color: var(--stone);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.job-role {
  font-size: 9.5pt;
  font-weight: 500;
  color: var(--dark-warm);
  margin-bottom: 0.8mm;
}
.job-desc {
  font-size: 9pt;
  color: var(--olive);
  margin: 0.5mm 0 1mm 0;
  line-height: 1.45;
}
.job ul {
  list-style: none;
  padding-left: 0;
  margin: 0.5mm 0 0 0;
  orphans: 2;
  widows: 2;
}
.job ul li {
  position: relative;
  padding-left: 5mm;
  font-size: 9pt;
  color: var(--near-black);
  line-height: 1.5;
  margin-bottom: 1.6mm;
}
.job ul li::before {
  content: "›";
  position: absolute;
  left: 2mm;
  color: var(--brand);
  font-size: 8.5pt;
}
.project-name {
  position: relative;
  padding-left: 1.8mm;
  font-size: 10.5pt;
  font-weight: 500;
  line-height: 1.2;
  color: var(--brand);
  margin: 1.8mm 0 0.5mm 0;
  break-after: avoid;
}
.project-name::before {
  content:"";font-size:0;
  position: absolute;
  left: 0;
  top: 0.7mm;
  width: 2pt;
  height: 2.6mm;
  background: var(--brand);
  border-radius: 0.5pt;
}
.project-summary {
  font-size: 9pt;
  font-weight: 400;
  color: var(--stone);
  line-height: 1.4;
  margin-left: 0.6mm;
}

/* ===== 个人亮点 ===== */
.highlight-list {
  list-style: none;
  padding-left: 0;
  margin: 0;
}
.highlight-list li {
  position: relative;
  padding-left: 5mm;
  font-size: 9pt;
  color: var(--near-black);
  line-height: 1.45;
  margin-bottom: 0.8mm;
}
.highlight-list li::before {
  content: "›";
  position: absolute;
  left: 2mm;
  color: var(--brand);
  font-size: 8.5pt;
}

/* ===== Page 2 ===== */
.page-break { break-before: page; }

/* ===== Skills ===== */
.skill-row {
  display: flex;
  gap: 2.5mm;
  padding: 1.7mm 0;
  border-bottom: 0.3pt dotted var(--border);
  align-items: baseline;
}
.skill-row:last-of-type { border-bottom: none; }
.skill-row:last-child { border-bottom: none; }
.skill-label {
  font-size: 9pt;
  font-weight: 500;
  color: var(--brand);
  letter-spacing: 0.3pt;
  width: 22mm;
  flex-shrink: 0;
  line-height: 1.36;
}
.skill-body {
  font-size: 9pt;
  color: var(--near-black);
  line-height: 1.4;
  letter-spacing: 0.3pt;
  flex: 1;
}
.skill-body .hl { color: var(--brand); }

/* ===== Education ===== */
.edu-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: 9.5pt;
  padding: 1.7mm 0;
}
.edu-row .school {
  font-family: var(--serif);
  font-weight: 500;
  font-size: 10.7pt;
}
.edu-row .major { color: var(--olive); font-size: 9.5pt; }
.edu-row .date {
  color: var(--stone);
  font-variant-numeric: tabular-nums;
  font-size: 9pt;
}
.edu-desc {
  font-size: 9pt;
  color: var(--olive);
  margin-top: 0.3mm;
  line-height: 1.4;
}

/* ===== Public work ===== */
.os-item {
  display: flex;
  align-items: baseline;
  gap: 2mm;
  padding: 1mm 0;
  border-bottom: 0.3pt dotted var(--border);
  break-inside: avoid;
}
.os-item:last-child { border-bottom: none; }
.os-name {
  font-family: var(--serif);
  font-size: 10pt;
  font-weight: 500;
  flex-shrink: 0;
}
.os-desc {
  font-size: 9pt;
  color: var(--olive);
  line-height: 1.4;
  flex: 1;
}
'''

PRINT_SINGLE = ""

def render(r) -> str:
    return kami_resume_html(r)
