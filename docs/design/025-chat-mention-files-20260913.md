# 对话框 @ 引用项目文件 · 方案设计

> 目标：在聊天输入框支持 `@` 引用当前会话项目目录内的文件/文件夹，
> 让 agent 精准获知用户所指，免去手动输入路径。

## 0. 现状与约束（代码事实）

| 事实 | 位置 |
| --- | --- |
| 输入框为轻量 TextArea，`onSend(question, files: ChatFile[])` | `divine-app/src/pages/chat/components/ChatInput/index.tsx`（509 行） |
| 会话绑定项目：`session.project_id` → `Project`（项目目录） | `divine-app/src/pages/chat/index.tsx:139` |
| 会话级工作区：`db.session_workspace(session_id)`，缺省回退全局 `workspace_dir()` | `divine-server/app/db/sessions.py:15` |
| 消息入口：`maybe_preprocess(question, session_id, workspace)` | `divine-server/app/api/chat.py:216` |
| agent 工具（read_file 等）以 workspace 为路径边界 | `app/tools/adapters/*` |
| 现有 `/api/files` 只列输出产物分类目录，不含项目文件树 | `app/api/files.py:108` |

约束：输入框刻意保持轻量 TextArea（无富文本依赖）；@引用不能引入重型编辑器。

## 1. 交互设计

### 1.1 触发与候选

- 在 TextArea 光标处键入 `@` → 弹出候选浮层（输入框上方）；
- 继续输入即模糊过滤：`@index` 匹配 `src/index.tsx`、`app/index.less`；
- `@/` 进入目录浏览模式，按目录层级展开；
- 键盘：`↑↓` 选择、`Enter/Tab` 确认、`Esc` 关闭、继续输入实时刷新；
- 确认后在光标处插入 token：`@相对路径 `（尾带空格），支持一消息多个 @；
- Backspace 删除到 token 内则重新唤起候选（可再改选）。

### 1.2 候选列表条目

```
[类型图标] 文件名        相对路径（截断中段）
           12.3 KB · 最近引用时间（如有）
```

分组排序：`最近引用（本会话）` → `当前目录` → `全局模糊匹配`，每组最多 5 条，
总返回 ≤ 20 条。图片文件显示缩略图（P2）。

### 1.3 发送态展示

保持纯文本消息（不做富文本）：发送后消息气泡内 `@路径` 用正则高亮为链接样式，
点击打开现有 `FilePreviewModal`。

## 2. 数据流设计

### 2.1 候选数据源（新增后端端点）

```
GET /api/workspace/files?prefix=index&limit=20&dirs=true
Authorization: 会话上下文（session_id 由前端带）
```

- 范围：会话生效工作区 = `session_workspace(session_id)` → 项目目录 → 全局 `workspace_dir()`（优先级依次回退）；
- 实现：进程内目录索引（首次扫描全树缓存，fs watcher 失效；≤5 万文件直接内存匹配）；
- 过滤：`.git`、`node_modules`、`.gitignore` 规则、隐藏文件、>10MB 二进制；
- 匹配：相对路径不区分大小写子序列/子串模糊（先精确前缀优先，再模糊兜底）；
- 返回：`{ "workspace": "/...", "items": [{ "path": "src/index.tsx", "type": "file|dir", "size": 123, "mtime": 1710000000 }] }`
- 安全：服务端拼路径 + `resolve()` 后必须落在工作区内（防 `../` 越界）。

### 2.2 消息协议（轻量双轨）

**主轨（纯文本）**：@token 直接留在 question 文本里（`帮我看看 @src/index.tsx 的错误处理`）。
agent 的 read_file 等工具天然支持相对路径，零协议成本；删除/移动文件后语义仍可读。

**增强轨（mentions 元数据）**：发送 payload 增加：

```json
{ "question": "帮我看看 @src/index.tsx 的错误处理",
  "mentions": ["src/index.tsx"] }
```

后端在 `maybe_preprocess` 阶段注入一条上下文前缀（不塞文件内容，避免 token 爆炸）：

```
[用户引用的文件（相对当前工作区）]
- src/index.tsx（12.3 KB, text/ts, 修改于 2 小时前）
```

文件内容由 agent 自行调用 read_file 读取（工具已有，路径边界已管）。

### 2.3 深度引用（P3，可选）

`mentions` 支持 `"inline": true`（或 `@@路径` 语法）：文本文件 ≤ 20KB 自动内联内容进上下文，
超限则降级为元数据注入。

## 3. 改动清单

### 后端（divine-server）

| 文件 | 改动 |
| --- | --- |
| `app/api/workspace_files.py`（新） | `GET /api/workspace/files` 搜索端点 + 目录索引缓存 + gitignore 过滤 + 越界防护 |
| `app/api/chat.py` | 请求模型加 `mentions: list[str]`；`maybe_preprocess` 后注入引用上下文前缀；mentions 路径做工作区边界校验 |
| `app/db/sessions.py` | 无改动（复用 `session_workspace`） |

### 前端（divine-app）

| 文件 | 改动 |
| --- | --- |
| `components/ChatInput/MentionPopup.tsx`（新） | 候选浮层组件（分组列表、键盘导航、加载/空态） |
| `components/ChatInput/index.tsx` | `@` 触发检测（光标位置解析当前 token）、插值、Esc/Backspace 处理、mentions 收集并随 onSend 上送 |
| `pages/chat/chatUtils.ts` | `parseMentions(text)`（正则提取 `@路径`）、消息渲染高亮 |
| `services/api.ts`（或 chat api 层） | 搜索端点封装（300ms 防抖 + AbortController） |
| `pages/chat/components/MessageItem` | `@路径` 高亮 + 点击预览 |

### Agent 侧

- `prompt_sections` 常驻节追加一句：`用户消息中的 @路径 为当前工作区相对路径，可直接用 read_file 等工具读取`。

## 4. 关键决策与取舍

| 决策 | 选择 | 理由 |
| --- | --- | --- |
| 候选来源 | 后端端点（非前端 Tauri fs 直读） | 统一安全边界；浏览器模式可用；索引/gitignore 逻辑收敛在后端 |
| 消息形态 | 纯文本 token + mentions 元数据双轨 | 零富文本依赖；agent 可用性最好；重命名等边缘场景可读 |
| 不自动内联文件内容 | 默认只注入元数据 | token 成本可控；读取决策权在 agent；P3 再加 inline 白名单 |
| 引用范围 | 会话工作区（session → project → 全局回退） | 与 agent 工具边界一致，不会引用到 agent 读不到的文件 |

## 5. 边界与异常

- 工作区不存在/为空：浮层显示「当前会话未绑定项目目录」+ 引导去 ProjectPicker；
- 超大目录（>5 万文件）：索引降级为懒扫描（仅两层 + 按需下钻），浮层提示「输入更多字符缩小范围」；
- `@` 后含空格：视为普通文本（路径 token 以空格终止）；
- 路径含空格：候选确认时自动加引号 `@"my file.txt"`，后端 mentions 解析同步支持；
- 与附件并存：附件走现有 `files: ChatFile[]`（上传内容），@引用只传路径，互不影响。

## 6. 分期落地

| 期 | 内容 | 验收 |
| --- | --- | --- |
| P1 | 后端搜索端点 + ChatInput @ 弹层 + mentions 透传与上下文注入 | 输入 @ 能搜到项目文件并引用；agent 能读懂引用并读取文件 |
| P2 | 最近引用记忆（session 级 localStorage）、`@/` 目录浏览、图片缩略图 | 二次引用无需搜索 |
| P3 | 深度引用（小文件内联）、@文件夹（展开文件清单注入） | 小文件零工具调用即可答 |

## 7. 测试要点

- 后端：路径越界（`../`）、gitignore 过滤、模糊排序稳定性、大小目录性能、mentions 注入格式；
- 前端：token 解析（含空格路径）、键盘导航、Esc/Backspace 行为、与附件混发；
- 端到端：@引用后 agent 实际 read 该文件并正确回答。
