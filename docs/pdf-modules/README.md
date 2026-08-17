# PDF 布局模块库

10 个布局模块 + 目录（TOC）× 11 主题的模块设计资产，全部基于同一套 design tokens
（语义 CSS 变量），模块样式与主题解耦，可独立复用。

## 文件说明

| 文件 | 内容 | 用途 |
| --- | --- | --- |
| `modules.css` | Design tokens + 11 主题变量 + 10 个模块样式 + TOC 样式（含 print 规则 `page-break-inside: avoid`） | 追加进任意 PDF 主题 CSS 即可获得全部模块能力 |
| `modules.html` | 10 个模块 + TOC 的干净 HTML 骨架示例（含 emphasis 变体） | Agent 生成参考 / 浏览器预览 / 渲染验证 |
| `modules.json` | 每个模块的结构化规范（字段、emphasis 变体、适用场景） | Agent 直接读取生成结构化数据 |

## 模块一览

| # | 模块 | 关键类名 | emphasis 变体 | 适用 |
| --- | --- | --- | --- | --- |
| ① | Hero Stat 大数字 | `.hero-stat .stat-grid .stat-value` | high/medium/low | 核心指标、资源需求 |
| ② | Pull Quote 金句 | `.pull-quote blockquote .quote-mark` | high/medium/low | 开篇破题、收尾 |
| ③ | Two Col Compare 对比 | `.compare-panel.before/.after` | — | 改版/方案对比 |
| ④ | Timeline 时间线 | `.timeline-node .timeline-dot` | — | 里程碑、路线图 |
| ⑤ | Feature Grid 特性 | `.feature-item` | — | 平台能力、亮点 |
| ⑥ | Callout Box 提示 | `.callout-box.info/warning/success/error` | — | 注意、风险、完成 |
| ⑦ | Metric Row 进度条 | `.metric-bar .metric-fill` | — | KPI 完成度 |
| ⑧ | Bio Card 人物 | `.bio-avatar .bio-name` | — | 作者、团队 |
| ⑨ | Tag Cloud 标签 | `.tag.hl` | — | 技能、关键词 |
| ⑩ | Conclusion Box 总结 | `.conclusion-box .action-item` | high/medium/low | 收尾、CTA |
| ⑪ | TOC 目录 | `.toc-item .num + a.title` | — | 目录页（页码 target-counter 自动生成） |

## 主题（11 个）

`tech` / `corporate` / `editorial` / `bold` / `minimal` / `forest` / `sunset` /
`lavender` / `mono` / `ocean` / `terminal`

切换方式：`<html data-theme="tech">`，或对容器元素设置 `data-theme` 属性。
暗色主题（bold/terminal）通过反转背景变量实现；衬线（editorial/mono）与
等宽（terminal）主题通过覆盖 `--font-sans` 实现。

## 与 divine-server 的关系

- 你现有的 11 个主题（universal/notion/linear/apple/modern/academic/minimal/...）
  已用同一套 `--primary/--bg-surface/--border` 变量体系，**本模块 CSS 可直接追加**。
- 落地路径：markdown 约定 → 模块 HTML（如 `> [!quote]` → pull-quote、
  `| A | B |` 表格已支持、`📊 2.4M` 类前缀 → hero-stat），渲染管线在
  `app/pdf_renderer/`。
- `modules.json` 可像 `travel_template_skeleton` 一样嵌入 Agent prompt，
  让 Agent 按模块结构输出数据。
