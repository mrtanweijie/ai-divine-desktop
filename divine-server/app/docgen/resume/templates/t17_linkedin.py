"""模板 17 · LinkedIn 领英（自旧 linkedin 主题迁入）— 品牌蓝条 + 标签式技能"""

from __future__ import annotations

from .flat_layout import flat_resume_html

id = "linkedin"

CSS = r'''
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
  /* LinkedIn 品牌条四边全出血：负 margin 突破 @page 的 12mm 顶距与 14mm 左右距，
     蓝条贴满纸张边缘（正文内容区保持 14mm 间距不受影响） */
  margin: -12mm -14mm 3.5mm -14mm;
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
  break-after: avoid;
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

/* "分类|内容" 技能行：逐行「分类：内容」 */
.skill-row {
  font-size: 9pt;
  color: #2c2c2c;
  line-height: 1.65;
  margin-bottom: 1.2mm;
}

.skill-row b {
  color: #0a66c2;
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
'''

PRINT_SINGLE = ""

# multi 模式通用 @page margin 左右为 0，但本模板 HTML 没有 .page 外层容器做内部 padding 兜底，
# 直接用 0 margin 会让正文贴满物理页面边。补回 14mm 横向 + 12mm 顶/11mm 底，与单页版一致；
# 同时覆盖 @page:first{margin-top:0}（通用多页块会取消首页顶距），否则 .topbar 的
# margin-top:-12mm 会把蓝条推出纸面被裁掉。
MULTI_EXTRA = """
@media print{
  @page{size:A4;margin:12mm 14mm 12mm 14mm}
  @page:first{margin-top:12mm}
}
"""

def render(r) -> str:
    return flat_resume_html(r, style="linkedin")
