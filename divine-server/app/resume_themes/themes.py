"""
简历主题 CSS 定义
3 套风格：
1. professional  — 经典商务蓝，适合投传统行业/大厂
2. creative     — 现代创意紫橙，适合设计/互联网/创业公司
3. minimal      — 极简黑白，适合学术/咨询/金融
"""

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


CREATIVE_CSS = r"""
/* ============================================================
   Creative Resume Theme — 现代创意紫橙
   适用：设计/互联网/创业公司/海外求职
   特点：顶部色块 Header + 卡片式布局 + 渐变点缀
   ============================================================ */

@page {
  size: A4;
  margin: 0;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: 'Noto Sans SC', 'Inter', 'Helvetica Neue', Arial, sans-serif;
  font-size: 9.5pt;
  line-height: 1.65;
  color: #1e1e2e;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
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

/* ===== 双栏主体 ===== */
.two-col {
  display: flex;
  gap: 22pt;
}

.col-left {
  width: 62%;
}

.col-right {
  width: 38%;
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
}

.section h2::before {
  content: "";
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
  transition: none;
}

.project-card:hover {
  border-color: #a855f7;
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
  font-family: 'Noto Sans SC', 'Inter', 'Helvetica Neue', Arial, sans-serif;
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


LINKEDIN_CSS = r"""
/* ============================================================
   LinkedIn Resume Theme — 领英蓝
   适用：LinkedIn/海外/外企/互联网投递
   特点：顶部品牌蓝条、蓝色强调、标签式技能、现代清晰
   ============================================================ */

@page {
  size: A4;
  margin: 12mm 14mm 12mm 14mm;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: "Segoe UI", "PingFang SC", "Noto Sans SC", "Helvetica Neue", Arial, sans-serif;
  font-size: 9.5pt;
  line-height: 1.55;
  color: #1c1c1c;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}

/* ===== 顶部蓝条 ===== */
.topbar {
  height: 2.2mm;
  background: #0a66c2;
  margin-bottom: 3.5mm;
}

.header {
  margin-bottom: 4mm;
}

.header h1 {
  font-size: 20pt;
  font-weight: 700;
  color: #0a66c2;
  letter-spacing: 0.3pt;
  margin-bottom: 1.5mm;
  line-height: 1.15;
}

.header .subtitle {
  font-size: 10pt;
  color: #555;
  margin-bottom: 2mm;
}

.header .contact {
  font-size: 8pt;
  color: #666;
  line-height: 1.8;
}

.header .contact .sep {
  color: #ddd;
  margin: 0 4px;
}

/* ===== 模块 ===== */
.section {
  margin-top: 4.5mm;
}

.section-title {
  font-size: 10pt;
  font-weight: 700;
  color: #0a66c2;
  text-transform: uppercase;
  letter-spacing: 1.2pt;
  border-bottom: 0.8pt solid #e0e0e0;
  padding-bottom: 1mm;
  margin-bottom: 2.4mm;
}

/* ===== 条目 ===== */
.entry {
  margin-bottom: 3mm;
  page-break-inside: avoid;
}

.entry:last-child {
  margin-bottom: 0;
}

.entry-head {
  display: table;
  width: 100%;
  margin-bottom: 1mm;
}

.entry-head .left {
  display: table-cell;
  font-size: 9.5pt;
  font-weight: 700;
  color: #1c1c1c;
}

.entry-head .left .sep {
  color: #ccc;
  margin: 0 3px;
}

.entry-head .left .role {
  font-weight: 400;
  color: #444;
}

.entry-head .right {
  display: table-cell;
  text-align: right;
  font-size: 8pt;
  color: #777;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.entry .desc {
  font-size: 9pt;
  color: #444;
  margin-bottom: 1mm;
}

.entry ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.entry li {
  font-size: 9pt;
  color: #2c2c2c;
  padding-left: 12px;
  position: relative;
  line-height: 1.55;
  margin-bottom: 0.3mm;
}

.entry li::before {
  content: "▸";
  position: absolute;
  left: 0;
  top: 0;
  color: #0a66c2;
  font-size: 8pt;
  line-height: 1.8;
}

/* ===== 技能标签 ===== */
.skills {
  font-size: 0;
  line-height: 2.0;
}

.skills .tag {
  display: inline-block;
  font-size: 8.5pt;
  padding: 0.8pt 7pt;
  margin: 0 4pt 2pt 0;
  background: #e8f0fe;
  color: #0a66c2;
  border-radius: 2pt;
  font-weight: 500;
}

.skills .tag.strong {
  background: #0a66c2;
  color: #fff;
  font-weight: 600;
}

.edu .school {
  font-weight: 700;
  font-size: 9.5pt;
}

.edu .meta {
  font-size: 8pt;
  color: #777;
  margin-top: 0.3mm;
}
"""

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
  @bottom-right {
    content: counter(page);
    font-size: 8pt;
    color: #999;
    font-family: "Noto Sans SC", sans-serif;
  }
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


def _kami_css(*, parchment: bool) -> str:
    """Kami 两版共用一套样式，只切换纸色与分隔线深浅。"""
    if not parchment:
        return KAMI_WHITE_CSS
    return (
        KAMI_WHITE_CSS
        .replace("纯白投递版", "暖色纸感底（parchment）")
        .replace("纯白背景", "暖色纸感底 #f5f4ed")
        .replace("#ffffff", "#f5f4ed")
        .replace("#dcd9cd", "#e8e6dc")
        .replace("#d8d5c9", "#e5e3d8")
    )


KAMI_CSS = _kami_css(parchment=True)


# 主题注册表
THEMES = {
    "professional": {
        "name": "professional",
        "display_name": "经典商务蓝",
        "description": "左深蓝侧边栏 + 右白主内容区，适合投传统行业/大厂/外企",
        "css": PROFESSIONAL_CSS,
        "preview_color": "#1e3a5f",
        "preview_accent": "#93c5fd",
    },
    "creative": {
        "name": "creative",
        "display_name": "现代创意紫橙",
        "description": "顶部渐变 Header + 卡片式布局，适合设计/互联网/创业公司",
        "css": CREATIVE_CSS,
        "preview_color": "#7c3aed",
        "preview_accent": "#ec4899",
    },
    "minimal": {
        "name": "minimal",
        "display_name": "极简黑白",
        "description": "大量留白 + 细线分隔，适合学术/咨询/金融/法律",
        "css": MINIMAL_CSS,
        "preview_color": "#1a1a1a",
        "preview_accent": "#666666",
    },
    "boss_zhipin": {
        "name": "boss_zhipin",
        "display_name": "BOSS 直聘",
        "description": "单栏流式、ATS 友好、克制商务蓝，适合招聘平台投递",
        "css": BOSS_ZHIPIN_CSS,
        "preview_color": "#1a3d6e",
        "preview_accent": "#6b7280",
    },
    "finance": {
        "name": "finance",
        "display_name": "金融经典",
        "description": "衬线字体、黑白双线、克制正式，适合金融/银行/投行/证券",
        "css": FINANCE_CSS,
        "preview_color": "#1a1a1a",
        "preview_accent": "#444444",
    },
    "linkedin": {
        "name": "linkedin",
        "display_name": "LinkedIn 领英",
        "description": "品牌蓝条 + 蓝色强调 + 标签技能，适合 LinkedIn/海外/外企投递",
        "css": LINKEDIN_CSS,
        "preview_color": "#0a66c2",
        "preview_accent": "#e8f0fe",
    },
    "kami": {
        "name": "kami",
        "display_name": "Kami 暖色",
        "description": "Kami 默认暖色纸感底 + 章节标题品牌色竖线，适合屏幕阅读与个人排版",
        "css": KAMI_CSS,
        "preview_color": "#f5f4ed",
        "preview_accent": "#203b61",
    },
    "kami_white": {
        "name": "kami_white",
        "display_name": "Kami 纯白",
        "description": "Kami 纯白投递版，打印零风险，适合正式投递 PDF",
        "css": KAMI_WHITE_CSS,
        "preview_color": "#ffffff",
        "preview_accent": "#203b61",
    },
}
