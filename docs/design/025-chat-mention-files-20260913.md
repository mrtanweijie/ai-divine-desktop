# 对话框 @ 引用文件 · / 指定技能 · 方案设计

> 目标：在聊天输入框支持两类引用——
> `@` 引用当前会话项目目录内的文件/文件夹，让 agent 精准获知用户所指；
> `/` 指定已安装技能（knowledge / executable），让本轮**强制**按该技能执行。
>
> 修订 v2：并入技能引用与协议结构化；触发符分工固定为 `@` = 作用对象，`/` = 做事方法。

## 0. 现状与约束（代码事实）

| 事实 | 位置 |
| --- | --- |
| 输入框为轻量 TextArea，`onSend(question, files: ChatFile[])` | `divine-app/src/pages/chat/components/ChatInput/index.tsx`（509 行） |
| 会话绑定项目：`session.project_id` → `Project`（项目目录） | `divine-app/src/pages/chat/index.tsx:139` |
| 会话级工作区：`db.session_workspace(session_id)`，缺省回退全局 `workspace_dir()` | `divine-server/app/db/sessions.py:15` |
| 消息入口：`maybe_preprocess(question, session_id, workspace)` | `divine-server/app/api/chat.py:216` |
| agent 工具（read_file 等）以 workspace 为路径边界 | `app/tools/adapters/*` |
| 现有 `/api/files` 只列输出产物分类目录，不含项目文件树 | `app/api/files.py:108` |
| 技能注册表是**进程级单例**，`refresh()` 整体替换内部 `_skills` | `app/skill_lib/registry.py:15,50` |
| 技能列表端点 `GET /api/skills`（不带 workspace 时合并**所有项目**） | `app/api/skills.py:27` |
| agent 侧每轮按**当前会话工作区**刷新技能 | `app/agent/tools/tools.py:123` |
| 技能目录常驻注入 prompt（名称 + 描述），`load_skill(name)` 按需加载正文 | `app/agent/core/prompts.py:267`、`app/agent/tools/tools.py:192` |
| 能力技能以独立工具暴露，工具名由 `_skill_tool_name(name)` 生成 | `app/agent/core/schema.py` |
| 子 agent 仅暴露 knowledge 技能与 `load_skill` | `app/agent/tools/subagents.py:551` |

约束：

- 输入框刻意保持轻量 TextArea（无富文本依赖），两类引用都不能引入重型编辑器；
- **技能候选必须与 agent 实际可用技能集合一致**，不允许"前端能选、后端不可用"（见 3.1）。

## 1. 交互设计

### 1.1 `@` 触发与候选（文件/目录）

- 在 TextArea 光标处键入 `@` → 弹出候选浮层（输入框上方）；
- 继续输入即模糊过滤：`@index` 匹配 `src/index.tsx`、`app/index.less`；
- `@/` 进入目录浏览模式，按目录层级展开；
- 键盘：`↑↓` 选择、`Enter/Tab` 确认、`Esc` 关闭、继续输入实时刷新；
- 确认后在光标处插入 token：`@相对路径 `（尾带空格），支持一消息多个 @；
- Backspace 删除到 token 内则重新唤起候选（可再改选）。

### 1.2 候选列表条目（文件/目录）

```
[类型图标] 文件名        相对路径（截断中段）
           12.3 KB · 最近引用时间（如有）
```

分组排序：`最近引用（本会话）` → `当前目录` → `全局模糊匹配`，每组最多 5 条，
总返回 ≤ 20 条。图片文件显示缩略图（P2）。

### 1.3 `/` 触发与候选（技能）

- 触发位置受限：仅在**行首或空白字符后**键入 `/` 才唤起候选（正则 `(?<=\s|^)/`）。`/` 在正常文本中大量出现（`2026/09`、`and/or`、`src/components`），不能像 `@` 那样任意位置触发；
- 继续输入即模糊过滤：匹配技能名、描述与拼音首字母；
- 候选按类型分节：`知识技能`（方法论 / SOP / 参考资料）、`能力技能`（可执行脚本工具）；
- 条目展示：`[类型徽标] 技能名` + `来源（项目/用户/内置）` + 描述截断；
- 键盘交互与 `@` 一致（`↑↓` 选择、`Enter/Tab` 确认、`Esc` 关闭）；两个弹层互斥，同一时刻只显示一个；
- 确认后插入 token：`/技能名 `（尾带空格），支持一条消息多个 `/技能`；
- 进入候选态后若继续输入不可能构成技能名的字符（如 `/2`、路径分隔符），自动退出候选并按普通文本处理。

**保留字与消歧**：维护 `RESERVED_SLASH = {help, clear, new, model, skill, ...}`（为未来的斜杠指令预留）。技能名命中保留字时，候选项插入 `skill:名称` 形式的消歧串；技能安装/迁移遇到保留字名时给出警告（不阻断）。

### 1.4 发送态展示

保持纯文本消息（不做富文本）：发送后气泡内 `@路径` 高亮为链接样式（点击打开现有 `FilePreviewModal`），`/技能名` 用等宽字体 + 技能图标胶囊渲染。两类 token 颜色与形状不同，便于一眼区分"作用对象"与"做事方法"。

### 1.5 输入框内不做高亮 + 引用 chip 行

**事实**：`components/ui/TextArea/index.tsx`（25 行）是 `<label>` + 原生 `<textarea>`，无镜像层；`index.less` 只定义整体边框与底色。原生 textarea 的 value 共用一套字体颜色与字形，**无法对 `@路径` / `/技能名` 做局部上色或独立图标**——这是元素能力边界，不是实现问题。且该组件被 `SettingsModal` 的 McpSection、MemorySection 等 4 处复用，不能为聊天输入框改写这个通用组件。

**方案取舍**：

| 方案 | 输入框内观感 | 成本 | 结论 |
| --- | --- | --- | --- |
| A 前缀字符 | token 原样显示，靠 `@` / `/` 前缀区分 | 0 | ✅ 采用 |
| B 引用 chip 行 | 输入框下方一行汇总本轮引用 | 低（复用现有附件 chip 区域） | ✅ 采用 |
| C overlay 镜像层 | 框内真高亮（变色/加底） | 中高 | ⏸ 列为 P2 可选 |
| D contentEditable | 框内真高亮 | 高 | ❌ 会推翻受控 value / IME / 粘贴 / 高度自适应，不采用 |

C 若后续要做，需新增 `HighlightTextArea`（不改通用 `TextArea`），并逐项对齐：字体族、`font-size: 13px`、`line-height: 1.6`、`padding: 8px 10px`、`white-space: pre-wrap`、滚动同步、IME 合成期冻结重渲染、末行空白补 `\u200b`。

**B 的 chip 行设计**：

- **位置**：与现有附件 chip 同一行（输入框下方 `.composer-attachments` 区域），文件附件 chip 在前、引用 chip 在后；
- **条目形态**：
  - 文件引用 `[文件图标] a.jpg`（相对路径中段截断，tooltip 显示完整路径）；
  - 技能引用 `[技能图标] [知识] photo-abstract-editorial`（类型徽标，tooltip 显示来源 project/user/builtin 与描述）；
- **交互**：点击 chip → 光标跳转到文本中对应 token 并选中；chip 上的 `×` → 同时删除 chip 与文本 token；
- **同步规则**：文本是唯一事实来源——文本 token 被手工删改时 chip 同步消失，chip 删除时同步删文本 token 及其尾随空格，两者由同一份 `mentions` 状态驱动，不维护两份事实；
- **上限提示**：技能引用超过 3 个时 chip 行高亮提示（与 §3.5 一致）。

## 2. 数据流设计

### 2.1 候选数据源（新增后端端点，文件与技能混排）

```
GET /api/workspace/mentions?q=index&session_id=...&kinds=file,skill&limit=20
```

- **文件候选**：范围 = 会话生效工作区（`session_workspace(session_id)` → 项目目录 → 全局 `workspace_dir()` 依次回退）；进程内目录索引（首次扫描全树缓存，fs watcher 失效；≤5 万文件直接内存匹配）；过滤 `.git`、`node_modules`、`.gitignore` 规则、隐藏文件、>10MB 二进制；匹配为不区分大小写的前缀优先 + 子序列兜底；
- **技能候选**：复用 `skill_registry`，但**必须按同一个 session workspace 刷新**，并与 agent 侧共用同一次刷新结果（见 3.1 硬问题 ①）；
- 返回（字段契约已冻结，完整定义见 §9.1）：

```json
{ "workspace": "/...", "truncated": false, "items": [
  { "kind": "file", "path": "src/index.tsx", "type": "file", "size": 123, "mtime": 1710000000 },
  { "kind": "skill", "path": "photo-abstract-editorial", "name": "photo-abstract-editorial",
    "type": "knowledge", "source": "user", "description": "...", "version": "1.0.0" }
] }
```

- 安全：服务端拼路径 + `resolve()` 后必须落在工作区内（防 `../` 越界）。

### 2.2 消息协议（结构化 mentions）

**主轨（纯文本）**：token 留在 question 文本里（`用 /photo-abstract-editorial 处理 @assets/a.jpg`），删除/移动后语义仍可读。

**增强轨（mentions 元数据）**：由 `list[str]` 升级为结构化数组——技能名可能与目录名同名，纯字符串无法区分类型：

```json
{ "question": "用 /photo-abstract-editorial 处理 @assets/a.jpg",
  "mentions": [
    { "type": "skill", "name": "photo-abstract-editorial" },
    { "type": "file", "path": "assets/a.jpg" }
  ] }
```

- **兼容**：`list[str]` 一律按 `type=file` 解析，旧前端不受影响；
- **后端只信 `mentions` 数组，不从 question 正文反向抽取**：`/` 与路径、日期歧义太大，正文正则会误伤。正则只用于前端高亮与光标 token 定位；
- 发送前校验一次：技能被卸载/改名、文件被删除的失效项从 mentions 中剔除，并在气泡上以删除线提示。

### 2.3 文件引用注入（保持原取舍）

后端在 `maybe_preprocess` 阶段注入一条上下文前缀（不塞文件内容，避免 token 爆炸）：

```
[用户引用的文件（相对当前工作区）]
- src/index.tsx（12.3 KB, text/ts, 修改于 2 小时前）
```

文件内容由 agent 自行调用 read_file 读取（工具已有，路径边界已管）。

### 2.4 技能引用注入（强注入）

技能与文件语义不同：文件是**指代**（读取决策权交给 agent），技能是**指令**（本轮必须按它执行）。因此技能不能沿用文件那套"只注入元数据"的策略，须走强注入，细节见第 3 节。

### 2.5 深度引用（P3，可选）

`mentions` 支持 `"inline": true`（或 `@@路径` 语法）：文本文件 ≤ 20KB 自动内联内容进上下文，
超限则降级为元数据注入。

## 3. `/` 指定技能：注入策略与硬约束

### 3.1 三个必须先修的硬问题

**① 技能候选集合与 agent 可用集合不一致（高危）**
`/api/skills` 不带 workspace 时执行 `refresh(project_roots=所有项目)`，把各项目的 `.divine/skills` 合并进同一个字典，同名技能按遍历顺序互相覆盖；而 agent 侧 `tools.py:123` 每轮只 `refresh(ctx.workspace)`。结果：前端搜得到、`/` 也选上了，`load_skill` 却返回"技能不存在"。
→ 修：mentions 端点的技能候选必须走会话作用域，与 agent 侧共用同一次 refresh 结果。

**② `skill_registry` 单例跨会话污染**
注册表是进程级单例，`refresh` 整体替换 `_skills`；两个不同项目的会话并发时互相覆盖，A 会话的技能目录可能落到 B 会话。文件引用没有这个问题（走 `session_workspace`），技能必须显式解决。
→ 修：registry 增加按 workspace 的作用域缓存（`dict[workspace, dict[str, SkillMeta]]`），或让 `load(name, workspace)` 显式带 workspace 参数。

**③ `refresh` 每次请求全量扫盘**
`tools.py` 每轮 build tools 都会遍历 project / user / builtin 三个 root 并解析每个 SKILL.md；叠加 `/` 触发的高频搜索请求后成本进一步放大。
→ 修：refresh 加 mtime 指纹缓存（目录 mtime + SKILL.md mtime），或与文件索引共用同一次扫描、共用失效入口。

### 3.2 注入策略

| 技能类型 | 注入形态 | 理由 |
| --- | --- | --- |
| knowledge | 直接注入 SKILL.md 正文 + references；或注入硬指令「本轮必须首先调用 `load_skill(name)`」 | 只注入一行描述等于重复 prompt 里已有的技能目录，agent 大概率仍不加载，用户会认为「/ 了没用」 |
| executable | 注入「必须调用工具 `<tool_name>`」+ 参数契约（stdin JSON / args，由 `script_mode` 决定）；react 模式需显式给出工具名与参数格式 | 能力技能的价值在执行，不在读文档 |

**预算上限**：单技能正文 ≤ 2 万字符，多技能累加封顶（建议 4 万字符）；超限降级为硬指令 + 描述，并在日志中标注降级。

**注入顺序**：先技能（决定方法），后文件（决定材料）。示例：

```
[本轮指定技能（必须使用）]
- photo-abstract-editorial（knowledge，来源 user）：正文已加载如下
  <SKILL.md 正文 …>

[用户引用的文件（相对当前工作区）]
- assets/a.jpg（1.2 MB, image/jpeg, 修改于 3 小时前）
```

### 3.3 使用校验闭环

技能引用是**契约**：本轮至少应产生一次 `load_skill` 或该技能对应的工具调用。工具调用事件已在 SSE 流中，agent 结束后比对 `mentions` 与实际 `tool_calls`，回传 `unused_mentions`，由前端提示「技能未被使用」——否则"选错了"用户无从察觉。

### 3.4 执行体透传

`subagents.py:551` 目前只给子 agent 暴露 knowledge 技能。若本轮 `/` 了 executable 技能而又走了子 agent，技能将不可见。
→ 修：本轮被引用的技能强制透传到该轮**所有执行体**（主循环 + 子 agent）的工具 allowlist。

### 3.5 数量与顺序

一条消息的技能引用建议 ≤ 2~3 个，超出时候选浮层直接阻止并提示；注入顺序 = 用户选择顺序。

## 4. 改动清单

### 后端（divine-server）

| 文件 | 改动 |
| --- | --- |
| `app/api/workspace_files.py`（新） | `GET /api/workspace/mentions` 端点（file + skill 混排）、目录索引缓存、gitignore 过滤、越界防护；技能候选按 session workspace 刷新 |
| `app/skill_lib/registry.py` | 按 workspace 的作用域缓存/查询接口；mtime 指纹缓存；保留字技能名警告 |
| `app/api/chat.py` | 请求模型 `mentions` 结构化（兼容 `list[str]`）；`_build_mention_context()`（技能强注入 / 文件元数据）；失效项剔除；注入预算控制；`skill:` 消歧解析；结束后计算 `unused_mentions` |
| `app/agent/core/prompts.py` | 常驻节追加两句：`@路径` 为当前工作区相对路径可直接读取；被 `/` 指定的技能正文已加载，无需重复 `load_skill` |
| `app/agent/tools/subagents.py` | 本轮被引用技能透传到子 agent 的 allowlist |
| `app/db/sessions.py` | 无改动（复用 `session_workspace`） |

### 前端（divine-app）

| 文件 | 改动 |
| --- | --- |
| `components/ChatInput/MentionPopup.tsx`（新） | 候选浮层组件，支持 `mode: "file" \| "skill"`；技能模式按类型分节、展示类型徽标与来源 |
| `components/ChatInput/index.tsx` | `@` 触发文件候选、`/` 触发技能候选（限行首/空白后）、插值、Esc/Backspace 处理、mentions 收集并随 onSend 上送；引用 chip 行渲染与文本 token 双向同步 |
| `components/ChatInput/index.less` | 引用 chip 行样式（与现有附件 chip 同构）：文件/技能两类 chip、类型徽标、删除按钮 |
| `pages/chat/chatUtils.ts` | `parseMentions(text)` 同时解析 `@路径` 与 `/技能名`（仅用于高亮与光标定位，不用于后端抽取）、消息渲染高亮 |
| `services/api.ts`（或 chat api 层） | 搜索端点封装（300ms 防抖 + AbortController） |
| `pages/chat/components/MessageItem` | `@路径` 高亮 + 点击预览；`/技能名` 胶囊渲染 |
| 技能中心 / 迁移入口 | 保留字技能名警告 |

## 5. 关键决策与取舍

| 决策 | 选择 | 理由 |
| --- | --- | --- |
| 候选来源 | 后端端点（非前端 Tauri fs 直读） | 统一安全边界；浏览器模式可用；索引/gitignore 逻辑收敛在后端 |
| 消息形态 | 纯文本 token + mentions 元数据双轨 | 零富文本依赖；agent 可用性最好；重命名等边缘场景可读 |
| 不自动内联文件内容 | 默认只注入元数据 | token 成本可控；读取决策权在 agent；P3 再加 inline 白名单 |
| 引用范围 | 会话工作区（session → project → 全局回退） | 与 agent 工具边界一致，不会引用到 agent 读不到的文件 |
| mentions 形态 | 结构化数组（兼容 `list[str]`） | 技能名与目录名可能同名，纯字符串无法区分类型 |
| 技能注入强度 | 强注入（正文或硬指令） | 技能是命令而非指代，弱注入等于没引用 |
| `/` 作为技能触发符 | 仅在行首/空白后触发 | 与路径、日期、URL 冲突严重，必须限制触发位置 |
| 正文抽取 | 后端只信 mentions 数组 | `/` 的歧义会让正文正则误伤路径与日期 |
| 技能候选来源 | 与 agent 侧共用会话作用域的 refresh | 避免"前端可选、后端不可用" |
| 输入框内 token 高亮 | 不做，改用 A+B（前缀字符 + 引用 chip 行） | 原生 textarea 不支持局部样式；通用 `TextArea` 被 4 处复用不可改写；C 镜像层留 P2 |

## 6. 边界与异常

- 工作区不存在/为空：浮层显示「当前会话未绑定项目目录」+ 引导去 ProjectPicker；
- 超大目录（>5 万文件）：索引降级为懒扫描（仅两层 + 按需下钻），浮层提示「输入更多字符缩小范围」；
- `@` 后含空格：视为普通文本（路径 token 以空格终止）；
- 路径含空格：候选确认时自动加引号 `@"my file.txt"`，后端 mentions 解析同步支持；
- 与附件并存：附件走现有 `files: ChatFile[]`（上传内容），@引用只传路径，互不影响；
- `/` 出现在普通文本中（`2026/09`、`and/or`、`src/components`）：因触发位置限制在行首/空白后，不产生浮层；
- 技能在草稿期间被卸载/改名：发送前校验剔除 + 气泡删除线提示；
- 技能名命中保留字：插入 `skill:名称` 消歧串；
- 技能正文超预算：降级为硬指令 + 描述，日志标注；
- 跨项目/用户级/内置同名技能：候选展示来源徽标，选中项以 `name + source` 精确解析；
- 技能与文件同名：由触发符区分，`@` 走文件、`/` 走技能，不做猜测；
- 文本 token 被手工删改：引用 chip 行同步移除（文本是唯一事实来源，不维护两份状态）；
- 点击 chip 的 `×`：同步删除文本中对应 token 及其尾随空格。

## 7. 分期落地

| 期 | 内容 | 验收 |
| --- | --- | --- |
| P1a | 后端 mentions 端点（文件）+ ChatInput `@` 弹层 + 结构化 mentions 透传与文件上下文注入 + 输入框下方引用 chip 行 | 输入 @ 能搜到项目文件并引用；agent 能读懂引用并读取文件 |
| P1b | `/` 技能候选、技能强注入（knowledge 正文 / executable 工具名）、3.1 三个硬问题修复、失效项校验 | 输入 `/` 选中技能后本轮确实调用 `load_skill` 或对应工具，且 `unused_mentions` 为空 |
| P2 | 最近引用记忆（session 级 localStorage）、`@/` 目录浏览、图片缩略图、技能使用校验提示、输入框内 token 高亮（`HighlightTextArea` 镜像层，可选） | 二次引用无需搜索 |
| P3 | 深度引用（小文件内联）、@文件夹（展开文件清单注入）、多技能组合编排 | 小文件零工具调用即可答 |

## 8. 测试要点

- 后端（文件）：路径越界（`../`）、gitignore 过滤、模糊排序稳定性、大小目录性能、mentions 注入格式；
- 后端（技能）：跨项目同名技能解析、mentions 端点与 agent 侧技能集合一致性、registry 并发作用域隔离、`refresh` 缓存命中、保留字消歧、注入超预算降级、executable 技能在 react 模式下的调用、`unused_mentions` 计算；
- 前端：`/` 仅在行首/空白后触发、两类弹层互斥、token 解析（含空格路径）、键盘导航、Esc/Backspace 行为、与附件混发；
- 端到端：`@` 引用后 agent 实际 read 该文件并正确回答；`/` 指定技能后 agent 确实加载/调用了该技能。

## 9. P0 开工前确认项（契约冻结）

开工前列出的 4 条确认项，结论如下（实现现状见 §4 改动清单）。

### 9.1 mentions 端点字段契约（冻结）

`GET /api/workspace/mentions`，实现于 `app/api/workspace_files.py`。

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `q` | 空（返回全部） | ≤ 200 字符 |
| `session_id` | 空 | 缺省回退全局工作区 |
| `kinds` | `file` | 逗号分隔，支持 `file`、`skill`、`file,skill` |
| `limit` | 20 | 1~50，**只作用于文件候选** |

响应顶层：

```json
{ "workspace": "/... 或 null", "items": [ ... ], "truncated": false }
```

- `workspace`：会话生效工作区绝对路径；无绑定项目/会话时为 `null`，此时 `items` 为空数组；
- `truncated`：目录索引超过 5 万条上限被截断时为 `true`；
- **文件条目**：`{ "kind": "file", "path": "src/index.tsx", "type": "file|dir", "size": 123, "mtime": 1710000000 }`，`path` 为工作区相对路径；
- **技能条目**：`{ "kind": "skill", "path": <技能名>, "name": <技能名>, "type": "knowledge|executable|mcp", "source": "project|user|builtin", "description": "...", "version": "..." }`。`path` 与文件条目同义（前端统一取 `path` 作为插入文本，技能即名称）；技能候选独立上限 8 条，不受 `limit` 影响。

### 9.2 `session_workspace` 签名（冻结）

`app/db/sessions.py:15`：`def session_workspace(session_id: str) -> str | None`——`sessions JOIN projects` 取 `p.path`；会话不存在或未绑定项目时返回 `None`。**DB 层零改动**：端点与 chat 注入均复用该函数，不新增查询、不改 `app/db/sessions.py` 行为。

### 9.3 `sendMessage` 传参链路（冻结）

统一为四参：`sendMessage(question, files, mentions, effort)`。

- `useChatStream.ts`：`sendMessage(question: string, files: ChatFile[], mentions: MentionRef[], effort: string)`；
- `ChatInput`：`onSend(question, files, mentions)` 向外抛出；
- `pages/chat/index.tsx`：调用点原样透传 `onSend={(q, files, mentions) => sendMessage(q, files, mentions, composerEffort)}`；
- `ChatStreamContext`（消息渲染层可点击组件用）保持三参 `(question, files?, effort?)`，内部发送时 `mentions` 传 `[]`——与 `sendSupplement` 的纯文本通道一致（插话不携带引用）。

### 9.4 i18n 命名空间（冻结）

- 输入框与候选浮层的 `@` / `/` 文案 → `chat.*`：`mentionTitle`、`mentionSkillTitle`、`mentionSectionKnowledge`、`mentionSectionExecutable`、`mentionKindKnowledge`、`mentionKindExecutable`、`mentionSourceProject`、`mentionSourceUser`、`mentionSourceBuiltin`、`mentionFileHint`、`mentionSkillHint`、`mentionSearching`、`mentionDir`；
- 气泡内「技能未被使用」软提示 → `message.unusedMentions`（`{{names}}` 插值）；
- 三语同步：`zh-CN` / `zh-TW` / `en`，缺一不可。
