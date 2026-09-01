"""Finance resume theme CSS."""

from __future__ import annotations

FINANCE_CSS = r"""
/* ============================================================
   Finance Resume Theme — 金融经典
   适用：金融/银行/投行/证券/基金/财务/审计
   特点：衬线字体、黑白双线、克制正式、ATS 友好
   ============================================================ */

@page {
  size: A4;
  margin: 16mm 17mm 15mm 17mm;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: "Times New Roman", "Source Han Serif CN", "Noto Serif SC", "SimSun", serif;
  font-size: 9.5pt;
  line-height: 1.5;
  color: #1a1a1a;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}

/* ===== Header 左对齐信息条 ===== */
.header {
  margin-bottom: 3mm;
  text-align: left;
}

.header h1 {
  font-size: 20pt;
  font-weight: 700;
  color: #000;
  letter-spacing: 3pt;
  margin-bottom: 1.5mm;
  line-height: 1.2;
}

.header .subtitle {
  font-size: 9pt;
  color: #444;
  margin-bottom: 2mm;
  letter-spacing: 0.3pt;
}

.header .contact {
  font-size: 7.5pt;
  color: #666;
  letter-spacing: 0.2pt;
}

.header .contact .sep {
  margin: 0 4px;
  color: #bbb;
}

.header-rule {
  height: 0;
  border-top: 1.5pt solid #000;
  border-bottom: 0.5pt solid #000;
  padding-top: 0.8mm;
  margin-top: 3mm;
}

/* ===== 模块 ===== */
.section {
  margin-top: 4.5mm;
}

.section-title {
  font-size: 9pt;
  font-weight: 700;
  color: #000;
  text-transform: uppercase;
  letter-spacing: 2pt;
  border-bottom: 0.8pt solid #000;
  padding-bottom: 0.8mm;
  margin-bottom: 2.5mm;
}

/* ===== 条目 ===== */
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
  font-size: 9.5pt;
  font-weight: 700;
  color: #1a1a1a;
}

.entry-head .left .sep {
  color: #bbb;
  margin: 0 3px;
}

.entry-head .left .role {
  font-weight: 400;
  font-style: italic;
  color: #333;
}

.entry-head .right {
  display: table-cell;
  text-align: right;
  font-size: 8pt;
  color: #666;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.entry .desc {
  font-size: 9pt;
  color: #333;
  margin-bottom: 0.8mm;
}

.entry ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.entry li {
  font-size: 9pt;
  color: #222;
  padding-left: 14px;
  position: relative;
  line-height: 1.55;
  margin-bottom: 0.3mm;
}

.entry li::before {
  content: "▪";
  position: absolute;
  left: 0;
  top: 0;
  color: #000;
  font-size: 6pt;
  line-height: 2.5;
}

.skills {
  font-size: 9pt;
  color: #222;
  line-height: 1.8;
}

.skills b {
  font-weight: 700;
  color: #000;
}

.edu .school {
  font-weight: 700;
  font-size: 9.5pt;
}

.edu .meta {
  font-size: 8pt;
  color: #666;
  margin-top: 0.3mm;
  font-style: italic;
}
"""
