# Divine 前端 UI 审计报告：配色 / 间距 / 圆角

> 编号：005 ｜ 类型：review ｜ 日期：2026-09-03 ｜ 状态：已实施
> 结论先行，逐条附证据（文件:行号）。**本报告只审计，不改代码**，改造方案见 §5，待你审核后我再动手。


## ✅ 执行状态（2026-09-03，已按你确认的决策落地，未提交）

三个决策点结论：**维持黑白极简（不引入品牌色）· K 线改回 A 股涨红跌绿 · 输入框统一 40px**。

已执行（低风险包，改完已过 `tsc -b` + `vite build`）：

| 项 | 内容 | 涉及 |
|----|------|------|
| P0 语义色修复 | dark `--color-success: #34d399`、`--color-warning: #fbbf24`（原灰白） | `styles/index.less` |
| K 线涨跌色 | `upColor` 红 `#ec0000` / `downColor` 绿 `#00da3c`（A 股惯例） | `chartOptions.ts:988` |
| 圆角值收敛 | `7→6px`、`9/10→8px`、`5/3→4px`、`10px 10px 0 0→8px 8px 0 0`；保留 50%/999px/24px/16px 顶栏/气泡尾角/2px 装饰 | 全仓 `.less`（26 文件） |
| 输入框高度 | `.field input/select` 34→40px | `styles/index.less` |

收敛结果：圆角从 **20+ 种取值 → 规则档 4/6/8/12px + 少量特征值**（50% 圆形 / 999px 胶囊 / 24px composer / 16px 窗口顶栏 / 气泡尾角混合值）。

### 第二轮（Phase 3 保守版 + Phase 4 部分，2026-09-03 已执行，未提交）

| 项 | 内容 | 涉及 |
|----|------|------|
| 间距单值噪声归并 | `padding/gap/margin` 单值 `5→4px`、`7→8px`、`9→8px` 共 31 处（±1px 手调值，归并到邻近档） | 全仓 `.less` |
| 状态色 token 化 | 新增 `--status-green/red/blue/orange/amber/violet`（dark 用 400 亮档、light 用 600-700 深档，浅色下状态点/文字对比度达标）；替换 Tag/Toast/McpSection/skills/tasks/GitInfoCard/FilePreviewPanel 里 20 处重复 tailwind hex 为 `var(--status-*)` | `styles/index.less` + 7 组件 |
| 图表色单源化 | 新建 `src/styles/uiPalette.ts`（与 `index.less` token 对齐的 JS 基色），Chart 与 Mermaid 的 text/surface 主色改引共享常量；Chart 轴文字 `#e8ecf1→#f2f4f6` 对齐正文 token | `uiPalette.ts`(新) + `chartOptions.ts` + `MermaidBlock.tsx` |

第二轮验证：`tsc -b` ✅ + `vite build` ✅。

### 第三轮（圆角 token 化，2026-09-03 已执行，未提交）

圆角值虽已收敛到 4/6/8/12 档，但仍是字面量写死。本轮建立 **`--radius-*` token 并全仓引用**（主题无关，放独立 `:root` 块）：

```css
:root {
  --radius-xs: 4px;   --radius-sm: 6px;   --radius-md: 8px;
  --radius-lg: 12px;  --radius-xl: 16px;  --radius-full: 999px;
}
```

替换结果：179 处圆角中 **155 处已改为 `var(--radius-*)`**（视觉零变化，变量值=收敛后值）。混合值同步 token 化：窗口顶栏 `var(--radius-xl) var(--radius-xl) 0 0`、气泡尾角 `var(--radius-md) var(--radius-md) 2px var(--radius-md)`、浮层顶角 `var(--radius-md) var(--radius-md) 0 0`、附件标签 14px → `var(--radius-full)`。

**保留的字面量（有意为之）**：`50%`×16（圆形——对非正方形容器比 999px 安全）、`2px`×3 装饰、`0`×2 直角/覆盖、composer `24px`（超大圆角容器，无 token 档）、SessionList `0 2px 2px 0` 特征尾角。`chartOptions.ts` 等 JS 内无残留。验证：`vite build` ✅。

**审计结论修正（诚实勘误）**：§2 P1-4"`#ffffff` 浅色假设导致深色下突兀发白"**严重度被高估**——逐文件复核后，绝大多数 `#ffffff` 位于 `:root[data-theme="light"]` 特判块内，或属功能性白色（开关滑块/勾选/PDF iframe 白底/danger 按钮文字）。深色主题实际无此可见 bug，该项降级为维护性问题（归入 light 补丁拆分项）。

**仍未执行（待你决定）**：
- 复合值间距（`padding: 7px 9px` 等多值声明约 20 处，需逐处语义判断）
- `MessageItem/index.less` 内部红绿状态色（code diff / 工具结果语境复杂，需单独处理）
- 拆 `:root[data-theme="light"]` 补丁、`MessageItem` 外其余组件中零散状态 hex、`NewChatGuide` 演示 chips（装饰性，有意保留独立色）

---

## 0. 结论速览

| 维度 | 严重度 | 一句话结论 |
|------|--------|-----------|
| 配色 | 🔴 P0 | 深色主题 `success`/`warning` 两个语义色被写成了**灰白色**，语义丢失（疑似复制粘贴 bug） |
| 配色 | 🟠 P1 | 无品牌色；大量硬编码 hex（60+ 处）与 `#ffffff`（20 处）散落组件，脱离 token |
| 配色 | 🟠 P1 | 图表主题色在 `index.less` / `MermaidBlock.tsx` / `chartOptions.ts` **三处重复维护**，极易漂移 |
| 间距 | 🟠 P1 | **无 spacing token**；gap 覆盖 2–18px 几乎每个整数，padding 1–48px 全谱系 |
| 圆角 | 🔴 P0 | 179 处、20+ 种取值，`6px/7px/8px` 三值并存（105 处），同类元素圆角互不一致 |

核心根因只有一句话：**设计 token 层缺失，样式靠"看着调"的硬编码堆叠**。深色/浅色主题不是两套对等的设计系统，而是"先写 dark，再为 light 打补丁"。

---

## 1. 扫描范围与方法

- 主题入口：`src/styles/index.less`（CSS 变量 + 全局组件类）
- 主题逻辑：`src/services/theme.ts`（`data-theme="dark" | "light"`）
- 组件样式：`src/components/**`、`src/pages/**` 下全部 `.less`
- 统计口径：正则抽取 `border-radius` / `gap` / `padding` / hex 色值并聚合频次

---

## 2. 配色问题

### 🔴 P0-1 深色主题语义色被写成灰白色

`src/styles/index.less:15-17`（dark 分支）：

```css
--color-success: #e5e7eb;   /* 这是灰白，不是绿 */
--color-warning: #cbd5e1;   /* 这是灰白，不是橙 */
```

对照 `index.less:42-44`（light 分支）却是正确的：

```css
--color-success: #16a34a;   /* 绿 */
--color-warning: #b45309;   /* 橙 */
```

**影响**：深色主题下所有 success / warning 语义元素（成功提示、告警 tag、状态点）都会渲染成灰白色，用户无法区分"成功/警告/普通"。这是本次审计唯一需要**优先修复**的硬 bug。

### 🟠 P1-2 无品牌色，accent 是纯黑白

`index.less:11-13`（dark）与 `39-41`（light）：

```
dark:  --color-accent: #ffffff（纯白）
light: --color-accent: #111827（近黑）
```

主按钮 `ui-button--primary`、`primary-button` 直接吃 `--color-accent` 做背景，深色下就是一块纯白按钮、浅色下纯黑按钮。整体 UI 是"黑白灰 + 零品牌记忆点"，缺少一个可识别的品牌强调色（对比 Linear 的紫、Notion 的无衬线黑 + 高亮蓝）。**是否引入品牌色需你拍板**（见 §6 建议）。

### 🟠 P1-3 硬编码 hex 大量散落（≈60+ 处，脱离 token）

代表性位置（`grep #[0-9a-f]{3,8}` 命中的业务色）：

| 文件 | 硬编码值 | 用途 |
|------|---------|------|
| `pages/skills/index.less` | `#93c5fd` `#4ade80` `#fb923c` | 技能分类色 |
| `pages/tasks/index.less` | `#4ade80` `#a78bfa` `#fb923c` `#facc15` `#f87171` | 任务状态色 |
| `components/ui/Tag/index.less` | `#22c55e` `#4ade80` `#d97706` | 标签语义色 |
| `components/ui/Toast/index.less` | `#4ade80` `#60a5fa` | 提示图标色 |
| `components/SettingsModal/McpSection.less` | `#22c55e` `#ef4444` `#9ca3af` `#d1d5db` | MCP 状态点 |
| `components/MessageItem/index.less` | `#cbd5e1` `#94a3b8` `#ef4444` `#22c55e` 等 10+ | 消息内联状态 |

这些"分类/状态色"没有进入 `:root` token，深浅主题下**对比度不保证**，且同一语义（如"成功/绿"）在不同文件里用了 `#22c55e` 与 `#4ade80` 两个不同值。

### 🟠 P1-4 `#ffffff` 硬编码（浅色主题假设）

20 处组件直接写死白底/白字，深色主题下会**突兀发白**：

- `components/ui/Input/index.less:64`（`light .ui-input:focus` 用 `#ffffff`，勉强可接受）
- `components/ui/Select/index.less`、`Dropdown/index.less`、`TextArea/index.less`：`background: #ffffff` / `#eef1f4` / `#e2e8f0`
- `pages/chat/components/ChatHeader/index.less`、`ModelEffortControl.less`、`ProjectPicker/index.less`
- `components/ui/Toast/index.less`、`Button/index.less:69`（danger 文字 `#ffffff`）

这些值本应由 `--color-surface` 等 token 承载，硬编码导致主题切换时无法联动。

### 🟠 P1-5 图表主题色三处重复维护

| 位置 | 内容 |
|------|------|
| `styles/index.less` | `--color-*` CSS 变量 |
| `MarkdownView/MermaidBlock.tsx` | 手写 dark/light 两套 `primaryColor/textColor/lineColor/...` |
| `ChartBlock/chartOptions.ts` | 手写 `ChartPalette`（`text/muted/border/...`）两套 |

三套值有对齐但靠人工同步，一旦改 token，图表/流程图不会跟着变。Mermaid 的 `#171b1f`/`#121517`/`#0d1013` 与 `--color-surface` 体系其实是同一批色，却各写一份。

### 🟡 P2-6 主题管理是"补丁式"

`styles/index.less:532-573` 出现一大段 `:root[data-theme="light"]` 特判，对 `session-sidebar / titlebar / chat-header / user-content / composer / minimap-preview` 逐个覆盖：

```css
:root[data-theme="light"] .session-sidebar,
:root[data-theme="light"] .titlebar,
:root[data-theme="light"] .chat-header {
  background: rgba(255, 255, 255, 0.78);
  backdrop-filter: blur(18px) saturate(140%);
}
```

这说明组件本身写死了 dark 逻辑，浅色主题靠"事后打补丁"纠正。正确的做法是这些透明毛玻璃态也走 token，两套主题各声明一次，而非"dark 打底 + light 例外"。

### 🟡 P2-7 K 线涨跌色与国际惯例相悖（待确认）

`ChartBlock/chartOptions.ts:988-989`：

```ts
const upColor = "#00da3c";   // 涨 = 绿
const downColor = "#ec0000"; // 跌 = 红
```

这是美股"涨绿跌红"。若面向 A 股用户，习惯是**涨红跌绿**。**需你确认是否有意为之**。

### 🟡 P2-8 focus 态三套并存

- `ui-button` / `field input` 用 `box-shadow: var(--focus-ring)`（2px 光晕）
- `ui-input:focus` 只改 `border-color` + `background`（无光晕，且 dark/light 背景变化方向相反）
- 全局 `*:focus-visible` 用 `outline: 2px solid`

三种聚焦反馈并存，键盘导航时视觉不统一。

---

## 3. 间距问题

### 🟠 P1-9 无 spacing token，值谱系全面铺开

`index.less` 里**一个 `--space-*` 变量都没有**，全部硬编码。统计 gap 出现过的值：

```
2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 16, 18   （px）
```

padding 出现过的值：

```
1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 16, 18, 20, 22, 24, 28, 40, 48
```

**典型"看着调"的证据**：`7px`、`9px`、`13px` 这类非 4 倍数与 `8px`、`10px`、`12px` 并存，肉眼几乎无差却各写各的。例如 `MessageItem/index.less` 里同时存在 `padding: 7px 9px`、`padding: 6px 9px`、`padding: 7px 12px`、`padding: 8px 12px` 四档近似值。

### 🟡 P2-10 同类控件高度不统一

| 控件 | 高度 |
|------|------|
| `.icon-button` | 32px |
| `.ui-button--medium` | 32px |
| `.ui-button--icon.medium` | 30px |
| `.field input/select` | 34px |
| `.ui-input` | 40px |
| `.ui-button--small` | 28px |

按钮与输入框在 28 / 30 / 32 / 34 / 40 之间横跳，同一行内混排时基线、视觉重心不齐。

---

## 4. 圆角问题

### 🔴 P0-11 圆角值严重碎片化（179 处 / 20+ 种取值）

频次统计：

```
6px × 52      8px × 39      50% × 16      7px × 14
5px × 11      999px × 9     10px × 9      4px × 6
12px × 6      9px × 3       2px × 3       3px × 2
0 × 2
混合值：24px、14px、16px 16px 0 0、10px 10px 0 0、8px 8px 2px 8px、0 2px 2px 0
```

最致命的是 **`6px` / `7px` / `8px` 三值并存共 105 处**——这三个值人眼几乎无法区分，却遍布全项目，是"逐处手调、无规则"的明确信号。`7px` 这种像素级微调（14 处）在任何设计系统里都不该出现。

### 🟡 P2-12 同类元素圆角不一致

| 元素 | 出现的圆角 |
|------|-----------|
| 按钮 | 7px（ui-button）、6px（icon-button / ui-button--icon / primary-button） |
| 输入框 | 7px（ui-input）、6px（field input） |
| 弹窗 | 8px（modal / confirm-dialog）、10px（ui-modal）、9px（settings-modal） |
| 下拉 | 8px（dropdown-menu）、6px（dropdown item） |

同一语义（"按钮"）在不同文件里取不同圆角，是"无 radius token + 组件各自为政"的直接后果。

---

## 5. 改造方案（分阶段，待审核）

> 原则：**先建 token、后收敛值；先修 bug、后动全局；每阶段可独立提交、可独立回滚。**

### Phase 0 — 制定 token 规范（本报告 §6 给出一套可落地的建议值）

在 `styles/index.less` 顶部补齐三类 token，dark/light 各声明一份：

1. **颜色**：修正 `success/warning`；补齐 `info`；统一 danger 到一个 ramp；可选引入品牌色。
2. **间距**：`--space-0…--space-12`，4px 基准。
3. **圆角**：`--radius-xs/sm/md/lg/xl/full` 六级。

### Phase 1 — 修 bug + 建 token（低风险，先行）

- 修 dark 分支 `success/warning` 灰白 bug（**一行改动，收益最大**）。
- 新增 `--radius-*`、`--space-*` token 到 `:root`，但**暂不改任何组件**（纯新增，零回归）。
- 若确认引入品牌色，补 `--color-accent-brand` 并让 primary 按钮可选切换。

### Phase 2 — 圆角收敛（机械化替换，可脚本化）

按映射规则全局替换：

| 现值 | 归到 |
|------|------|
| 7px | 6px（按钮/输入框） |
| 5px | 4px（小元素）或 6px |
| 9px / 10px | 8px（弹窗/下拉） |
| 10px | 12px（大卡片） |
| 14px | 12px 或 16px |

目标：把 20+ 种收敛到 6 种（`4/6/8/12/16/full`）。

### Phase 3 — 间距收敛

按 4px 基准归并 gap/padding，重点清理 `7/9/13` 等非 4 倍数与"6/7/8 近似档"。同时统一控件高度（按钮 32px、输入框 36px 或 40px，二选一）。

### Phase 4 — 颜色收敛（风险最高，放最后）

- 去 `#ffffff` / 硬编码 hex → 全部映射到 token。
- 拆掉 `:root[data-theme="light"]` 补丁，把毛玻璃态改写成 token 驱动。
- 统一 Mermaid / Chart 两套色到 token（或从 token 派生）。
- 确认涨跌色是否要改回"涨红跌绿"。

---

## 6. 建议 token 值（供拍板）

### 颜色（补充/修正项）

```css
/* dark */
--color-success: #34d399;   /* 修正：emerald 400 */
--color-warning: #fbbf24;   /* 修正：amber 400 */
--color-danger:  #f87171;   /* 统一到 red 400（现值 #f47b6e 偏珊瑚橙） */
--color-info:    #60a5fa;   /* 新增：blue 400 */

/* light */
--color-success: #16a34a;   /* 维持 */
--color-warning: #d97706;   /* 微调：amber 600（现值 #b45309 偏暗） */
--color-danger:  #dc2626;   /* 维持 */
--color-info:    #2563eb;   /* 新增：blue 600 */

/* 品牌色（可选，二选一，待你定） */
--color-brand:      #5b8cff;   /* 方案 A：科技蓝 */
--color-brand:      #2f9e7d;   /* 方案 B：teal（与你旅行攻略模板一致） */
```

### 间距

```css
--space-0: 0;  --space-1: 4px;  --space-2: 8px;  --space-3: 12px;
--space-4: 16px; --space-5: 20px; --space-6: 24px; --space-8: 32px;
--space-10: 40px; --space-12: 48px;
```

### 圆角

```css
--radius-xs: 4px;    /* tag / checkbox / 代码行 */
--radius-sm: 6px;    /* 按钮 / 输入框 / 图标按钮 */
--radius-md: 8px;    /* 卡片 / 弹窗 / 下拉 */
--radius-lg: 12px;   /* 大卡片 / 浮层 */
--radius-xl: 16px;   /* 面板头部 */
--radius-full: 999px;/* 胶囊 / 头像(50%) */
```

---

## 附录 A：圆角完整频次

| 值 | 次数 | 值 | 次数 |
|----|------|----|------|
| 6px | 52 | 10px | 9 |
| 8px | 39 | 4px | 6 |
| 50% | 16 | 12px | 6 |
| 7px | 14 | 9px | 3 |
| 5px | 11 | 2px | 3 |
| 999px | 9 | 3px | 2 |

混合值：`24px`、`14px`、`16px 16px 0 0`、`10px 10px 0 0`、`8px 8px 2px 8px`、`0 2px 2px 0`（各 1）。

## 附录 B：待你确认的三个决策点

1. **品牌色**：是否引入？（方案 A 科技蓝 / 方案 B teal / 维持黑白极简）
2. **K 线涨跌色**：是否改回 A 股"涨红跌绿"？
3. **控件高度基准**：输入框统一 36px 还是 40px？（影响 Phase 3 范围）
