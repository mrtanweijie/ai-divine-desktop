# docs 目录索引

> 组织方式：**按类型分子目录**（`plan/` 规划、`design/` 设计、`fix/` 修复、`review/` 复盘、`templates/` HTML 样张），
> 文件名 = `编号-英文名-日期（YYYYMMDD）.md`（无类型前缀，目录即类型）。
> 每个类型目录内独立编号，新增文档时在对应目录按当前最大编号顺延。
> 文件头统一格式：`> 编号：NNN ｜ 类型：xxx ｜ 日期：YYYY-MM-DD ｜ 状态：…`

## 目录

### 规划（plan）

| 编号 | 文档 | 日期 | 状态 |
| --- | --- | --- | --- |
| 001 | [plan-project-blueprint](plan/001-project-blueprint-20260807.md) | 2026-08-07 | 已归档（开发依据基线） |
| 008 | [plan-code-support-roadmap](plan/002-code-support-roadmap-20260830.md) | 2026-08-30 | 已全部实施（P0–P4） |
| 014 | [plan-five-optimizations](plan/003-five-optimizations-20260830.md) | 2026-08-30 | 未实施 |
| 041 | [plan-main-thread-blocking](plan/005-main-thread-blocking-20260917.md) | 2026-09-17 | **待实施（方案待审）** |

### 设计（design）

| 编号 | 文档 | 日期 | 状态 |
| --- | --- | --- | --- |
| 002 | [design-mermaid](design/001-mermaid-20260811.md) | 2026-08-11 | 已实施 |
| 003 | [design-svg-tool](design/002-svg-tool-20260811.md) | 2026-08-11 | 已实施 |
| 004 | [design-subagent](design/003-subagent-20260821.md) | 2026-08-21 | 已实施 |
| 005 | [design-react-loop](design/004-react-loop-20260822.md) | 2026-08-22 | 已实施 |
| 007 | [design-preprocess](design/005-preprocess-20260829.md) | 2026-08-29 | 已实施 |
| 010 | [design-pdf-tool](design/006-pdf-tool-20260830.md) | 2026-08-30 | 未实施（分层增强提案） |
| 011 | [design-ppt-tool](design/007-ppt-tool-20260830.md) | 2026-08-30 | 未实施（分层增强提案） |
| 012 | [design-word-tool](design/008-word-tool-20260830.md) | 2026-08-30 | 未实施（分层增强提案） |
| 015 | [design-incident-recovery-loop](design/009-incident-recovery-loop-20260901.md) | 2026-09-01 | 已实施并验证 |
| 016 | [design-docgen-refactor](design/010-docgen-refactor-20260901.md) | 2026-09-01 | 已实施 |
| 018 | [design-ask-user](design/011-ask-user-20260903.md) | 2026-09-03 | 已实施 |
| 019 | [design-hitl-middleware-migration](design/012-hitl-middleware-migration-20260903.md) | 2026-09-03 | 不排期（评审定稿） |
| 021 | [design-user-steering](design/013-user-steering-20260903.md) | 2026-09-03 | 已实施 |
| 022 | [design-ux-html-baseline](design/014-ux-html-baseline-20260903.md) | 2026-09-03 | 已实施 |
| 023 | [design-agent-progress-observability](design/015-agent-progress-observability-20260904.md) | 2026-09-04 | P0/P2 已实施，P1 已回退 |
| 024 | [design-streaming-performance](design/016-streaming-performance-20260904.md) | 2026-09-04 | 未实施（B1–B6 待实施） |
| 026 | [design-office-edit-closed-loop](design/017-office-edit-closed-loop-20260906.md) | 2026-09-06 | 已实施（期一/二/三） |
| 031 | [design-svg-architecture-routing](design/021-svg-architecture-routing-20260909.md) | 2026-09-09 | 未实施（方案待审） |
| 032 | [design-agent-memory-architecture](design/022-agent-memory-architecture-20260911.md) | 2026-09-11 | 已实施（一至五期，2026-09-12） |
| 035 | [design-pdf-page-template-styles](design/023-pdf-page-template-styles-20260913.md) | 2026-09-13 | **已实施（论文/报告四套页式模板接入 PDF 工具）** |
| 036 | [design-model-effort-slider](design/024-model-effort-slider-20260913.md) | 2026-09-13 | **P1 已实施（滑块直选单面板）** |
| 037 | [design-chat-mention-files](design/025-chat-mention-files-20260913.md) | 2026-09-13 | 未实施（方案待审） |
| 042 | [design-agent-auto-debug](design/026-agent-auto-debug-20260917.md) | 2026-09-17 | **已实施（P1–P3）** |

### 修复（fix）

| 编号 | 文档 | 日期 | 状态 |
| --- | --- | --- | --- |
| 027 | [fix-ppt-empty-slides](fix/001-ppt-empty-slides-20260906.md) | 2026-09-06 | 已实施 |
| 028 | [fix-pdf-module-style](fix/002-pdf-module-style-20260906.md) | 2026-09-06 | 已实施 |
| 038 | [fix-mention-skill-false-positive](fix/003-mention-skill-false-positive-20260914.md) | 2026-09-14 | 已实施（技能集合校验 / 胶囊去前缀 / 浮层单标题 / 文件图标按后缀） |
| 039 | [fix-session-page-collapse](fix/004-session-page-collapse-20260914.md) | 2026-09-14 | 已实施（待重建 sidecar 后在 app 内确认） |
| 040 | [fix-tool-card-stuck-loading](fix/005-tool-card-stuck-loading-20260915.md) | 2026-09-15 | **已实施（工具卡状态收敛 + abort 结算；16 项断言通过）** |

### 复盘（review）

| 编号 | 文档 | 日期 | 状态 |
| --- | --- | --- | --- |
| 006 | [review-agent-optimization](review/001-agent-optimization-20260827.md) | 2026-08-27 | 已归档（优化总结） |
| 009 | [review-project-capabilities](review/002-project-capabilities-20260830.md) | 2026-08-30 | 已归档（已被 025 复核修订） |
| 013 | [review-optimization-feasibility](review/003-optimization-feasibility-20260830.md) | 2026-08-30 | 已归档（仅分析未实施） |
| 017 | [review-project-health](review/004-project-health-20260901.md) | 2026-09-01 | 已归档（历史复盘，由 025 修订） |
| 020 | [review-ui-design-audit](review/005-ui-design-audit-20260903.md) | 2026-09-03 | 已实施 |
| 025 | [review-capabilities-recheck](review/006-capabilities-recheck-20260905.md) | 2026-09-05 | **现行有效（最新能力复盘）** |
| 033 | [review-architecture-analysis](review/007-architecture-analysis-20260912.md) | 2026-09-12 | 已归档（架构与功能分析） |
| 034 | [review-pdf-template-ui-audit](review/008-pdf-template-ui-audit-20260913.md) | 2026-09-13 | **已实施（011–014 模板 UI 优化）** |
| 036 | [review-app-freeze-diagnosis](review/009-app-freeze-diagnosis-20260915.md) | 2026-09-15 | **已实施（Tauri 同步命令 + 逐条目 git 子进程 → 批量 + 异步 + 防抖，实测 23.2×）** |

### 样张（sample），独立编号

| 编号 | 文档 | 日期 |
| --- | --- | --- |
| 001 | [sample-ppt-template-preview](templates/001-ppt-template-preview-20260830.html) | 2026-08-30 |
| 002 | [sample-ux-html-baseline-preview](templates/002-ux-html-baseline-preview-20260903.html) | 2026-09-03 |
| 003 | [sample-obsidian-style](templates/003-obsidian-style-20260904.html) | 2026-09-04 |
| 004 | [sample-portfolio-report](templates/004-portfolio-report-20260904.html) | 2026-09-04 |
| 005 | [sample-mobile-app-ui-spec](templates/005-mobile-app-ui-spec-20260904.html) | 2026-09-04 |
| 006 | [sample-pop-ppt-style](templates/006-pop-style-20260912.html) | 2026-09-12 |
| 007 | [sample-pop-pptx](templates/007-pop-pptx-sample-20260912.pptx) ｜ [预览图](templates/007-pop-pptx-sample-20260912-preview.png) | 2026-09-12 |
| 008 | [sample-travel-swiss](templates/008-travel-template-swiss-20260912.html) ｜ [预览 PDF](templates/008-travel-swiss-preview.pdf) | 2026-09-12 |
| 009 | [sample-travel-bento](templates/009-travel-template-bento-20260912.html) ｜ [预览 PDF](templates/009-travel-bento-preview.pdf) | 2026-09-12 |
| 010 | [sample-travel-aurora](templates/010-travel-template-aurora-20260912.html) ｜ [预览 PDF](templates/010-travel-aurora-preview.pdf) | 2026-09-12 |
| 011 | [sample-academic-report](templates/011-academic-report-template-20260912.html) ｜ [预览 PDF](templates/011-academic-report-preview.pdf) | 2026-09-12 |
| 012 | [sample-thesis-paper](templates/012-thesis-paper-template-20260912.html) ｜ [预览 PDF](templates/012-thesis-paper-preview.pdf) | 2026-09-12 |
| 013 | [sample-data-analysis-report](templates/013-data-analysis-report-template-20260912.html) ｜ [预览 PDF](templates/013-data-analysis-report-preview.pdf) | 2026-09-12 |
| 014 | [sample-research-report](templates/014-research-report-template-20260912.html) ｜ [预览 PDF](templates/014-research-report-preview.pdf) | 2026-09-12 |
| 015 | [sample-launch-keynote](templates/015-launch-keynote-style-20260912.html) | 2026-09-12 |
| 016 | [sample-product-devconf](templates/016-product-intro-devconf-style-20260912.html) | 2026-09-12 |
| 017 | [sample-quotes-sketch](templates/017-quotes-sketch-20260917.html) ｜ [预览 PDF](templates/017-quotes-sketch-preview.pdf) | 2026-09-17 |
| 018 | [sample-quotes-sketch-page](templates/018-quotes-sketch-page-20260917.html) ｜ [预览 PDF](templates/018-quotes-sketch-page-preview.pdf) | 2026-09-17 |

## 附属目录

- `templates/`：HTML / PPT 视觉样张（独立编号 001–018，含预览 PDF）
  - 011–014 四套（学术报告 / 论文投稿 / 数据分析报告 / 研究报告）与 018（金句手绘解读）
    已作为**页式模板**接入 PDF 工具，
    运行时副本在 `divine-server/app/docgen/pdf/pdf_themes/{academic_report,thesis_paper,data_report,research_report,quotes_sketch}.html`，
    详见 [design 023](design/023-pdf-page-template-styles-20260913.md)（018 为 2026-09-17 追加的第五套）。
    改样张后需同步复制到 `pdf_themes/`，
    由 `divine-server/tests/test_pdf_page_templates.py::test_doc_sample_matches_runtime_copy` 强制校验两者一致。
  - 015–016 是 PPT 主题（keynote / devconf）的视觉样张，主题已实现在
    `divine-server/app/docgen/ppt/renderer/themes.py`，**样张不参与运行时渲染**；
    其占位符采用「整句包裹 + 内层插槽」的嵌套写法，与 011–014 的扁平约定不同——
    这是历史写法（当前括号平衡），若日后接入会做占位符替换的管线，须先扁平化。
  - 017 是「金句手绘解读」的**网页阅读版**样张（宋体 + 纸感米白 + 细描边卡片），
    未接入管线，与运行时副本**有意不同**（故不进 `_DOC_TO_RUNTIME`）。
    它把配图做成**可选插槽**：`.card--art` 有配图走 `.frame`，
    `.card--text` 无配图则放大金句并用引号饰件撑住版面，不留空框。
    同一份文件兼顾网页阅读与 A4 导出（`@page` + `@media print`，整页垂直居中、
    一卡一页）；预览 PDF 即由该文件直接渲染。
    **它是纯骨架**：12 个通用占位符（`{{主标题}}` / `{{金句原文}}` / `{{解读}}` 等），
    不含任何具体人名、事件或案例内容；各槽位的建议字数写在文件开头的 HTML 注释里。
    注意这与 011–014 的做法不同——那四套的占位符内文是仿真内容（如
    `{{基于深度学习的图像识别方法研究}}`），本样张按要求保持通用。
  - 018 是 017 的**分页运行时版**（PDF 管线消费的那一份）：结构改成
    `<div class="page cover">` + 6 张 `<div class="page">` 金句卡 + `<div class="page end">`，
    共 8 页；PDF-first（无 `@media print` 分支，`@page` 直接铺纸色）。
    配图插槽落为虚线「图位」`.plate`——**页式模板管线的图片内嵌只对 travel 生效**，
    非 travel 模板里放 `<img>` 会被 WeasyPrint 直连外网、失败即白块，
    因此不放真图（`test_quotes_sketch_has_no_img_tag` 锁住该约束）；
    接入真实插图时把 `.plate` 换成 `<img>` 即可，其余版式不变。
    同一套视觉在 **HTML 工具**侧以 `ux_html.py` 的 `Quotes` 风格基座提供
    （纸感 token + `--font-body` 切中文衬线），两条路径共用同一套色值。
  - 占位符卫生由 `tests/test_pdf_page_templates.py` 强制校验：括号平衡 + 无四重括号（011–018），
    且 011–014 与 018 禁止嵌套（`test_sample_placeholders_balanced` / `test_pdf_sample_placeholders_are_flat`）。
- `assets/`：文档引用的图片资源
- `pdf-modules/`：PDF 模块 JSON/CSS/HTML 资源（由 docgen 管线引用）
