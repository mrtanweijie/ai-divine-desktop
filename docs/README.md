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
| 032 | [design-agent-memory-architecture](design/022-agent-memory-architecture-20260911.md) | 2026-09-11 | 未实施（方案待审） |

### 修复（fix）

| 编号 | 文档 | 日期 | 状态 |
| --- | --- | --- | --- |
| 027 | [fix-ppt-empty-slides](fix/001-ppt-empty-slides-20260906.md) | 2026-09-06 | 已实施 |
| 028 | [fix-pdf-module-style](fix/002-pdf-module-style-20260906.md) | 2026-09-06 | 已实施 |

### 复盘（review）

| 编号 | 文档 | 日期 | 状态 |
| --- | --- | --- | --- |
| 006 | [review-agent-optimization](review/001-agent-optimization-20260827.md) | 2026-08-27 | 已归档（优化总结） |
| 009 | [review-project-capabilities](review/002-project-capabilities-20260830.md) | 2026-08-30 | 已归档（已被 025 复核修订） |
| 013 | [review-optimization-feasibility](review/003-optimization-feasibility-20260830.md) | 2026-08-30 | 已归档（仅分析未实施） |
| 017 | [review-project-health](review/004-project-health-20260901.md) | 2026-09-01 | 已归档（历史复盘，由 025 修订） |
| 020 | [review-ui-design-audit](review/005-ui-design-audit-20260903.md) | 2026-09-03 | 已实施 |
| 025 | [review-capabilities-recheck](review/006-capabilities-recheck-20260905.md) | 2026-09-05 | **现行有效（最新复盘）** |

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

## 附属目录

- `templates/`：HTML / PPT 视觉样张（独立编号 001–007）
- `assets/`：文档引用的图片资源
- `pdf-modules/`：PDF 模块 JSON/CSS/HTML 资源（由 docgen 管线引用）
