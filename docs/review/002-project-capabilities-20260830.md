# AI Divine Desktop 项目功能分析

> 编号：002 ｜ 类型：review ｜ 日期：2026-08-30 ｜ 状态：已归档（已被 025 复核修订）
> 版本：v1.0
> 方法：4 路并行代码勘察（agent 层 / API·DB·工具层 / 前端 / 桌面壳·工程化），全部结论附 `文件:行号` 证据
> 姊妹篇：《[003-optimization-feasibility-20260830.md](003-optimization-feasibility-20260830.md)》关注"还能怎么优化"，本文回答"项目现在有什么、怎么实现的"


---

## 0. 项目定位与总体架构

**Divine 是一个本地优先、隐私可控的桌面 AI 助手**：三层进程模型，SQLite 单库本地存储，不依赖任何云端自有服务（仅调用用户配置的 LLM API）。

| 层 | 技术 | 规模 | 职责 |
| --- | --- | --- | --- |
| 桌面壳 | Tauri 2 + Rust | 1,464 行 | sidecar 生命周期、托盘、剪贴板落盘、文件监听、系统日历桥接、更新器 |
| 前端 | Vite + React 19 + TS（自研组件，不用 AntD） | 21,339 行 | 聊天 UI、虚拟滚动渲染、会话/项目管理、设置、任务/技能页 |
| 后端 sidecar | FastAPI + SQLite + LangGraph | 41,744 行（agent 层 8,682 行） | Agent 编排、意图路由、62 个工具、RAG、调度器、本地模型管理 |

进程与端口：

```
Tauri 主进程 (lib.rs)
 ├─ WebView (React, hash 路由单页)          ←→  FastAPI sidecar 127.0.0.1:8019
 ├─ sidecar 监控线程（5s 探活，掉线重启）        ├─ llama-server 子进程 127.0.0.1:8016（按需）
 ├─ 托盘 / 关窗隐藏 / vibrancy                  ├─ 调度器线程（scheduled_tasks 轮询）
 └─ Rust commands ×21（粘贴落盘/文件树/git diff/日历/通知）
```

- sidecar 拉起：三级路径查找（dev → exe 旁 → resource），注入 `DIVINE_DATA_DIR`/`DIVINE_WORKSPACE_DIR`（`src-tauri/services/sidecar.rs:40-118`）；首轮 120s 宽限适配 PyInstaller 冷启动（`:166-210`）。
- 前端等待 sidecar 就绪：`StartupGate` 轮询 `/api/health`（800ms 间隔，`StartupGate/index.tsx:13-51`）。

---

## 1. 功能全景（按用户可感知能力）

| # | 能力域 | 代表功能 |
| --- | --- | --- |
| A | 对话与模型 | DeepSeek 流式对话、深度思考、多模型配置与按会话切换、本地 GGUF 模型、余额查询、云端重答 |
| B | 意图路由 | ~20 类意图识别（关键词+本地模型混合）、本地动作短路执行（截图/锁屏/开应用）、按意图裁剪工具集 |
| C | 工具系统 | 62 个工具：文件/代码/文档生成/网络/图示/系统/Agent 元工具；三级安全策略 |
| D | 计划与子代理 | write_todos 待办计划、plan_first 先方案后执行、高危审批中断、run_subagents 并行子代理 |
| E | 知识 | 本地 RAG（SQLite TF-IDF）、用户记忆（remember/forget）、SKILL.md 技能库（可执行+知识两类） |
| F | 文档生产力 | Word/Excel/PPT/Markdown 笔记、PDF 生成流水线（12 主题）、简历（7 主题）、SVG/ECharts/Mermaid |
| G | 任务与日程 | 定时任务调度、提醒通知、日历事件、macOS 系统日历双向同步 |
| H | 终端与代码 | WS 交互式终端+审批、git 工具族、format/lint/test、edit_files/edit_lines/apply_patch |
| I | 会话管理 | 项目化会话、FTS5 全文搜索、导出（md/pdf/text）、上下文用量、手动/自动压缩 |
| J | 桌面集成 | 托盘、关窗隐藏、粘贴截图/文件落盘、文件面板预览（HTML/SVG/PDF/图片/diff）、自动更新 |
| K | 工程化 | 4 平台打包矩阵、macOS 签名公证、GitHub Actions + Gitea fastlane 双发布链、i18n 三语 |

---

## 2. 对话主链路（最核心数据流）

```
ChatInput → POST /api/stream_chat (chat.py:84)
  → orchestrator.run_agent (orchestrator.py:134-583)
      1. 构建 AgentRunContext → 意图分类 classify_intents (intent/intent.py:363-438)
      2. 本地意图且置信度≥0.75 且非提问 → execute_local_action 短路返回 (orchestrator.py:282-339)
      3. _build_llm / _build_tools（按意图裁剪）/ _build_agent
      4. LangGraph astream_events 消费；外层 while 循环处理 interrupt→Command(resume) (orchestrator.py:355-480)
      5. _stream_agent_run (core/sse.py:326-384) 队列并行消费 token 流 + 工具事件
  → SSE 事件流 → 前端 services/sse.ts:49-103 手写解析 → messageStore → MessageList 渲染
```

**SSE 事件协议**（约 13 类）：`message/think/think_done`（core/sse.py:249-313）、`plan`（middleware/middleware.py:33）、`tool`（含 status=confirm 审批复用，core/sse.py:24-217）、`todo_update`、`subagent`（subagents.py:747）、`scheduled_tasks_changed`/`calendar_events_changed`（execution.py:830/887）、`compacted`（orchestrator.py:570）、`done/error/cancelled`。

**DSML**：自研流式工具调用标记解析器，容忍模型输出的 "｜DSML｜" 噪声 token，正则增量解析 `<invoke><parameter>` 块（llm/dsml.py:9-40）——这是不依赖 provider 原生 function calling 的兜底通道。

**中断与审批**：`HumanInTheLoopMiddleware`（tools/tools.py:183-196）+ 渲染协议（core/sse.py:19-217）支持 plan/plan_choice/terminal/external_file/git/skill/subagents_write 等中断类型；orchestrator 收到中断后 `asyncio.wait_for(180s)` 等用户决定（orchestrator.py:389-476）。

---

## 3. 各子系统实现要点

### 3.1 意图路由（路由即省钱）

- `classify_intents`：关键词匹配为主，可选本地模型 classify（keyword/local/hybrid 三模式，orchestrator.py:178-199）；历史上下文可回补意图但排除本地动作类，防"已截图保存"污染（intent.py:310）；`intents_from_tool_history` 用工具记录回补短指令（intent.py:441）。
- 路由后三个差异化行为：①本地动作短路（不调云端）；②系统提示词按节裁剪注入（orchestrator.py:460-486）；③**工具集裁剪**——按意图只挂相关工具 schema，省 47% token（tools/tools.py:39-62、91-94，对应提交 955676c）。
- 保护机制：提问句式 `is_question_like` 防止"什么是截图"被误执行本地动作（intent.py:352-360）。

### 3.2 工具系统（62 个工具，双执行通道）

- 注册：`ToolRegistry` + `@register_tool`（registry.py:86），adapters/ 51 个文件静态导入触发注册；支持用户插件 `data/plugins` 热加载（main.py:33-35）。
- 执行双通道：重型工具走子进程脚本 `scripts/*.py`（base.py:126-161）；轻量 IO（read_file/grep/glob/search/directory_tree/sqlite_query）走进程内 `text_file_io`（base.py:304-323，对应提交 a43ccb3）。
- 安全：`terminal_policy.py` 三级 safe/confirm/block——git 只读子命令白名单（:36）、硬拦截 `rm -rf/shutdown/dd` 等（:56）、curl/wget 一律 confirm（:80）。
- 工具分组：文件 IO（read/write/edit_files/edit_lines/apply_patch/move/grep/glob…）、代码（terminal/git 族/format/lint/run_tests）、文档（word/spreadsheet/presentation/notes/pdf_generate/pdf_render/pdf_split_merge/ux_html）、网络（web_search/web_fetch/web_fetch_batch，JS 页浏览器兜底）、图示（draw/edit/describe_svg、svg_to_png、mermaid_export、generate_chart、image_generate/resize）、系统（clipboard/notes/remember/sqlite_query/kill/bg_status）、Agent 元工具（create_plan/run_subagents/schedule_task/write_calendar/load_skill/install_skill/discover_importable_skills/migrate_skill）。

### 3.3 计划、审批与子代理

- `create_plan` 已跳过注册（tools/tools.py:87-88），实际用 `write_todos` + TodoSyncMiddleware 落库并发 `plan` SSE；plan_first 模式下其他工具被拦截提示先出方案（execution.py:118-122）。
- `run_subagents`（tools/subagents.py）：2–8 个独立任务，写任务须声明互不重叠的 write_paths（:244-255）；含写/终端的批次先整体审批（execution.py:138-222）；每任务独立 agent+受限只读工具集+独立提示词，`Semaphore(≤4)` 并行（:755-769）；写操作前后快照生成 diff（:389-466）；结果汇总 JSON 回主代理。

### 3.4 知识三件套：RAG / 记忆 / 技能

| 子系统 | 实现 | 关键局限 |
| --- | --- | --- |
| RAG | 自研 SQLite TF-IDF 余弦检索（rag_store.py:68-230），定长 1000 字符分块，英文词+中文单字/bigram | **无 embedding 模型**，纯词面匹配；agent/rag/rag.py 每轮自动取 top3 注入提示词 |
| 记忆 | `user_memories` 表 + remember/forget 常驻工具 + TF-IDF 检索 top5 注入"已知用户信息"块（core/prompts.py:66-100） | 同样词面匹配，无语义召回 |
| 技能 | SKILL.md 格式，knowledge/executable 两类（skill_lib/registry.py:13）；可执行技能刷新后注册为动态工具（tools/tools.py:82,110）；GitHub/Gitee 安装、`.claude/skills` 等迁移；前端 skills 页管理 | 无市场/在线浏览（前端只做本地管理） |

### 3.5 文档生产力（差异化最强的一块）

- **PDF 流水线**：intent 解析 → recipes 配方（report/travel 等）→ content LLM 生成 → design_rules 场景→主题/配色/封面确定性决策 + design_enforcer 校验回退 → engine 编排（pdf_tool/）；渲染 WeasyPrint 优先、ReportLab 兜底（pdf_renderer/renderer.py:1-14）；12 套 CSS 主题 + 旅行 HTML 模板，前端可主题预览（`/pdf/themes`、`/render-preview`）。
- **简历**：7 套主题（boss_zhipin/creative/finance/linkedin/minimal/professional/kami），CSS 变量替换 + 主题专用 renderer（resume_themes/）。
- Office 三件套 + Markdown 笔记；SVG 全链路（生成/编辑/描述/转 PNG）；ECharts 图表内联；ux_html 按用户选择的风格生成 UX 页面。

### 3.6 任务、日程与通知

- 调度器：main.py lifespan 启动，逐 tick 轮询 `scheduled_tasks.next_run_at`，到期执行提醒或 `_run_agent_task`（scheduler.py:134）——**Agent 定时任务**（到点让 Agent 干活）是隐藏亮点。
- 日历：`calendar_events` 表 + Rust 侧 osascript JXA 写 macOS 系统 Calendar（system.rs:111-165），按 summary+时间±60s 匹配删除；`calendar_synced` 字段记录同步态。
- 提醒：Rust 原生通知 + 前端轮询双通道。

### 3.7 本地模型（隐私卖点）

- `LocalLLMManager` 以 subprocess 拉起 llama-server（127.0.0.1:8016，OpenAI 兼容），二进制查找 用户数据目录→PyInstaller 部署→`bin/<target>/llama/`→PATH（core/local_llm.py:138-170,355-374）。
- 模型注册表：Qwen2.5-0.5B/1.5B/3B、Phi-3-mini、gemma-2-2b 的 GGUF，HuggingFace 直链+镜像下载（core/model_registry.py:59-116,341-351）；API 暴露 status/hardware/recommended/mode/start/stop/install/uninstall/download_progress（api/local_llm.py:55-301）。
- 本地模型三用途：意图分类、历史摘要（compact 优先走本地）、长文本预整理（preprocess）；聊天侧 "local" 虚拟模型解析到 llama-server（core/llm.py:44-51）。**按需启动，不常驻**（与优化清单"常驻"假设相反）。

### 3.8 上下文工程（长会话不爆)

| 机制 | 触发 | 行为 |
| --- | --- | --- |
| compact 自动压缩 | 每轮后"新增≥12 行且≥4 轮"（state/compact.py:66-67,206-216） | 优先本地模型摘要，存 `session_summaries`，下轮以 SystemMessage 重注入；发 `compacted` SSE |
| preprocess 长文整理 | 显式"整理+这段"双命中或 >800 token（middleware/preprocess.py:98-108,214-227) | 本地小模型分块 2000 字×5 整理，原文落盘 attachments，失败降级云端 |
| project_context | 会话命中项目 | 注入 README/依赖/2 层目录树 ≤1800 字，TTL 300s 缓存（middleware/project_context.py:196-258） |
| 历史组装 | 每轮 | db/history.py `history_for_model` 组装模型上下文 |

---

## 4. 前端功能全景

- **单路由 + 视图切换**：只有 `/chat` 一个路由，tasks/skills 是 `?view=` 条件渲染（pages/chat/index.tsx:160-162,1207-1215）；布局 = TitleBar + SessionList 左栏 + 聊天主区 + FilePreviewPanel 右栏（:1131-1310）。
- **聊天渲染管线**：`@tanstack/react-virtual` 虚拟滚动（estimateSize 140 + measureElement + 底部跟随 + 向上翻页加载，MessageList/index.tsx:49-121）；Shiki v4 流式增量高亮（35+ 语言按需单例，@shikijs/stream）；Mermaid 动态 import + LRU 缓存；HTML/SVG 代码块 iframe/内联预览（WebPreviewBlock）；ECharts 由工具结果转 option 动态渲染；工具卡片 ToolStatusCard（933 行，内含 terminal 审批交互）；深度思考 `<details>` 折叠+流式预览；本地模型回答可一键"云端重答"（useChatStream.ts:461-527）；MarkdownView/MessageItem 已加 memo（最新提交 0432d68）。
- **会话与项目**：项目化会话（置顶/排序/图标）、FTS 搜索弹窗、md/pdf/text 三格式导出、上下文用量展示、按会话记忆模型选择（localStorage）。
- **文件面板**：文件树懒加载、git DiffView、HTML/SVG Web 预览、图片/PDF 走 Rust `get_binary_preview` dataUrl、文件改动 watch + "接受变更"。
- **设置**：basic（用户名/深度思考默认/reasoning_effort/context_limit/语言/主题）、model（多模型增删+各自 Key）、local（本地 LLM 安装/启停/模式，611 行）、about（版本/更新）；每 tab 只保存自己的字段避免覆盖 Key（SettingsModal/index.tsx:123-140）。预置 DeepSeek/小米 MiMo/GLM 提供商列表（config/providers.ts）。
- **状态管理**：全自研 hooks store（messageStore 按会话缓存 + streamingSessions 支持多会话并发流，messageStore.ts:12-81）；i18n 三语 zh-CN/zh-TW/en（zh-TW 由 opencc-js 脚本生成）。

---

## 5. 桌面壳与工程化

- **Rust 命令 ×21**：sidecar 控制、粘贴落盘（文本 2M 字符/图片 10MB/文件 100MB 限制，哈希去重，paste.rs）、系统打开（文件/Finder/URL）、原生通知、日历桥接、文件树/git diff/二进制预览/watch（基于 notify crate）。
- **窗口行为**：关窗→隐藏到托盘（全屏时先退全屏，lib.rs:68-81）、托盘左键唤起、macOS vibrancy + 全屏事件监听（objc2）、无全局快捷键/开机自启/single-instance。
- **自动更新**：Tauri updater + GitHub Releases `latest.json`（tauri.conf.json plugins.updater）；`publish-macos.sh` 产出 tar.gz+minisign 签名+清单并上传。
- **打包矩阵**：build-sidecar.sh 支持 darwin-arm64/x64、win32-x64、linux-x64，自动下载对应 llama-server 并补 dylib；PyInstaller onefile + ~160 hiddenimports；**不做 fat binary**（PyInstaller onefile lipo 必崩，故 Gitea fastlane 链路出双架构独立 DMG，Fastfile:19-30）。
- **安全配置**：CSP 限 connect-src 127.0.0.1:8019 与 api.deepseek.com；capabilities 仅 main 窗口最小权限；Entitlements 含 JIT/未签名内存（PyInstaller 需要）。
- **测试**：后端 42 个测试文件（工具/PDF/意图路由/LLM/基础设施全覆盖）；**前端零测试**（与优化清单结论一致）。

---

## 6. 数据模型

SQLite 单库 `ai_workspace.db`，11 张表 + FTS5（db/migrations.py）：

```
projects ─< sessions ─< messages ─< message_parts
              │              └─< tool_runs
              ├─ approval_mode / plan_mode / locale
              ├─< session_summaries（compact 摘要）
              └─< agent_todos（计划待办）
scheduled_tasks ─< calendar_events（system_event_id / calendar_synced）
user_memories（TF-IDF 检索）    token_usage（用量统计）
sessions_fts（FTS5，rebuild_fts5 全量重建——旧触发器有 bug 已弃用，migrations.py:164,183）
```

数据落点：开发态 `divine-server/data|workspace`；安装版由 Rust 注入系统应用数据目录（sidecar.rs:111-118）。

---

## 7. 功能缺口与风险清单（按优先级）

| 级别 | 问题 | 证据 | 说明 |
| --- | --- | --- | --- |
| 🔴 高 | API Key 明文存储 | `data/settings.json` 存 api_key（0644），keyring 未装 | 已在优化清单确认为真实问题（8b9e24c 仅收紧了文件权限） |
| 🔴 高 | LangGraph checkpointer 是进程内存态 | tools/tools.py:29 `InMemorySaver` | sidecar 重启后进行中会话的工具调用状态丢失（已有 `_has_incomplete_tool_calls` 检测缓解，orchestrator.py:58-78） |
| 🟡 中 | 审批等待 180s 硬超时 | orchestrator.py:389-476 `asyncio.wait_for(180)` | 用户关窗/离开即超时拒绝；无持久化待审批队列 |
| 🟡 中 | RAG/记忆均为词面匹配 | rag_store.py:192-230 | 无语义召回，中文长文档检索质量受限；可接本地 embedding 模型（llama-server 已具备能力） |
| 🟡 中 | 固定端口 8019 + 无 single-instance | services/sidecar.rs:11-12 | 多开会复用旧 sidecar（数据目录一致时无害，但多版本并存会串） |
| 🟡 中 | FTS 搜索全量重建索引 | db/migrations.py:164 `rebuild_fts5` | 会话量大后搜索延迟线性增长 |
| 🟢 低 | 前端零测试 | — | 核心渲染管线（sse.ts/MessageList）回归靠手测 |
| 🟢 低 | 无全局快捷键/开机自启/单实例 | Cargo.toml | 桌面助手类产品的常见预期功能 |
| 🟢 低 | 私有符号即事实公共 API | core/__init__.py:1-60 re-export `_` 前缀函数 | 拆包过渡方案，长期应收敛 |

---

## 8. 与《优化清单可实施性分析》的对照更新（2026-08-30）

昨晚的可行性分析给出 agent 层拆包 Phase 0-5 计划，**该拆包已在工作区完成但尚未提交**：

- `git status` 显示 `app/agent/{constants,context,llm,local_llm,model_registry,prompt_sections,prompts,schema,sse}.py → core/`、`intent.py/local_actions.py → intent/`、`middleware*/preprocess/project_context → middleware/`、`rag.py → rag/`、`compact/persistence/plans → state/`、`execution/... → tools/` 全部 rename 已暂存，orchestrator.py 留顶层——与建议分组一一对应。
- `core/__init__.py:1-60` 集中 re-export 私有符号兼容旧 import，属过渡 shim；测试迁移情况待提交前回归（41 个测试文件中 14 个直接 import `app.agent.*`）。
- **提交前建议**：跑全量 `pytest` 回归 + 确认 PyInstaller spec 的 hiddenimports 是否需要同步包路径。

---

## 9. 一句话总结

Divine 已经是一个**功能密度很高的本地 AI 工作台**：对话/工具/子代理/RAG/记忆/技能/文档生成/定时任务/桌面集成九大能力闭环，62 个工具与三级安全策略是主资产；当前短板集中在**持久化健壮性**（checkpointer 内存态、审批窗口、API Key 明文）与**检索语义化**（RAG/记忆纯词面匹配），前端测试为空白。
