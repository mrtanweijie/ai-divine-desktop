"""BOSS Zhipin resume theme CSS."""

from __future__ import annotations

BOSS_ZHIPIN_CSS = r"""
/* ===== BOSS 直聘风简历 ===== */
@page {
  size: A4;
  margin: 1.8cm 1.8cm 1.6cm 1.8cm;
  @bottom-right {
    content: counter(page);
    font-size: 8pt;
    color: #999;
    font-family: "Microsoft YaHei", "Noto Sans SC", sans-serif;
  }
}

:root {
  --ink: #1f2329;
  --muted: #6b7280;
  --line: #e3e6eb;
  --brand: #1a3d6e;
}

* { box-sizing: border-box; }

body {
  font-family: "Microsoft YaHei", "Noto Sans SC", "PingFang SC", Arial, sans-serif;
  font-size: 10pt;
  line-height: 1.5;
  color: var(--ink);
  margin: 0;
}

.resume-header {
  text-align: left;
  margin-bottom: 6pt;
}

.resume-header h1 {
  font-size: 21pt;
  font-weight: 700;
  margin: 0 0 2pt 0;
  color: var(--ink);
  letter-spacing: 0.5pt;
}

.resume-header .intent {
  font-size: 10.5pt;
  color: var(--brand);
  font-weight: 600;
  margin-bottom: 3pt;
}

.resume-header .contact {
  font-size: 8.5pt;
  color: var(--muted);
}

.resume-header .contact span {
  margin-right: 10pt;
}

.section {
  margin-top: 10pt;
  page-break-inside: auto;
}

.section-title {
  font-size: 11pt;
  font-weight: 700;
  color: var(--brand);
  border-bottom: 0.75pt solid var(--line);
  padding-bottom: 2pt;
  margin-bottom: 5pt;
}

.summary {
  font-size: 9.5pt;
  color: #333;
  margin: 0 0 2pt 0;
}

.entry {
  margin-bottom: 7pt;
  page-break-inside: avoid;
}

.entry-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.entry-head .org {
  font-size: 10pt;
  font-weight: 700;
}

.entry-head .org .role {
  font-weight: 600;
  color: #333;
}

.entry-head .period {
  font-size: 8.5pt;
  color: var(--muted);
  white-space: nowrap;
}

.entry .desc {
  font-size: 9pt;
  color: #444;
  margin: 1pt 0 2pt 0;
}

.entry ul {
  margin: 2pt 0 0 0;
  padding-left: 12pt;
}

.entry li {
  font-size: 9pt;
  margin: 1.5pt 0;
  line-height: 1.45;
}

.entry li::marker {
  color: var(--brand);
}

.skills-line {
  font-size: 9.5pt;
  color: #333;
}

.skills-line b {
  color: var(--brand);
  font-weight: 600;
}

.edu .school {
  font-weight: 700;
  font-size: 10pt;
}

.edu .meta {
  font-size: 8.5pt;
  color: var(--muted);
}

.resume-header,
.section,
.entry,
.skills-line {
  background: none;
  border-radius: 0;
  box-shadow: none;
}
"""
