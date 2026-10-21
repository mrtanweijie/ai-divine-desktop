# 全面优化方案 v2（2026-10-16）

> 覆盖四维度：后端性能、Agent 能力、前端体验、架构治理。
> 原则：只出方案不改代码；每项含位置/证据/影响/修复思路。
> 上版（[010-optimization-analysis-20261009.md](010-optimization-analysis-20261009.md)）中 P0-2、P0-4 已确认完成，本文档剔除并补充架构与前端新发现。

---

## 一、架构问题（新发现，长期债务）

### A1. `api/chat.py` 上帝模块（1274 行）做着 agent 层的活 — CRITICAL
- **证据**：`stream_chat()`（chat.py:394-988）在路由层实现：附件提取、会话创建/标题生成、mention/skill 注入、本地 LLM 预处理与云端路由、取消事件注册表、surface-action 幂等、`retry_cloud()` 重写一遍同样的 SSE 循环（:988-1087）
- **影响**：会话/标题/取消逻辑不动 HTTP 层就无法单测；与 `orchestrator.py` 形成一个回合的两个"事实源"
- **修复**：抽 `app/chat/service.py`（纯编排）+ 瘦路由；API 层只验证和委托

### A2. agent ↔ api 层级倒置（循环依赖形状）— HIGH
- **证据**：`orchestrator.py:16` → `from ..api.terminal import ...`，而 `api/chat.py:17` → `from ..agent import run_agent`；`api/terminal.py` 持有有状态的 HITL 决策注册表
- **修复**：终端决策状态移入 `app/agent/decisions.py`，API 只留 HTTP 适配

### A3. 五条并行的聊天流实现 — HIGH
- **证据**：`api/chat.py stream_chat` + `retry_cloud`、`api/chat_local.py stream_local_chat`（367 行，自带 `_expand_choice_selection` 重复）、`orchestrator.py run_agent`（1002 行）、`agent/tasks/common.py run_agent_with_user_prompt`；错误信封 4 种风格（HTTPException / `{"detail"}` / `{"error"}` / `{"ok","message"}`）
- **影响**：持久化/SSE/审批语义最多要修 5 处
- **修复**：orchestrator 作为唯一管线 + `provider=local|cloud` 策略旋钮；删 chat_local 重复逻辑

### A4. CI 从不跑测试（1370 个测试不设关卡）— HIGH
- **证据**：`.github/workflows/build.yml` 只有 checkout/pnpm/pyinstaller/tauri，v* tag 触发；`divine-server/tests/` 1370 个测试函数零门禁
- **修复**：加 PR job：`pytest` + `pnpm typecheck`，过了才允许 release build

### A5. Sidecar 固定端口盲复用 — HIGH
- **证据**：`src-tauri/src/services/sidecar.rs:12`（8019 固定）；`spawn()` 端口开着就复用——任何占用 8019 的进程都被当作 sidecar（TcpStream connect 即健康检查）；旧 binary 更新后也会被"复用"；崩溃的 Tauri 留下孤儿 sidecar，下次启动照样复用
- **修复**：`GET /api/health` 身份握手（app-id + version）才允许复用；8019+ 端口池回退；pid 文件 + 陈旧 pid 清杀

### A6. 设置默认值散落三处 + schema 漂移 — MEDIUM-HIGH
- **证据**：`config.py:281-334`（~30 键）、`DEFAULT_* :31-35`、`schemas.py:207-230`；`local_llm_preprocess_*`、`ui_a2ui_enabled` 等不在 schema 里直接 `current.update(updates)` 写入；坏 settings.json `except: pass` 静默失败
- **修复**：单一 Pydantic `AppSettings` 模型作唯一默认值+校验源；`save()` 走模型往返

### A7. 错误封套 4 种风格 + 内部异常文本直漏前端 — MEDIUM-HIGH
- **证据**：REST 用 HTTPException（116 处）、未捕获异常 `main.py:113-135` 返回 `{"detail": str(exc)[:500]}`（原始 Python 异常、路径、SQL 直给客户端）、SSE 用 `error_event`、杂项 `{"error": str(e)}`
- **修复**：统一 `{code, message, message_key?}` 封套（JSON + SSE 同构）；traceback 只进日志

### A8. 文件预览端点路径穿越防护是前缀字符串比较 — MEDIUM
- **证据**：`api/files.py:59` `str(path).startswith(str(root))` 可被兄弟目录绕过（`/rootX` vs `/root`）；`pdf_preview`/`pptx_preview`/`document_preview` 接受任意绝对路径无约束
- **修复**：统一 `ensure_within(root, path)` 用 `Path.is_relative_to` + 共享 allowlist（workspace/output/projects）

### A9. Terminal：`shell=True` + 黑名单策略 — MEDIUM
- **证据**：`tools/scripts/terminal.py:132-134`；`bg_process.py:123` `create_subprocess_shell` 完全不过策略；黑名单可被 `r"m" -rf`、`bash -c` 绕过
- **修复**：`ask` 保持默认；`auto` 模式用 shlex/AST 白名单解析；bg_process 接入同一策略模块

### A10. Migration 无版本号、append-only 超级过程 — MEDIUM
- **证据**：`db/migrations.py:256-392` 单个 `init_db()` 每次启动重跑 ~15 个 PRAGMA 扫描 + 数据回填可能永久重复执行；无 `user_version`
- **修复**：编号迁移表 + `PRAGMA user_version` 游标；回填每个迁移 id 只跑一次

### A11. 前端上帝文件镜像后端 — MEDIUM
- **证据**：`chat/index.tsx` 1001 行、`useChatStream.ts` 874 行、`api.ts` 869 行（18 个路由单客户端）、`types.ts` 668 行；后端：`execution.py` 1260、`orchestrator.py` 1002、`local_llm.py` 924
- **修复**：chat 页按 feature 切片；api.ts 按资源模块拆

### A12. i18n 769 处内联中文兜底，三语言包手工同步 — LOW-MEDIUM
- **修复**：加缺失键 lint 脚本（used keys vs 三包对比）

---

## 二、后端性能（复核后剩余项）

### B1. 动态 system prompt 每次模型调用同步跑重活 — 最高优先
- **位置**：`app/agent/core/prompts.py:428-547`
- **证据**：每次 LLM 调用前同步执行：settings 读取、意图分类、工具历史查询、`build_project_context` FS 遍历、`list_todos`、记忆检索（≤500 行 + 纯 Python TF-IDF）+ `touch_memory_access` **写**、`list_messages` 全量历史、RAG、技能目录；10 轮工具回合重复 10+ 次，全在事件循环上
- **修复**：改 `async def`（LangChain dynamic_prompt 支持协程），或每回合算一次缓存进 `AgentRunContext`；`_history_backtrack_context` 仅关键词命中才加载

### B2. RAG 搜索 O(语料) + 0 命中触发全量重建
- **位置**：`app/rag_store.py:176-225`、`:131-173`
- **修复**：打分下推 SQL（FTS5 + norm 列）、chunk 内存缓存 mtime 失效、重建放后台线程带 TTL 防抖

### B3. 46/71 工具每次调用新开 Python 进程
- **位置**：`app/tools/base.py:114-152`
- **实测开销**：空脚本 40-70ms；`import openpyxl` 90-440ms；`import app.docgen.pdf` 270-575ms；`import weasyprint` ~1.0s
- **修复**：stdlib/轻量脚本走已有 `_run_in_process`；重型用持久 worker 池

### B4. FTS + 拼音 O(N²) 重建 —（原 P0-4，附精确链路）
- **位置**：`db/messages.py:67` → `db/fts.py:147-154`（`sync_session`）→ `:124-143`（`_sync_pinyin_rows`）
- **修复**：增量 upsert 只处理新消息行；`sync_session` 保留给重命名

### B5. 消息 parts N+1 加载（热门路径）
- **位置**：`db/history.py:342-348`（`load_session`）、`:449-450`（`load_session_page`）、`api/sessions.py:215`（export）
- **证据**：100 条消息页 = 100+ 次往返；`history_for_model` 已有正确的 `IN (...)` 批量模式可复用
- **修复**：批量 `WHERE message_id IN (...)` + Python 分组

### B6. chat.py 冗余 DB 往返
- **证据**：同一 session 查 3 次（`chat.py:217-293`）；全量 `list_messages` 只为判空（`:333`）；同步 `read_text()` 整个预处理原文（`:363`）；附件串行解析逐个 commit（`:387-467`）
- **修复**：顶部取一次复用；`SELECT 1 ... LIMIT 1`；`asyncio.to_thread` 限长读；`gather` + 批量事务

### B7. 每回合重建 ~60 个 pydantic model + StructuredTool + 技能扫描
- **位置**：`tools.py:125-154`、`core/schema.py:61-80`、`skill_lib/registry.py:19-73`
- **修复**：`@lru_cache` args model；StructuredTool memoize；refresh 加 mtime TTL

### B8. 冷启动 LangChain 0.64-1.02s
- **证据**：`import app.main` 0.82-1.02s；`core/__init__.py:24,33` 拉入 `.llm`/`.model_registry`
- **修复**：惯性 `__getattr__`；`run_agent` 移入 `stream_chat` 内导入

### B9. 缺索引
- `sessions(updated_at)`、`tool_runs(session_id, started_at)`、`user_memories(status, project_id)`、`messages(session_id, role, created_at)` → 加 migration

---

## 三、Agent 能力缺陷

### C1. `create_plan` 幽灵工具（计划优先功能自破）
- **位置**：`execution.py:268,281` 返回 "请先调用 create_plan"，但 `tools.py:133` 已剥离该工具；全部 prompt 已改写为 `write_todos`，唯漏此二处 + `sse.py:59`
- **修复**：改字符串（小时级）

### C2. 工具结果 stub 窗口固定 12 条，与 context_limit 脱钩 — 上下文丢失主因
- **位置**：`orchestrator.py:193`（`_TOOL_STUB_KEEP_RECENT = 12`）
- **证据**：`context_limit=50` 下用户以为保留 50 条，实际 N-1 轮读的文件/grep 结果 N 轮即丢 → 重读循环、SEARCH miss、过期编辑
- **修复**：`stub_zone_end = len - max(limit // 2, 12)`

### C3. `run_subagents` 有效不可达
- **证据**：工具（`tools.py:82`）和规则（`intent.py:71`）都被 `子agent|subagent|并行|run_subagents|同时调研|多来源` 锁定；945 行并行基础设施闲置，多源调研串行
- **修复**：移出 `_CONTENT_TOOLS` 常驻；`_SUBAGENT_RULES` 入 `ALWAYS_SECTIONS`

### C4. 意图回填 bug（`_PROJECT_WORKFLOW` 经常不注入）
- **位置**：`prompts.py:457` `if not intents:` — 有部分意图命中但缺 project 时不回填
- **修复**：`intents |= intents_from_tool_history(...)` 无条件并集

### C5. Session 摘要每回合重复插入
- **位置**：`orchestrator.py:551-563` 无 id `SystemMessage` → `add_messages` 追加不替换 → 每回合累积 ~400 token，挤占 stub 区
- **修复**：`id="session_summary"` 稳定 id 原位替换

### C6. 意图分类每回合跑两次
- **位置**：`orchestrator.py:460-467` vs `prompts.py:456-459`（第二次 `local_llm_enabled=False` 硬编码 → 结果可能不一致）
- **修复**：orchestrator 分类一次存 `ctx.intents`；`is_ready()` 缓存 2-5s

### C7. Todo 追踪按"每工具调用推进一条"
- **位置**：`execution.py:290-301`（每次工具调用 `_claim_next_todo`）、`db/todos.py:161-178`（run 结束强制 pending→skipped）
- **影响**：5 步计划 5 次任意成功调用（含 read）后显示 `5/5 完成` → 注入的计划进度块模型以为完成 → 过早收尾；跨 run 计划被清 → "继续"丢失计划
- **修复**：只有与 todo 关联（`todo_id` 字段）或 edit/build 类工具才推进；`settle_todos` 仅在无 pending/用户结束时执行

### C8. 跨文件替换缺失
- **修复**：新增 `replace_in_files`（regex + glob + dry-run diff 审批）

### C9. Git 面太小 + commit 恒 `add -A`
- **证据**：仅 status/diff/log/commit/revert；无 branch/merge/stash/checkout/blame/push
- **修复**：扩展 action + 精确 staging，走已有审批卡

### C10. terminal/run_tests 长任务无心跳
- **证据**：`progress_callback` 仅 `web_fetch_batch` 接入（`execution.py:1029-1033`）；600s 命令期间零输出
- **修复**：周期 `{"event":"tool","status":"running","elapsed":N,"tail":"..."}`；terminal 接入 progress_callback

### C11. 无浏览器验证能力
- **证据**：全项目无 Playwright/puppeteer；`ux_html`/`html_generate`/`presentation` 产出从未验证
- **修复**：`browser_snapshot`/`browser_click`（Playwright）+ workflow 加"启动 dev server 后截图自查"

### C12. 错误恢复从不换策略
- **证据**：超时自动重试仅 4 个只读工具（`tool_runtime.py:20-21`）；grep 0 命中不放松 pattern；terminal 超时不转 `background=true`；edit SEARCH miss 不退 `edit_lines`
- **修复**：超时附提示消息；SEARCH miss 自动附最近片段行号

### C13. 测试完整性 / 环境块 / 代码质量契约缺失
- `_PROJECT_WORKFLOW` 无"禁止改测试让它过"规则
- `project_context.py` 无 OS/shell/git branch/日期环境块
- 无风格一致性/依赖冻结/占位符纪律条款
- **修复**：各加一行（小时级）

### C14. 上下文窗口默认值危险
- **位置**：`state/compact.py:24` `_DEFAULT_CONTEXT_WINDOW = 1_000_000` — 未登记模型按 1M 算预算 → 真实 128k 模型硬 400
- **修复**：默认 128_000；优先读模型设置里的 `context_window`

---

## 四、前端体验（本轮新完成分析）

> 总评：明显优于典型 React chat UI（rAF 流缓冲、稳定前缀冻结、零 `any`、无 moment/lodash），问题集中在 app-shell 重渲染、错误边界、重连策略。

### F1. 全应用 0 Error Boundary — 一个坏渲染炸全 App — HIGH
- **证据**：grep `ErrorBoundary|componentDidCatch` = 0；脆弱叶子直接在 UI 树：Mermaid `dangerouslySetInnerHTML`（`MermaidBlock.tsx:262`）、i18n 插值 ~150 处、Date 解析、SSE payload `as unknown as` 强转（`useChatStream.ts:229,239,289`）无运行时校验
- **修复**：路由 + `MessageItem` 包 ErrorBoundary，fallback 显示原始文本

### C/F2. ChatPage 外壳随流式 60Hz 重渲染 — HIGH（长会话）
- **证据**：`messageStore.ts:17-32` 每 chunk 重写 Record；`chat/index.tsx:86` 派生 messages → ChatPage ≤60Hz 重渲染，拖出 **ChatInput（723 行未 memo）**、**SessionList/ProjectList（638 行未 memo，~20 props）**
- **修复**：流式消息面抽独立子组件（selector store）只订阅当前会话；memo ChatInput/SessionList

### F3. 请求层无重试/SSE 断线重连/去重 — MEDIUM-HIGH
- **证据**：`request.ts:88-132` 把原始 response body 当错误消息直显；`consumeSSE` 无中途恢复，TCP 抖动即整轮终止需手动重发；`done` 触发 `refreshSessions+refreshProjects+refreshWorkspace` 与 `sessions_changed` 事件并发重叠；非 SSE 请求无超时（挂死后 promise 泄漏，仅 StartupGate 做对了）
- **修复**：幂等 GET 加 retry(fn, backoff)；refresh 加 in-flight map；错误包 i18n 文案；默认 30s `AbortSignal.timeout()`

### F4. 切换无缓存会话时闪"开始新的对话"空态 — MEDIUM
- **证据**：`useSessionLoader.ts:94-99` 无缓存时 `setSelectedId` 后置，期间渲染 EmptyState
- **修复**：加 `loadingSession` 状态 + 骨架屏

### F5. SessionSearchModal 三合一 bug — MEDIUM
- **证据**：①`AbortController` 创建了但 `searchSessions` 无 signal 参数 → 从未真取消；②debounce timer 不在 unmount 清理 → 关闭后仍发请求 setState；③`dangerouslySetInnerHTML` 渲染服务端 snippet（`SessionSearchModal.tsx:129`）XSS 面依赖后端转义
- **修复**：signal 透传；unmount 清 timer；服务端返回 token-saf `<mark>` 结构

### F6. 会话列表全量渲染无虚拟化/分页 — MEDIUM
- **证据**：搜索默认视图渲染所有会话；`refreshSessions` 不带 project_id 过滤后又客户端过滤（`api.ts:30-33` 后端本来就支持）
- **修复**：传 project_id；列表截断/virtualize

### F7. 虚拟化重挂载触发 Markdown 重解析 + Shiki 同步高亮 — MEDIUM
- **证据**：`MessageList:253-278` 屏幕外项卸载，回滚重挂载全量重 parse + 高亮（`HighlightedCode.tsx:206-237` 自述 200-800ms）
- **修复**：高亮结果 LRU（key=messageId+lang+theme）；Markdown 树按 message id 缓存

### F8. FilePreview 每 2.5s 无条件轮询 — MEDIUM
- **证据**：`FilePreview.tsx:100-102` `setInterval(load, 2500)` 与 workspace:changed 监听叠加；每组件各开一个 Tauri listener
- **修复**：删轮询（监听已覆盖）或仅前台+可见时轮询；共享单一 change bus

### F9. `messagesBySession` 终身增长 — MEDIUM-LOW
- **证据**：仅会话删除时清；访问过就常驻内存（32MB toolOutputCache 有界，消息数组无界）
- **修复**：LRU 保留最近 ~10 会话

### F10. 强依赖未路由级懒加载 — LOW
- **证据**：`router.tsx:19-30` 单路由直引入；`ScheduledTasksPage`+`SkillsPage` 静态导入 ChatPage；重石（echarts/mermaid/x6/shiki 已动态 import，尚可）
- **修复**：`?view=` 视图 lazy()

---

## 五、修订后的执行批次

| 批次 | 内容 | 工作量 |
|------|------|--------|
| **速赢（字符串/一行）** | C1 幽灵工具 → C4 回填并集 → C5 摘要 id → C13 三条 prompt 契约 → C14 窗口默认值 | 小时级 |
| **体验高杠杆** | F1 ErrorBoundary → B1 prompt 异步化 → F2 流面抽离+memo → F3 重试/超时/去重 | 天级 |
| **性能高杠杆** | B3 工具进程复用 → B4 FTS 增量 → B2 RAG 下推+后台 → B5 parts 批量 → B9 索引 | 天级 |
| **能力补齐** | C2 stub 联动 → C3 subagent 解锁 → C8 replace_in_files → C9 Git 扩展 → C11 浏览器验证 | 天级 |
| **架构瘦身** | A1 chat 抽 service + A3 统一流管道（同一重构）→ A2 decisions 下沉 → A5 sidecar 身份握手 → A6 单一设置模型 → A7 统一封套 → A4 CI 门禁 | 天级 |
| **体验细节** | F4 骨架屏 → F5 Modal 三修 → F6-F10 → A8 路径含界 → A9 shlex 白名单 → A10 迁移版本化 | 天级 |
| **验证** | 每批跑 `evals/harness` 13 场景 + 前端 `pnpm typecheck` | — |

## 已完成项（勿重复投入）
- ~~SettingsStore mtime 缓存~~（config.py:269-279）
- ~~SQLite thread-local 连接复用~~（connection.py:44-62）
- ~~ToolMessage 截断压缩、SSE 截断、ReAct 上限~~（上版完成）
- ~~edit_files 逐文件提交、反馈环工具、批量工具、图标~~（此前完成）
