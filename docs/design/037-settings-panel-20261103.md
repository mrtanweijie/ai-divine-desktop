# 037 · 设置弹窗升级为独立设置面板（2026-11-03）

> 日期：2026-11-03 ｜ 类型：design ｜ 状态：**P1 已实施**
> 已实施：`pages/settings/` 整页面板（分组导航 + SettingRow 骨架 + section 深链 `?view=settings&section=x`）、
> 8 个 section 组件原样迁至 `pages/settings/sections/`、basic 拆出 外观/键盘快捷键 薄页、
> 入口改造（侧栏/横幅深链）、**SettingsModal 删除**（含 updater 的 settingsOpen 死代码清理）、
> ESC 返回、窄窗口导航收窄。保存模型：P1 维持分区保存按钮（P2 行级即时保存另行排期）。

## 1. 现状与问题

设置目前是 `SettingsModal`——一个覆盖在对话上的**居中弹窗**（`settingsOpen` state 控制，
侧栏 footer 与 API Key 横幅两个入口）。随着分区增长（basic / model / **media** / mcp /
local / memory / browser / about 已 8 个，后续只会更多），弹窗形态的问题：

1. **纵向空间不足**：模型列表、MCP 服务器、生成模型都是长表单，弹窗里要内部滚动，
   "设置"变成了"在抽屉里翻箱子"；
2. **遮挡对话**：调模型参数时经常要对照对话里的报错，弹窗全遮；
3. **无法深链**：横幅只能传 `settingsInitialSection` 打开弹窗，不能落在一个可分享/
   可返回的视图状态上；
4. **无分组层级**：8 个 tab 平铺在弹窗左栏，加到十几个后不可维护；
5. **保存模型不统一**：有的分区点"保存"、有的即时保存（全局快捷键），心智负担大。

## 2. 目标形态（对照截图）

```
┌──────────────┬────────────────────────────────────────────┐
│ ← 返回工作区  │  模型设置                                    │
│              │                                            │
│ 基础设置      │  ┌──────────────────────────────────────┐  │
│  常规         │  │ 默认模型            [DeepSeek ▾]     │  │
│  外观         │  │ 对话使用的模型                        │  │
│  键盘快捷键   │  ├──────────────────────────────────────┤  │
│ 模型          │  │ 思考模式            [Switch]          │  │
│  对话模型     │  │ …                                    │  │
│  生成模型     │  └──────────────────────────────────────┘  │
│  本地模型     │                                            │
│ Agent 能力    │                                            │
│  浏览器控制   │                                            │
│  记忆         │                                            │
│  MCP 服务器   │                                            │
│              │                                            │
│ ──────────── │                                            │
│ 👤 TANWEIJIE │                                            │
└──────────────┴────────────────────────────────────────────┘
```

- **整页视图**，与「已安排」「技能」「生成任务」同一机制（`view=settings`）；
- 左侧**两级导航**：分组标题（不可点）+ 设置项；右侧内容区滚动；
- 右侧每条设置是一**行**：左「标题 + 一句话描述」、右控件（对照截图）；
- 顶部「返回工作区」回到 chat 视图；**ESC 同效**；
- 底部 footer：用户名（后续放账号/主题快捷入口，本期只展示）。

**与截图的有意差异**（不做没有后端的东西——035 §7.7 同一原则）：
截图里的「远程设备 / 电脑控制 / 子智能体 / 插件 / 技能 / 命令 / 钩子 / 数据与统计」
我们**没有对应功能，导航里不出现**。技能/插件目前有独立页面（`view=skills`），
不往设置里塞第二份入口。

## 3. 信息架构：导航分组与映射

现有 8 个 section 全部保留，重新分组（**不新增、不合并功能**，只动层级）：

| 分组 | 导航项 | 来自现 section | 拆分说明 |
| --- | --- | --- | --- |
| 基础设置 | 常规 | basic（语言/用户名/上下文上限/思考档位） | 主题相关拆到「外观」 |
| 基础设置 | 外观 | —（新增壳，承接 basic 里的主题偏好） | 浅/深/跟随系统 |
| 基础设置 | 键盘快捷键 | basic 里的全局快捷键开关 | 独立成页，后续加快捷键列表 |
| 模型 | 对话模型 | model | 原样 |
| 模型 | 生成模型 | media | 原样（036） |
| 模型 | 本地模型 | local | 原样（横幅深链目标改为 `section=local`） |
| Agent 能力 | 浏览器控制 | browser | 原样 |
| Agent 能力 | 记忆 | memory | 原样 |
| Agent 能力 | MCP 服务器 | mcp | 原样 |
| 关于 | 关于 | about | 原样 |

分组标题：基础设置 / 模型 / Agent 能力 / 关于（i18n key `settings.group.*`）。
新 section id：`appearance`、`shortcuts` 两个壳页实现很薄（各 1–3 行设置）。

## 4. 布局与组件规范

### 4.1 SettingRow（新组件，本次的核心资产）

```
┌──────────────────────────────────────────────┐
│ 默认模型                        [Select ▾]   │
│ 对话使用的模型                                │
└──────────────────────────────────────────────┘
```

- props：`title` / `description?` / `control` / `children?`（宽控件如模型列表用 children 占整行）；
- 行高 `min-height: 56px`，标题 13px / 描述 11.5px（muted），控件右对齐垂直居中；
- 分组卡片：相关行包进一张卡片（`--radius-md` + `--color-surface-2`），卡片间 12px；
- **全键盘可达**：控件本身可聚焦即可，行容器不做 button（避免嵌套交互）；
- 全部走现有 token（深浅色自动），**不写死色值**（044 §9.4）。

### 4.2 页面骨架

`pages/settings/index.tsx`：

- 布局 `Flex`：左 220px 导航（可折叠，同 session-sidebar 折叠逻辑）+ 右内容区；
- 导航项复用 `.settings-nav-item` 样式（搬过来，不共享 modal 的类名——
  非 CSS Modules 全局类名会互染，新类加 `sp-` 前缀，028 教训）；
- 顶部返回按钮 + 当前 section 标题（大字号，对照截图的「常规」）。

### 4.3 各 section 内容区迁移

**Section 组件原样复用**（BasicSection / ModelSection / MediaSection / McpSection /
LocalSection / MemorySection / BrowserSection / AboutSection）——本方案只换壳不动内容。
迁移时只做两件事：

1. 每个组件的**外层容器**换成 SettingRow / 卡片结构（表单控件不动）；
2. basic 拆出 Appearance / Shortcuts 两个薄组件。

## 5. 保存模型（分两阶段，P1 不做行级重构）

- **P1（换壳）**：维持现状语义——分区底部「保存」按钮 + 少数即时保存项
  （全局快捷键）。saveCurrentSection 的分组逻辑原样搬到面板。
  保存成功 toast（现有机制）。
- **P2（即时保存）**：SettingRow 支持 `onCommit`，Select/Switch 变更即存、
  Input 失焦或 500ms debounce 存，移除「保存」按钮。各 section 的草稿 state
  要从分区级下沉到行级，改动面大，单独排期。

**不做**"半即时"（有的行即时有的要保存）——那正是现在的心智负担来源。

## 6. 视图层与路由

- `view=settings`（与 tasks/skills/media 同机制），**section 进 query**：
  `view=settings&section=local`——横幅深链、浏览器刷新都落在同一位置；
- ChatPage：`settingsOpen` state 删除，`activeView` 增加 `"settings"`；
- 返回：`openView("chat")`（或浏览器返回，searchParams 天然支持）；
- ESC 处理：面板内 `useEffect` 监听 keydown → 返回 chat（modal 的 ESC 语义平移）。

## 7. 入口与迁移

| 入口 | 现状 | 改为 |
| --- | --- | --- |
| 侧栏 footer 设置链接 | `setSettingsOpen(true)` | `openView("settings")` |
| API Key 横幅「去安装本地模型」 | `setSettingsInitialSection("local")` + 开弹窗 | `openView("settings", "local")` |
| 意图页等其他 `settingsInitialSection` 消费方 | 同上 | 同上深链 |

**SettingsModal 整体删除**（不是保留做降级）：8 个 Section 组件搬到
`pages/settings/sections/`，modal 骨架废弃。保留两套壳是维护税，一次切干净。
`onClose` 里的 `getSettings()` 回刷逻辑平移到面板（本地模型启停后刷新）。

## 8. 实施拆解

| 阶段 | 内容 |
| --- | --- |
| P1-a 骨架 | `pages/settings/` 页面 + 分组导航 + SettingRow 组件 + `view=settings` 路由与深链 |
| P1-b 迁移 | 8 个 section 组件搬入 + basic 拆 appearance/shortcuts + 入口改造 + 删 SettingsModal |
| P2 即时保存 | 行级 onCommit + 移除保存按钮（单独排期） |

## 9. 验收标准（P1）

1. 侧栏设置 → 整页面板打开，左分组导航、右内容区，无弹窗遮罩；
2. 「返回工作区」/ ESC 回到对话；浏览器返回键同效（searchParams 历史）；
3. 横幅「去安装本地模型」→ 直接落在「本地模型」页；
4. 每个分区保存行为与迁移前一致（逐分区过一遍：模型/生成模型/MCP/本地/记忆/浏览器/常规）；
5. 本地模型启停后设置面板内的模型列表会刷新（原 onClose 回刷语义保留）；
6. 深浅色两套主题下行式布局无错位（SettingRow 全 token 化）；
7. 窄窗口（<900px）导航可折叠，内容区不横向滚动；
8. 代码里不再有 `SettingsModal` 引用（grep 为零）。

## 10. 待拍板

1. **保存模型**：P1 先保持「分区保存按钮」（本方案默认），还是直接一步到位做行级即时保存？
   我建议分两阶段——换壳是纯搬运风险低，行级保存要重写 8 个 section 的草稿逻辑，混在一起出问题难定位。
2. **「外观」「键盘快捷键」** 两个壳页本期做（从 basic 拆出，各几行），还是先不拆、
   basic 原样搬？拆了导航更贴截图，但多两个薄页面。
