"""
Kami 真实简历模板 CSS
- 暖色 parchment 原版：背景 #f5f4ed，墨蓝 #1B365D
- 纯白投递版：背景 #ffffff，分隔线加深一档
版式：4 个数字卡片 + 3 步时间线 + 项目三段式 + 5 技能 + 2 页
"""

_KAMI_CSS_TEMPLATE = r"""
/* ============================================================
   Kami Resume Theme
   暖色纸感底 #f5f4ed / 墨蓝 #1B365D / 衬线承担层级
   ============================================================ */

@page {
  size: A4;
  margin: 11mm 13mm 11mm 13mm;
  background: __BG__;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --parchment: __BG__;
  --ivory: __IVORY__;
  --border: __BORDER__;
  --border-soft: __BORDER_SOFT__;
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
  font-family: var(--serif);
  font-size: 12.5pt;
  font-weight: 500;
  color: var(--near-black);
  border-bottom: 0.5pt solid var(--border);
  padding: 0 0 1mm 0;
  margin: 5.8mm 0 1.7mm 0;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 2mm;
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
"""


def _kami_css(*, parchment: bool) -> str:
    if parchment:
        return (
            _KAMI_CSS_TEMPLATE
            .replace("__BG__", "#f5f4ed")
            .replace("__IVORY__", "#faf9f5")
            .replace("__BORDER__", "#e8e6dc")
            .replace("__BORDER_SOFT__", "#e5e3d8")
        )
    return (
        _KAMI_CSS_TEMPLATE
        .replace("__BG__", "#ffffff")
        .replace("__IVORY__", "#ffffff")
        .replace("__BORDER__", "#dcd9cd")
        .replace("__BORDER_SOFT__", "#d8d5c9")
    )


KAMI_CSS = _kami_css(parchment=True)
KAMI_WHITE_CSS = _kami_css(parchment=False)
