# 全面优化方案（2026-10-09）

> 来源：对 divine-server 后端性能、Agent 能力、前端体验的三维度深度分析。
> 原则：只输出方案，不改代码；每项标注影响级别、位置、修复思路。
> 执行节奏：改完每批跑 `evals/harness`（13 场景）对比通过率。

---

## 🔴 P0 — 高影响（直接卡顿 / 功能坏掉）

### P0-1. 动态 system prompt 每次模型调用都同步跑重活

- **位置**：`app/agent/core/prompts.py:428-547`
- **问题**：每次 LLM 调用前在事件循环上同步执行：
  - `settings_store.load()`
  - 关键词意图分类
  - 工具历史 DB 查询
  - `build_project_context` 文件系统 stat/walk
  - `db.list_todos` / `db.get_session` / `db.search_memories`（最多加载 500 行 + 纯 Python TF-IDF）
  - `touch_memory_access`（DB 写）
  - `_history_backtrack_context` → `db.list_messages(session_id)` 全量历史
  - RAG 搜索、技能目录
- **影响**：一个 10 轮工具调用的回合重复 10+ 次，冻结 uvicorn 单线程事件循环 → 所有其他会话的 SSE 心跳被卡；首个 token 延迟显著增加。
- **修复**：
  1. 改为 `async def`（LangChain `dynamic_prompt` 支持协程），或
  2. 在 `run_agent`（orchestrator）里每回合只算一次，缓存进 `AgentRunContext`，闭包读缓存；
  3. `_history_backtrack_context` 改为仅在关键词命中时才加载全量历史。

### P0-2. RAG 搜索每次全量加载 + 可能触发全量重建

- **位置**：`app/rag_store.py:176-225`（`search_workspace`）、`:131-173`（`index_workspace`）；触发链 `app/agent/rag/rag.py:44-49` → `prompts.py:510`
- **问题**：
  - 每次搜索 `SELECT` 全部 `rag_chunks` + `rag_terms`，逐 chunk `json.loads(tokens)` + Python 余弦循环 → O(语料) 每次模型调用，跑在事件循环上。
  - 0 命中且问题含 16 个常见中文关键词（"文件/内容/方案/之前"…）时，触发 `rag_index_workspace()`：`os.walk` + 读最多 500 文件 × 200KB + 分词 + INSERT，**全在请求路径内**，多秒卡死，且无 TTL/增量缓存（`DELETE` + 全量重建）。
- **修复**：
  1. 打分下推到 SQL（FTS5 + 存储 norm 列）；
  2. 按 workspace 内存缓存已加载 chunk 集合，mtime 失效；
  3. `index_workspace` 放后台线程 + mtime/TTL 防抖，绝不进 prompt 构建路径。

### P0-3. 每次工具调用新开一个 Python 进程

- **位置**：`app/tools/base.py:114-152`（`run` → `_run_subprocess_tool`）、`:161-168`、`:198-214`；已有的进程内替代 `:294-343`（`_run_in_process`）
- **问题**：71 个适配器中 **46 个**走 `subprocess.run([sys.executable, script])`。实测启动开销：
  - 空脚本 ~40-70ms
  - `import openpyxl` ~90-440ms
  - `import app.docgen.pdf` ~270-575ms
  - `import weasyprint` ~1.0s
  - 仅 6 个走 `_run_in_process`：`read_file`, `glob_files`, `grep_files`, `search_files`, `directory_tree`, `sqlite_query`
- **修复**：
  1. 轻量/stdlib 脚本（`calculator`, `notes`, `clipboard`, `memory`, `write_calendar`, `document_outline`…）全部改走 `_run_in_process`（已暴露 `run_tool(workspace, params)` 签名）；
  2. 重型依赖（office/PDF/SVG）用持久 worker 池（`multiprocessing.Pool`）预热；
  3. 至少把零散的廉价调用批处理。

### P0-4. 每条消息插入触发 O(N²) FTS + 拼音重建

- **位置**：`app/db/messages.py:67`（also `:39`）、`app/db/sessions.py:111` → `app/db/fts.py:147-154`（`sync_session`）→ `:124-143`（`_sync_pinyin_rows`）→ `:70-78`（`lazy_pinyin`）
- **问题**：`add_message` 删掉该 session 全部 FTS 行再重插，然后对最多 2000 字 × **每条**历史消息重跑 `pypinyin.lazy_pinyin`。200 条中文会话：每写一条消息就重新拼音化整个历史 → 写延迟随会话长度二次增长。
- **修复**：增量 upsert — 只 `INSERT INTO sessions_fts ... WHERE m.id = ?` 新消息行，只对新行做拼音；`sync_session` 保留给重命名场景。

### P0-5. `create_plan` 幽灵工具（Agent 被告知调用不存在的工具）

- **位置**：`app/agent/tools/execution.py:268`、`:281`；`app/api/sse.py:59`
- **问题**：工具结果返回 *"请先调用 create_plan 制定计划"*，但 `tools.py:133` 已把 `create_plan` 从工具集剥离，且 `prompts.py:475,523`、`compact.py:144,151` 全部把 `create_plan` 改写为 `write_todos`。模型收到指示调不存在的工具 → 幻觉调用报错 / 卡住。
- **修复**：
  1. `execution.py:268,281` 字符串改为 `write_todos`；
  2. `sse.py:59` `"tool": "create_plan"` → `write_todos`。

---

## 🟡 P1 — 中高影响（能力 / 体验短板）

### P1-1. 工具结果 stub 窗口固定 12 条，与 `context_limit=50` 脱钩

- **位置**：`app/agent/orchestrator.py:193`（`_TOOL_STUB_KEEP_RECENT = 12`）、`:192-193, 284`
- **问题**：所有 `ToolMessage` > 600 字符且不在最后 12 条消息内的，一律替换为 `[早期工具结果已清理…]`。用户设 `context_limit=50` 以为保留 50 条，实际上一轮读的文件内容 / grep 结果本轮即丢 → 重读循环、SEARCH 未命中、基于过期代码编辑。
- **修复**：`stub_zone_end = len(messages) - max(int(limit or 12) // 2, 12)`，让 stub 区随设置联动。

### P1-2. `run_subagents` 被窄关键词门控，几乎不可达

- **位置**：`tools.py:82`（`_CONTENT_TOOLS["run_subagents"]="subagent"`）、`intent/intent.py:71`（`CONDITIONAL_SECTIONS["subagent"]`）
- **问题**：工具与规则同时被 `子agent|subagent|并行|run_subagents|同时调研|多来源` 关键词锁定。945 行并行基础设施（隔离、写声明、diff、取消、信号量）闲置；多源调研串行烧轮次。
- **修复**：
  1. `run_subagents` 从 `_CONTENT_TOOLS` 移除（常驻）；
  2. `_SUBAGENT_RULES` 加入 `ALWAYS_SECTIONS`，或关键词扩为 `同时/分别/逐个/每个/三/五…` + prompt 规则 "≥3 独立子任务 → run_subagents"。

### P1-3. 意图回填 bug：`if not intents:` 导致部分命中时不回填

- **位置**：`app/agent/core/prompts.py:457`
- **问题**：仅当 `intents` **完全为空**时才跑 `intents_from_tool_history(...)`。若某个弱意图命中但 `project` 未命中 → `_PROJECT_WORKFLOW` 不注入，回填也救不回来 → 模型在没读到"探索→计划→编辑→验证→回滚→汇报"纪律的情况下就开始编辑。
- **修复**：`intents |= intents_from_tool_history(...)` 无条件并集；或把 `_PROJECT_WORKFLOW` 移入 `ALWAYS_SECTIONS`。

### P1-4. Session 摘要每回合重复插入（无 id）

- **位置**：`app/agent/orchestrator.py:551-563`
- **问题**：一旦有摘要，每次 run 都 `SystemMessage(content=summary)`（无 `id`）插入 graph input；LangGraph `add_messages` 对无 id 消息是**追加**而非替换 → 每回合累积一份 ~400 token 摘要，且落在旧消息之后而非头部，膨胀输入、挤占 12 条 stub 区。
- **修复**：`SystemMessage(content=..., id="session_summary")` 稳定 id → `add_messages` 原位替换。

### P1-5. 意图分类每回合跑两次

- **位置**：`orchestrator.py:460-467` vs `core/prompts.py:456-459`
- **问题**：orchestrator 带 settings 分类一次；prompt 构建器再分类一次（且 `local_llm_enabled=False` 硬编码默认）→ 结果可能不一致、重复查询 `intents_from_tool_history`；local/hybrid 模式每回合额外 HTTP 健康检查 + 最多 5s 阻塞。
- **修复**：orchestrator 分类一次存 `ctx.intents`，prompt 构建器读取；`is_ready()` 缓存 2-5s。

### P1-6. 无跨文件正则替换工具

- **位置**：无（缺失能力）
- **问题**：`edit_files` 要求逐文件精确 `search`；跨 40 文件重命名 API、换 import、迁配置键，模型必须 glob → 逐文件读 → 输出几十组 SEARCH/REPLACE → token 贵且易漏/不一致。
- **修复**：新增 `replace_in_files` 适配器（rg 式 regex + glob + `count`/dry-run 返回 unified diff 供审批），并在 `_PROJECT_WORKFLOW` 文档化。

### P1-7. Git 只有 5 个操作，`commit` 永远 `add -A`

- **位置**：`app/tools/scripts/git_tool.py`
- **问题**：仅 `status/diff/log/commit/revert`；无 branch/merge/stash/checkout/blame/cherry-pick/conflict/push。`git_commit` 恒 `git add -A` → 可能提交用户无关改动。
- **修复**：扩展 `_GitBaseAdapter` 的 `action`：`add(path)`、`branch`、`merge`、`stash`、`blame`、`checkout`；精确 staging；全部走已有 git 审批卡。

### P1-8. terminal / run_tests 600s 内零输出

- **位置**：`app/agent/tools/execution.py:1029-1033`（`progress_callback` 仅 `web_fetch_batch` 接入）
- **问题**：60-600s 命令只发 `running` 一次、结束发 `done` → 10 分钟构建看起来冻结，用户误判卡死并取消；无法提前从失败测试输出中止损。
- **修复**：`_execute_tool` 发周期 `{"event":"tool","status":"running","elapsed":N,"tail":"..."}` 心跳；terminal 适配器接入 `progress_callback` 透出尾部行。

### P1-9. 无浏览器验证能力

- **位置**：全项目无 Playwright/puppeteer
- **问题**：`ux_html` / `html_generate` / `presentation` 产出但从未验证（搜索确认 0 引用）。对比 OpenHands/Cursor，agent 无法确认 dev server 起来、页面渲染、bug 修好 → `_PROJECT_WORKFLOW` 的 verify 步仅静态（lint+tests），生成质量问题静默上线。
- **修复**：新增 `browser_snapshot(url, selectors)` / `browser_click` 工具（Playwright）+ workflow 加一行 "启动 dev server 后 browser_snapshot 截图自查 UI"。

### P1-10. Plan/todo 追踪按"每工具调用消耗一条"

- **位置**：`execution.py:290-301`（`_claim_next_todo` 每次工具调用都跑）、`:1182`（`_finish_todo`）、`db/todos.py:161-178`（`settle_todos` 结束强制 pending→skipped）
- **问题**：5 项计划在任意 5 次成功调用（含 read/grep）后显示 `5/5 完成`，但注入给模型的 `当前计划进度` 块就报"计划已完成" → 过早收尾；跨 run 计划被强制 `skipped` → "继续"丢失计划。
- **修复**：仅当模型关联了 `active`/`todo_id` 字段（或只对 edit/build 类工具推进）才 claim；`settle_todos` 仅在无 pending 或用户显式结束计划时执行。

---

## 🟢 P2 — 低影响（性能 / 规范）

| # | 问题 | 位置 | 修复 |
|---|------|------|------|
| P2-1 | 每回合重建 ~60 个 pydantic args model + `StructuredTool` + 技能目录扫描（`skill_registry.refresh` 无 TTL） | `tools.py:125-154`、`core/schema.py:61-80`、`skill_lib/registry.py:19-73` | `@lru_cache`（key=工具名+schema hash）、memoize StructuredTool、refresh 加 mtime/TTL |
| P2-2 | 缺索引 | `db/migrations.py:129-139,163-164,187-188,316,349` | 加 `idx_sessions_updated`、`idx_tool_runs_session_started`、`idx_memories_status_project`、`idx_messages_session_role_time` |
| P2-3 | N+1：每条消息单独查 parts | `db/history.py:346`、`:450`、`api/sessions.py:215` | 复用 `history_for_model` 的 `IN (...)` 批量模式 |
| P2-4 | 同一 session 查 3 次 + 全量 `list_messages` 只为判空 + 同步 `read_text()` 整文件 + 附件逐个串行 commit | `api/chat.py:217-293,333,363,387-467` | 顶部取一次复用；`SELECT 1 ... LIMIT 1`；`asyncio.to_thread` + 限长读；`gather` 并行附件 + 批量事务 |
| P2-5 | LangChain 冷启动 0.64-1.02s（包级 `__init__` 拉入） | `core/__init__.py:24,33`、`intent/intent.py:19` | `.llm`/`.model_registry`/`.local_llm` 惰性 `__getattr__`；`run_agent` 移入 `stream_chat` |
| P2-6 | 未知模型 `context_window` 默认 1,000,000 → 超窗 400 | `state/compact.py:24` | 默认 128_000；优先读模型设置里的 `context_window` 字段 |
| P2-7 | CJK token 估 1/char，预算高估 | `core/context.py:34-40` | CJK ×0.6-0.7 或预算路径用真 tokenizer |
| P2-8 | 无测试完整性规则（agent 可改测试让它过） | `_PROJECT_WORKFLOW` | 加一行 *"禁止修改/跳过/删除测试来让测试通过；认为测试有误先向用户说明"* |
| P2-9 | 无环境块（OS/shell/git branch/日期/运行时版本） | `project_context.py` | 追加 `平台=... shell=... 日期=... git=branch@HEAD [dirty]` |
| P2-10 | `_TOOL_LOCKS` 会话字典永不清理 | `tools.py:39` | run 结束时 `pop` |
| P2-11 | `retry_cloud` / 热路径 `settings_store.load()` 每次 deepcopy | `api/chat.py:836`、`prompts.py:431` | 每回合读一次存 `AgentRunContext`；或返回 frozen view |
| P2-12 | `list_sessions` 相关子查询 + export N+1 + 同步 PDF | `db/sessions.py:60-80`、`api/sessions.py:204-217` | last_message 改 `LEFT JOIN GROUP BY`/窗口函数；export 批量 parts |
| P2-13 | 意图关键词误报：`"lock"`⊂`"block"`、`"运行"`→open_app、ASCII 无词边界、`local_llm_mode` 默认 keyword | `intent/intent.py:424-426` | ASCII 用 `\b...\b`；歧义动词要求 ≥2 字中文上下文；默认 `hybrid` |
| P2-14 | 错误恢复从不换策略（grep 0 命中不放松、terminal 超时不转 background、edit SEARCH miss 不退 edit_lines） | `tool_runtime.py:20-21`、`middleware/debug_loop.py` | 超时附 hint "改用 background=true + bg_output"；SEARCH miss 自动附最近片段行号 |
| P2-15 | Prompt ~60% 是文档/样式规则，ALWAYS 段 ~1.5k token/次 | `prompt_sections.py` | 主题/封面表已条件注入；去掉 always-on 的 `_OPTIONS_CARD_RULES` 重复示例 JSON |
| P2-16 | `_should_ask_plan` 多数请求先来一轮确认往返 | `execution.py:219-269` | 消息含显式计划/直接执行标记时自动通过；`approval_mode != "ask"` 跳过 |

---

## 前端待补充分析

> 本次前端深度分析（ChatPage 重渲染、MessageList 虚拟化、MarkdownView 解析成本、bundle 体积、内存泄漏、搜索加载）任务中断，以下为已知线索，需补一轮：

- `src/pages/chat/index.tsx` — ChatPage 组件体量与状态粒度
- `src/pages/chat/components/MessageItem/` — 无关消息更新是否触发重渲染
- `src/pages/chat/components/MarkdownView/` — markdown 是否每次渲染重新 parse
- `src/services/` — 请求去重、错误处理
- SessionSearchModal — 是否全量加载会话列表
- 事件监听 / interval 清理

---

## 建议执行顺序

| 批次 | 内容 | 工作量 |
|------|------|--------|
| **速赢** | P0-5、P1-3、P1-4、P1-5、P2-8、P2-9（改字符串/一行逻辑） | 小时级 |
| **高杠杆** | P0-1 → P0-3 → P0-4 → P0-2 → P1-1 | 天级 |
| **能力补齐** | P1-6 → P1-7 → P1-9 → P1-2 | 天级 |
| **体验 & 规范** | P1-8 → P1-10 → P2-* 批量 | 天级 |
| **验证** | 每批改完跑 `evals/harness` 13 场景，对比 resolve-rate | — |

---

## 参考：已完成项（无需再做）

- ~~SettingsStore mtime 缓存~~ — `config.py:269-279` 已实现
- ~~SQLite thread-local 连接复用~~ — `connection.py:44-62` 已实现
