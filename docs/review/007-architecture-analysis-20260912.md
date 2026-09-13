# 007 · 项目架构与功能分析（2026-09-12）

> 编号：007 ｜ 类型：review ｜ 日期：2026-09-12 ｜ 版本：v0.2.1 ｜ 状态：完成
> 范围：`divine-app`（前端 + 桌面壳）、`divine-server`（后端 sidecar）、工程与文档体系

---

## 1. 项目定位

**Divine：本地优先、隐私可控的桌面 AI 助手。**

一句话概括架构选型：**把「宿主」和「大脑」彻底分开**。Rust/Tauri 只做进程宿主与系统集成，全部业务逻辑跑在一个 Python sidecar 里，前端只负责渲染与交互。三方通过本机回环的 HTTP + SSE 通信，不依赖云端账号，数据默认落在本机 SQLite。

| 端口 | 服务 | 职责 |
| --- | --- | --- |
| 8019 | FastAPI sidecar | Agent、SSE、SQLite、工具系统 |
| 8010 | Vite dev server | 前端开发服务，`/api` 代理到 8019 |
| 8016 | llama-server | 本地模型（意图识别 / 长文预整理 / 本地问答） |

---

## 2. 分层架构

```
┌──────────────────────────────────────────────────────┐
│ 桌面壳  Tauri 2 + Rust                                │
│ 窗口 / 托盘 / 全局快捷键 / 自动拉起并监控 sidecar       │
└───────────────────────┬──────────────────────────────┘
                        │ 内嵌 WebView
┌───────────────────────▼──────────────────────────────┐
│ 前端  React 19 + Vite + TypeScript                    │
│ 自研组件（无 AntD）· 会话工作台 · 图表/图形/代码渲染     │
└───────────────────────┬──────────────────────────────┘
                        │ HTTP + SSE（/api 代理）
┌───────────────────────▼──────────────────────────────┐
│ 后端 sidecar  FastAPI（:8019）                        │
│ API 路由 ×72 · Agent 编排 · 工具 ×70 · docgen 渲染     │
└───────────────────────┬──────────────────────────────┘
                        │ SQLite 读写
┌───────────────────────▼──────────────────────────────┐
│ 本地存储  SQLite + 文件系统                            │
│ data/divine.db · workspace 文档 · output 产物          │
└──────────────────────────────────────────────────────┘
```

**关键设计**：Tauri 壳通过 `src/services/sidecar.rs` 负责 sidecar 的拉起、健康检查与掉线重启。这样做的收益是——后端可以独立开发、独立测试（`python run.py`）、独立打包（PyInstaller），桌面壳换掉也不影响业务代码。

---

## 3. 代码规模与模块分布

### 后端 `divine-server/app`（64,634 行 Python）

| 模块 | 文件 | 行数 | 职责 |
| --- | --- | --- | --- |
| `docgen/` | 78 | 21,466 | 文档生成：PDF / Word / PPT / 图表 / 简历渲染器 |
| `tools/` | 140 | 20,245 | 工具注册、adapter 实现、子进程脚本、模板 |
| `agent/` | 37 | 11,257 | Agent 编排（LangGraph）、prompt、工具执行、意图裁剪、SSE 拆分 |
| `db/` | 17 | 3,389 | SQLite 连接、迁移、按领域拆分的仓储、自研检索原语 |
| `api/` | 17 | 3,374 | HTTP / SSE / WebSocket 路由 |
| `llm/` | 7 | 1,325 | provider、DSML 流解析、LangChain 适配 |
| `skill_lib/` | 6 | 1,195 | 内置技能库 |
| `mcp/` | 3 | 478 | MCP server 连接管理（stdio / SSE） |
| 根级 | — | ~3,200 | config、main、scheduler、schemas、rag_store 等 |

### 前端 `divine-app/src`（138 个 ts/tsx，27,390 行）

| 目录 | 行数 | 说明 |
| --- | --- | --- |
| `pages/` | 20,237 | 主要是 `pages/chat`（消息流、输入区、工具卡片、项目、会话列表）+ `pages/tasks` |
| `components/` | 4,166 | 自研 UI：SettingsModal、TitleBar、ConfirmDialog、StartupGate 等 |
| `services/` | 1,696 | api / sse / tauri / storage / updater 等 |
| `config` `i18n` `hooks` `layout` `styles` | 597 | 配置、国际化、布局 |

### 工程配套

| 项 | 规模 |
| --- | --- |
| 后端测试 | 98 个 `test_*.py`，19,164 行 |
| 离线评测 | `evals/`：fake_model + harness + scenarios（含记忆检索专项） |
| 文档 | `docs/` 下 plan 4 篇 / design 22 篇 / review 6 篇 / fix 2 篇 |

---

## 4. Agent 运行时管线

请求从 `POST /api/stream_chat` 进入后，经过五个阶段：

1. **接入与预处理** — 历史裁剪、摘要压缩、超长工具结果 stub 化（`agent/middleware/preprocess.py`）
2. **意图分流** — 本地 llama-server 分类，置信度 ≥ 0.75（`DEFAULT_LOCAL_LLM_THRESHOLD`）且命中本地意图（`open_app` / `screenshot` / `lock_screen` / `search_file`）时本地直答，**完全不调云端 LLM**
3. **Prompt 装配** — 动态注入记忆 top-K、RAG 检索结果、技能目录、计划进度（`agent/core/prompt_sections.py`）
4. **LangGraph 推理循环** — `create_agent` + 中间件链
5. **工具执行管线** — 统一 adapter，含审批、终端策略、超时、`tool_runs` 落库

### 中间件链（`agent/tools/tools.py::_build_agent`）

按注册顺序：

| 中间件 | 作用 |
| --- | --- |
| `TurnCounterMiddleware` | 轮次计数 |
| `_build_dynamic_prompt` | 每轮动态重建 system prompt |
| `ModelCallLimitMiddleware` / `ToolCallLimitMiddleware` | 模型调用与工具调用双重限流（`MAX_TOOL_TURNS`） |
| `HumanInTheLoopMiddleware` | `write_todos` 计划审批（approve / reject） |
| `TodoSyncMiddleware` | Todo 状态与 SSE 同步 |
| `UserInjectionMiddleware` | 用户中途插话注入 |
| `TodoListMiddleware` | 待办列表 |
| `ToolErrorMiddleware` | 工具异常兜底，转为可读文本回灌模型 |
| `ReActParseMiddleware` | 仅 `tool_mode == "react"` 时插到最外层，把文本 ReAct 轨迹转成标准 `tool_calls` |

**设计亮点**：`tool_mode` 支持 `auto / native / react` 三态。对于不支持原生 function calling 的模型，用最外层中间件做文本协议转换，**下面的限流、审批、Todo 同步、错误处理全部无需改动**——这是一次很干净的关注点分离。

### 容错细节

`orchestrator.py` 里有一段 `_pending_tool_call_ids`：处理「AIMessage 带 tool_calls 但对应 ToolMessage 缺失」的线程（崩溃或取消导致），因为 provider 会直接拒绝这种消息序列，所以调用前先修复。这类边界处理说明作者踩过真实的坑。

---

## 5. 工具系统

- **70 个 adapter**（`app/tools/adapters/`），覆盖：文件读写/编辑、代码（patch / lint / format / 测试 / 代码审查）、文档（Word / PPT / Excel / PDF / SVG / HTML / 图表）、检索（glob / grep / 目录树 / RAG / SQLite）、系统（终端 / 剪贴板 / 后台进程 / 定时任务 / 日历）、协作（子代理 / 计划 / 提问）。
- **注册机制**：`app/tools/registry.py` 是一个纯 dict，`@register_tool` 装饰器在 import 时完成注册。插件机制 `load_plugins_from(data/plugins/)` 让用户插件与内置工具**共用同一条执行管线**（审批、终端策略、超时、持久化），坏插件跳过不影响启动。
- **MCP 动态注入**：`mcp_manager.snapshot_tools()` 的产物包装成 `McpToolAdapter`，同样并入 registry。异常被吞掉（`MCP 不可用绝不影响本地工具`）。
- **Office 编辑闭环**：`office_backup.py` 编辑前自动备份，`undo_turn.py` 支持撤销，外部文件生成编辑副本不碰原件。

---

## 6. 数据层

`app/db/migrations.py` 定义 12 张核心表：

| 表 | 用途 |
| --- | --- |
| `projects` / `sessions` / `messages` / `message_parts` | 会话与项目组织（消息按 part 拆分） |
| `tool_runs` | 工具运行记录（带 retention 清理，启动时 prune） |
| `agent_todos` | 计划待办 |
| `scheduled_tasks` / `calendar_events` | 定时任务与日程 |
| `user_memories` | 长期记忆 |
| `session_summaries` | 会话摘要（滚动压缩，`cutoff_rowid` 推进） |
| `token_usage` | 用量统计 |
| `fts_state` | 全文检索状态 |

**检索不走向量库**：`fts.py` + `retrieval.py` + `fts_query.py` 实现自研 SQLite 倒排索引（词频 + doc_freq），零 embedding 模型、零外部依赖。这是刻意的取舍——用检索质量换「全栈本地化 + 免模型下载」。

### 记忆分层（design/022）

五层模型对齐 CoALA 术语，已实施一至五期：

- **L0 工作记忆** — 窗口内消息 + 滚动摘要（≥12 行且 ≥4 user turn 触发压缩）
- **L1 情景记忆** — `session_summaries`，可跨会话检索
- **L2 语义记忆** — `user_memories`，打分 = `w_sim·sim_norm + 0.15·importance + 0.05·confidence + w_recency·recency`，各量纲先归一化再加权
- **L3 程序记忆** — runbook / skill
- **L4 外部记忆** — RAG 倒排索引

设计原则里最值得记住的一条：**冲突处理的失败模式必须良性**——任何极性/相似度判定都是启发式、必然误判，所以误判代价必须是「保留两条」或「挂起待确认」，**永远不是静默错删**。为此把自动覆盖收紧为「高重复判定」，语义更新交由模型显式指定 `supersede_id`。

---

## 7. 前端

- **路由极简**：`createHashRouter` 只有 `/chat` 一条真实路由，`/` 和 `*` 都重定向过去；`pages/tasks` 作为任务页存在。桌面应用不需要多页路由，这个选择是对的。
- **状态管理用轻量 store**：`pages/chat/state/` 下 7 个 store（session / message / input / config / fullscreen / sessionModel / sessionEffort），共 277 行——没有引入 Redux/Zustand 之类的重方案。
- **SSE 事件协议**：`services/sse.ts` 定义了 11 类事件（`think` / `think_done` / `message` / `plan` / `plan_sync` / `todo_update` / `tool` / `subagent` / `scheduled_tasks_changed` / `calendar_events_changed` / `done` / `error`），前后端契约清晰，且带 dev 下的调试日志。
- **渲染能力**：react-markdown + Shiki（流式高亮）+ ECharts + Mermaid + 自绘 SVG，配套 `ChartBlock` / `GraphBlock` / `MarkdownView` / `FilePreviewPanel` 等组件。
- **零组件库依赖**：全部自研，换来完整的样式控制权，代价是组件维护成本。

---

## 8. 桌面壳

- Tauri 2，features：`tray-icon` / `image-png` / `macos-private-api`
- 平台能力：`window-vibrancy`（毛玻璃）、`tauri-plugin-global-shortcut`（全局快捷键）、`notification` / `updater` / `dialog` / `process`
- macOS 专有：`objc2-app-kit` / `objc2-foundation`，用于系统日历桥接与 `notify-rust` 原生通知
- 权限收敛在 `capabilities/default.json`，只开 `core:default` + 窗口拖拽 + dialog/notification/updater/restart，**没有放开任意文件系统或 shell 权限**——安全边界划得比较克制

---

## 9. 架构评价

### 优势

1. **进程隔离干净**：壳 / 前端 / 后端 / 存储四层职责单一，任一层可独立开发、测试、替换。
2. **本地优先落地彻底**：SQLite + 自研倒排索引 + 可选本地 llama-server，核心链路无强制云依赖；无 API Key 时自动降级演示 Agent，开箱可跑。
3. **中间件式 Agent 扩展**：限流、审批、Todo 同步、错误兜底、ReAct 协议转换全部外挂，业务代码零侵入。
4. **工程化配套完整**：98 个测试文件 / 19k 行测试 + 独立离线评测 harness（fake_model 驱动，不依赖真实 API）+ ruff + eslint + prettier + husky + lint-staged + i18n 抽取校验 + 签名公证脚本 + fastlane。
5. **文档即设计过程**：`docs/design/` 22 篇设计文档记录每次改造的动机与取舍（如 022 记忆架构 v2 的评审修订要点），可追溯性强。

### 风险与观察

| 观察 | 影响 | 建议 |
| --- | --- | --- |
| `docgen/` 21k 行、`tools/` 20k 行，两者合计占后端 65% | 单模块体量大，新人上手成本高 | 按输出格式（pdf/ppt/word/chart）与工具域继续细分，或抽出独立包 |
| 前端 `pages/chat` 单页承载 2 万行 | 会话页是绝对热点，改动风险集中 | 已按 components 拆分，可继续把「工具卡片渲染」抽成独立子域 |
| `tools/adapters/` 70 个文件平铺 | 目录膨胀，命名靠前缀区分 | 按域分子目录（doc / code / sys / web） |
| Agent 强绑定 LangGraph / LangChain 1.x | 框架版本升级会牵动 11k 行 agent 代码 | 依赖已锁到精确版本（`langchain==1.3.15` 等），升级需专项验证 |
| 无向量检索 | 语义召回弱于 embedding 方案 | 已作为明确非目标，若引入需评估「零外部依赖」原则 |
| `data/` 目录 78 个条目、`.venv39-backup` 等残留 | 仓库根目录有历史包袱 | 清理并补 `.gitignore` |

---

## 10. 一句话总结

Divine 是一个**架构纪律明显高于同类个人项目**的本地优先 AI 助手：用 Rust 壳解决桌面宿主问题，用 FastAPI sidecar 承载全部业务，用 LangGraph 中间件把横切关注点外挂，用 SQLite + 自研倒排索引守住「数据不出本机」这条底线。当前主要矛盾不在设计，而在**大模块（docgen / tools / chat 页）的体量控制**与**框架依赖锁定后的升级路径**。
