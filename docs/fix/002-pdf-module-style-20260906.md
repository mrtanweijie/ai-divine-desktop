# PDF 样式修复方案（模块内容 `**` 未加粗 / hero-stat 横条右溢 / compare·feature 卡片溢出）

> 编号：002 ｜ 类型：fix ｜ 日期：2026-09-06 ｜ 状态：已实施
> 取证：用户提供的 6 张截图对应产物（`基于理想汽车2026年上半年销量数据的分析报告.pdf`、`Cantus_编程模型横向对比报告.pdf` 等）+ 真实管线复现实验（WeasyPrint 66.0）
> 关联：[001-ppt-empty-slides-20260906.md](001-ppt-empty-slides-20260906.md)（同轮发现的姊妹问题，修复约定互相适用）


## 1. 现象与归属模块

| 截图现象 | 归属模块 | 渲染路径 |
| --- | --- | --- |
| 执行摘要 KPI 横条第 4 项 `30,468辆` 被页缘截断 | `hero-stat`（蓝色 data-emphasis=high 横条） | `markdown.py:147-171` → `modules.css:110-146` |
| 5.2 建议 AFTER 面板最后一条要点画出面板底边 | `compare`（BEFORE/AFTER 双栏） | `markdown.py:172-190` → `modules.css:211-251` |
| 核心能力总览 4 张卡片描述文字溢出卡片底边；卡片标题"智能对话"被拆成"智能对/话" | `features`（feature-grid） | `markdown.py:212-230` → `modules.css:313-326` |
| "选型判断"蓝框 / "核心判断"绿框里 `**加粗**` 显示为字面星号 | callout（`[!conclusion]`/`[!success]` 等 alert 块） | `markdown.py:83-130` |
| 月份/同比数据被硬套成 BEFORE=月份、AFTER=百分比的"对比" | `compare` 语义误用 | 模型侧问题（§4.4） |

## 2. 根因（均已在真实管线复现或代码确诊）

### 2.1 `**` 未加粗：模块内容只做 HTML escape，无 inline markdown 解析（100% 确诊）

正文段落走 python-markdown 库，`**bold**` 正常；但**所有模块**的内容是手工 `html_lib.escape()` 拼接 HTML，星号原样保留：

- alert/callout 正文：`markdown.py:88` `text = " ".join(esc(line) for line in body)`
- conclusion：`markdown.py:114`；bio：`markdown.py:127`
- compare 列表项：`markdown.py:177-179`；hero-stat/metrics/timeline/features 各分支同理

模型在 callout/对比卡里写 `**加粗**` 是高频自然行为（本次两份报告都有），全部字面输出。

### 2.2 hero-stat 横条右溢：`nowrap` + `1fr` 最小内容宽度下限，不换行不缩字（机制确诊）

三层机制叠加：

1. 渲染器设计为单行数据带：`cols = max(2, min(len(items), 4))`（`markdown.py:167`），4 项 → `grid-4`，**CSS grid 在项数 ≤ 列数时永远单行**，不存在自动换行；
2. `.stat-value { white-space: nowrap }`（`modules.css:142`，为防"12 项"空格断行错位）；
3. `grid-template-columns: repeat(4, 1fr)` 的 `1fr` 实际是 `minmax(auto, 1fr)`——**轨道不能收缩到内容最小宽度以下**。`196,272辆` 36px 粗体 nowrap 的 min-content ≈ 全文宽，四项 min-content + 3×24px gap 超过版心宽度时，grid 既不换行也不缩字，整体右溢被页缘裁掉。

### 2.3 compare / feature 卡片内容溢出：WeasyPrint 66 grid 行高低估约一行（已复现，非分页问题）

复现实验（真实管线 `render_markdown_to_pdf` + 真实 modules.css + marked-table 语法）：

| 实验 | 结果 |
| --- | --- |
| 模块置于页中（前置 300 句把模块推后） | AFTER 面板矩形底边 y=327，溢出文本墨迹底 y=336，**溢出 9pt** |
| 同一内容置于页首（无任何分页压力） | 面板底 y=403 vs 文本底 y=412，**同样溢出 9pt** |
| 最小复现（手写 HTML，不用 modules.css） | 不溢出，行高正常随内容增长 |

结论：**与分页/断页无关**，是 WeasyPrint 66 的 grid 行高计算在真实 CSS 组合（`line-height:1.7` 的 li + `padding:24px` 面板 + `align-items:stretch` + 中间 48px 分隔列）下系统性低估约一行，最后一行墨迹画出面板底边。`features` 卡片同机制（desc 行数多时溢出）。`.module` 已有 `page-break-inside: avoid`（`modules.css:98`），但解决不了"单页内行高不足"。

### 2.4 compare 语义误用：prompt 约定缺口

截图 2 中模型把"月份|同比"时间序列硬套 compare（BEFORE=2月-7月、AFTER=▼12.1%…），左右并无对比关系。marked-table 语法只约定了"两列表格 + `{: .compare}`"，没有说清**什么数据不该用 compare**。

## 3. 修复方案

### 3.1 P0-1：模块内容统一过 inline markdown（修 `**`）

`markdown.py` 新增共享函数 `_inline_md(text: str) -> str`（先 `esc` 再替换，保证安全）：

```python
def _inline_md(text: str) -> str:
    """escape 后解析行内 markdown：**粗**、*斜*、`码`、[文](链)。"""
    t = html_lib.escape(text or "")
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    return t
```

替换所有模块内容拼接点的 `esc(...)`（callout 正文/标题、conclusion、bio、compare 列表、hero-stat label/trend、timeline、features、metrics、tags）。裸 URL 与无标记文本不受影响；`**` 不配对时保持字面（容错）。

### 3.2 P0-2：hero-stat 防溢出——`minmax(0,1fr)` 基础加固 + 自适应降列（采纳"一行两卡"方案）

**CSS 基础加固**（`modules.css`）：

```css
.grid-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.grid-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.grid-4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.grid-4 .stat-value { font-size: clamp(22px, 2.6vw, 36px); } /* WeasyPrint 不支持 vw，实现时改为渲染端字号分档 */
```

**渲染端自适应**（`markdown.py` hero-stat 分支，对齐 PPT 侧 `pick_size` 先例）：

1. 估算 4 项 value 的像素宽（字符数 × 字号系数），总宽 + gaps > 版心可用宽时：
   - 首选**字号降档**（36 → 30 → 26px）仍放得下则保持单行；
   - 降两档仍放不下 → **降为 2×2**：`cols=2` 时 4 项经 grid 自动换行排两行（`repeat(2, minmax(0,1fr))` 天然换行），即用户建议的"一行两个卡片"；单行数据带变两行数据带，高度代价可接受（KPI 本就是页面重点）；
2. `nowrap` 保留（防"12 项"错位断行），配合 `minmax(0,1fr)` 后轨道可收缩，极端长值由降列兜底。

### 3.3 P0-3：compare / features 模块布局从 grid 换 table（绕开 WeasyPrint grid 行高缺陷）

WeasyPrint 对 **table 布局的支持远比 grid 成熟**（正文 markdown 表格已大量使用、无行高问题）：行高随内容增长、等高列（`table-cell` 天然 stretch）、跨页行为可控都是表格的基石行为。

- `.compare-grid` → `display: table; width:100%`，左/右面板 → `display: table-cell`（等高自动成立），中间 VS 分隔列 → 48px 固定宽 `table-cell`；
- `.feature-grid-container.cols-N` → `table` + 固定布局：`table-layout: fixed` + N 个等宽 `table-cell`（行数由渲染端按项数分行：每行 N 项，超出自动下一行——同时解决 4 项以上不换行问题）；
- `stat-grid` 若 P0-2 后仍有残余场景可一并换 table（render 端按行分组输出 `<tr>`）；
- 视觉不变：面板背景/圆角/内边距全部作用在 `table-cell` 内的 `div` 上（WeasyPrint 对 table-cell 的 border-radius 支持有限，圆角需包一层内层 div——实现时以复现用例回归视觉效果）；
- 保留复现 PDF 作为回归 fixture（§5），防止换布局引入新视觉回归。

### 3.4 P1：compare 语义防误用（prompt + 渲染端双保险）

- `prompt_sections.py` 模块约定段补一句："compare 仅用于方案/对象/路径对比（双方互斥）；时间序列、单指标多期数据用普通 table 或 timeline，禁止把'月份|同比'类数据拆成 Before/After"；
- 渲染端兜底（可选）：compare 行数两侧不平衡 > 2 倍或任一侧单元格全部无中文/无实词时，降级渲染为普通表格并记 warning——先不做，观察 prompt 修正效果。

### 3.5 P2：qa.py 补模块体检

`docgen/pdf/renderer/qa.py` 增加两条检查（沿用 PDF 管线既有 QA 习惯）：

- 渲染后用 pymupdf 抽取"文本墨迹是否超出所在页版心右缘/页面底缘"（KPI 溢出类）；
- callout/comparison 模块文本含字面 `**` 时记 warning（回归 3.1 的防线）。

## 4. 测试计划

| 测试 | 内容 |
| --- | --- |
| `tests/test_pdf_module_inline.py` | `_inline_md`：`**粗**`/嵌套标点/不配对 `**`/已含 HTML 字符的转义安全 |
| `tests/test_pdf_hero_stat_fit.py` | 长值 4 项 → 字号降档或 2×2 降列判定；短值 4 项保持单行 |
| `tests/test_pdf_module_overflow.py`（关键回归） | 本方案 §2.3 的两个复现输入固化为 fixture，断言：面板矩形底边 ≥ 文本墨迹底边（pymupdf 几何断言）；换 table 布局后同样通过 |
| `tests/test_pdf_qa_modules.py` | qa 对字面 `**` 与越界墨迹的告警 |

## 5. 影响面

- `markdown.py` 模块渲染函数是改动主区，**python-markdown 正文链路不动**；
- `modules.css` 改 grid → table 仅影响 6 个 marked-table 模块的内部布局，模块外边距/页内位置不变；
- PPT 侧 `layouts.py` 自绘实现与 PDF 无共享代码，互不影响；本次"归一化层 + 自适应字号 + 渲染后自检"的修法约定与 [PPT空页修复方案](001-ppt-empty-slides-20260906.md) §8 一致。

## 6. 分期与工作量

| 期 | 内容 | 工作量 |
| --- | --- | --- |
| 一（P0） | `_inline_md` 全模块接入 + hero-stat 自适应（含 2×2 降列）+ compare/features 换 table 布局 + 复现 fixture 回归 | 2–3 天 |
| 二（P1） | prompt compare 语义约定 + 观察误用率 | 0.5 天 |
| 三（P2） | qa.py 模块体检两条 | 0.5 天 |
