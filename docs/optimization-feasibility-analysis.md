# AI Divine Desktop 优化清单 · 可实施性分析

> 版本：v1.0
> 日期：2026-08-30
> 状态：📋 分析完成（本轮未实施代码）
> 方法：5 路并行代码勘察（agent 耦合度 / 工具与安全 / 数据库 / 前端渲染 / LLM 与 SSE），全部结论均附 `文件:行号` 证据

---

## 0. 总览：清单假设与现状的差异（重要）

原始优化清单基于对项目的部分假设，勘察后发现 **多项"建议"实际已实现**。逐项落地前必须先对齐现状：

| 清单建议 | 现状 | 结论 |
|---|---|---|
| 2.1 消息查询改游标分页 | **已实现**：`db/history.py:243-316` keyset 分页（rowid 游标）+ `GET /sessions/{id}?before_id=` + 前端 `index.tsx:300-338` 向上翻页 | 无需再做；剩余价值在 `history_for_model` 全量扫描 |
| 1.2 引入 Zustand/Jotai | 无 zustand/jotai，但现有 `messageStore.ts` 用 ref 缓存刻意规避重渲染 | **不建议近期迁移**（风险中高、收益不明确） |
| 2.3 虚拟滚动优化 | **已实现**：`@tanstack/react-virtual` + measureElement 动态测高 + 自动跟随 + 向上加载 + 缩略图 | 无需引入，仅可微调 overscan |
| 2.3 代码高亮按需加载 | **已实现**：Shiki v4 动态 import + 流式增量高亮（37 语言单例） | 已达标 |
| 2.2 意图分类缓存 | 意图识别是**纯本地关键词匹配**（零 LLM 成本）；唯一 LLM 调用是本地模型 classify（`_classifier_cache` 预留未用） | 只缓存 classify，缓存关键词检测无意义 |
| 2.2 本地模型常驻 | 现状即"启动后常驻，仅退出时停止"（`main.py:47-52`） | 反向优化：建议加**空闲超时自动停止** |
| 5.2 终端命令加超时 | **已有三层超时**（tool_runtime wait_for / base.py subprocess timeout / 脚本层 clamp） | 缺口是 in-process 工具超时线程泄漏 |
| 3.1 会话搜索增强 | **已实现**：FTS5（sessions_fts）+ 搜索 UI（SessionSearchModal） | 问题是"每次搜索全量 rebuild 索引" |
| 3.1 会话导出 | **已实现**：`GET /sessions/{id}/export`（markdown/pdf/text） | 无需再做 |
| 4.1 types.ts 用 any | **零 any**（469 行），全项目仅 8 处 any | 剩余价值在 SSE 类型黑洞 |
| 5.1 API Key 加密 | **确认明文**：`data/settings.json` 存 api_key（0644），keyring 未安装 | 真实问题，值得做 |
| 4.3 前端测试 | **完全没有**（后端有 41 个测试文件） | 从零搭建 |

---

## 1. 架构优化

### 1.1 后端模块解耦（agent 层拆分）

**可行性：可行，但成本主要在测试迁移**

- `app/agent/` 26 个模块、8,481 行。内部依赖基本是 DAG，但有 **3 处环风险**：
  1. `intent ↔ compact` 惰性环（intent.py:494 ↔ compact.py:115）
  2. `prompts ↔ react` 惰性环（prompts.py:336）
  3. `agent ↔ api.terminal` 潜在顶层环（chat.py:14 顶层导 run_agent，execution.py:14 / orchestrator.py:16 顶层导 api.terminal——当前仅因 `api/__init__.py` 为空才不断裂，**最脆弱**）
- 依赖枢纽：`schema.py`（163 行）与 `context.py`（44 行）各 6 条内部入边，是天然 core 层，拆包必须**先落位**。
- 对外 API 面很小：仅 6 个模块被 app/ 引用（`run_agent`、local_llm、preprocess、llm、compact、model_registry），26 条 import 中仅 1 条顶层导入，其余全是惰性导入。
- **最大成本**：14/41 个测试文件（34%）、53 行 import 直接导入 `app.agent.*`，且大量引用下划线私有符号（`_build_tools`、`_stream_agent_run` 等），拆包后路径全要迁移。

**建议分组**：intent/（intent+local_actions）、rag/（rag，纯叶子）、tools/（tools+tool_runtime+execution+react+subagents+interrupts）、middleware/（middleware+preprocess+project_context）、state/（persistence+plans+compact）、core/（context+schema+constants+prompt_sections+prompts+llm+local_llm+model_registry+sse）、组合根留在 agent/ 顶层（orchestrator）。

**建议顺序**（每步回归面控制在 1–3 个引用方）：
- Phase 0：拆纯叶子（rag / project_context / middleware / local_actions / interrupts / tool_runtime / plans）
- Phase 1：破除 2 个惰性环（estimate_tokens 下沉 core；REACT_FORMAT_PROMPT 归属 core）
- Phase 2：拆 tools 大组；Phase 3：intent/rag；Phase 4：state 组；Phase 5：core 归拢
- 贯穿：execution/orchestrator 的 `..api.terminal` 改惰性导入

**风险**：中。命名冲突（新 `agent/tools/` 与现有 `app/tools/` 同名）、私有符号即事实 API、local_llm 惰性导入模式必须保留（否则启动即拉起子进程逻辑）。
**改动量**：3–5 人日（含测试迁移；可加 re-export shim 过渡）。

### 1.2 工具注册中心插件化

**可行性：可行，改动量中等**

- 现状：`registry.py` 集中式 `ToolRegistry` + `@register_tool` 装饰器（54-65 行），`adapters/__init__.py:1-66` 静态 import 触发注册（60 个工具、53 个 adapter 文件）。
- **PyInstaller 硬约束**：`divine-server.spec` 的 hiddenimports 逐模块列出 adapter（133-157 行）——`entry_points` 方案不可用（importlib.metadata 入口点不会被收集）。
- 建议：registry 增加 `register_module/unregister`；改为"目录扫描 + 注册表解耦"，保留 `@register_tool` 作插件 API；PyInstaller 侧用 `collect_submodules` hook 或 build-sidecar.sh 扫描生成 hiddenimports。
- **动态卸载在会话内不可生效**（StructuredTool 已注入 LLM schema），需"下一会话生效"语义。
- 风险：插件 = 任意代码执行面（同权限执行终端/读写路径），需来源校验或定位为"本地开发者插件"；`_CONTENT_TOOLS` 意图裁减白名单是名称硬编码，插件工具默认常驻注入（token 成本上升）。
- 改动量：2–4 人日（含三平台打包验证）。

### 1.3 Sidecar 通信优化（gRPC / MessagePack）

**可行性：不建议做（收益低、成本极高）**

- 现状：Tauri（Rust）只负责 spawn + 健康检查（`services/sidecar.rs`，TCP 300ms 探测），**实际通信是前端浏览器直接 fetch HTTP/SSE 到 127.0.0.1:8019**（`request.ts` + `sse.ts`）。
- 换 gRPC：浏览器端需要 gRPC-Web 网关或连 Tauri IPC 转发——架构性改造，且当前瓶颈不在序列化（消息负载已被 `persistence.py _frontend_truncate` 深度截断，见 `docs/agent-optimization-summary.md` §2.4）。
- 换 MessagePack：浏览器 fetch 无法直接消费 MessagePack 流，同样需要前端解码层。
- **结论**：JSON 序列化不是当前性能瓶颈（SSE 负载已压缩、数据量小）；如未来出现大文件/高频 IPC 需求，优先做 SSE 批量发送（见 2.2）而不是换协议。

---

## 2. 性能优化

### 2.1 数据库层面

#### PRAGMA cache_size（快速收益项）

**可行性：可行但当前收益≈0（预防性一行）**

- 现状：`connection.py:34-41` 已设 WAL + synchronous=NORMAL + busy_timeout(10s)，**无 cache_size/temp_store/mmap_size**。
- 实测：全库仅 **0.5 MB**（page_count=134），默认 cache_size=-2000（2 MB）已是库的 4 倍；设 -64000（64MB）是库的 122 倍。
- ⚠️ 注意：per-connection PRAGMA（线程缓存连接，uvicorn 线程池 40 条 × 64MB = 2.5GB 潜在内存浪费）。
- 建议：可顺手加 `cache_size=-16000`（16MB，折中）+ `temp_store=MEMORY`；mmap_size 不必。改动 1–3 行于 `connection.py:38-40`。**价值要等库长到几百 MB 才显现**。

#### 消息查询分页

**已实现**（游标分页闭环），见 §0。剩余优化点：
- **`history_for_model`（模型侧历史）全量扫描**（`history.py:57-69`）：`SELECT * FROM messages WHERE session_id=? ORDER BY created_at ASC` 全量取回再切片——**每轮对话都执行**（chat.py:320、chat.py:651、scheduler.py:156、compact.py:184）。建议改 rowid 反向 LIMIT 尾部窗口化。改动集中在单函数 <30 行，前端零改动，有 `tests/test_db_repositories.py:62-86` 兜底。
- `load_session` 全量：`index.tsx:346`、`useChatStream.ts:244` 无 options 调用——可顺手传 limit 只取 tool_runs。

#### FTS5 索引维护

**基础已存在，问题是"每次搜索全量重建"**

- `sessions_fts`（会话级聚合）已建（`migrations.py:154-161`）；无触发器（早期触发器有历史 bug 已弃用，`migrations.py:181-198`）。
- **缺陷**：`sessions.py:157-162` **每次搜索先 `rebuild_fts5()` 全量重建**（DELETE + INSERT 全表）——O(全部消息) 且占唯一写锁。当前 53 条无感，消息上万后每次搜索都是全表写。
- 建议：去掉每次 rebuild → 启动时 `init_db` 重建一次 + 水位增量（记录 max(rowid) 只插新行）。改动 <30 行，集中在 migrations/sessions。
- `PRAGMA optimize`：挂 `init_db` 末尾 1 行即可（增量 analyze，3.18+ 支持，当前 3.53）。
- **无任何测试覆盖 FTS5/search**，改动需补测试。
- 可选新功能：消息级 FTS5（当前只能定位到会话+snippet，不能跳转具体消息）——后端中 + 前端中，触发器有历史坑。

#### 索引现状

- messages 只有 `idx_messages_session(session_id)`，**无 `(session_id, created_at)` 复合索引** → `list_messages`/`history_for_model` 有 `USE TEMP B-TREE FOR ORDER BY`（实测 EXPLAIN QUERY PLAN）。
- 建议加 `CREATE INDEX IF NOT EXISTS idx_messages_session_created ON messages(session_id, created_at)`（可选含 role 使 last_message 子查询走覆盖索引）。1 行幂等迁移，WAL 在线建，低风险。
- 当前数据规模下为预防性收益。

### 2.2 LLM 调用

#### SSE 流式输出批量发送（快速收益项）⭐

**可行性：高，前端零改动**

- **关键事实**：前端 `message` 事件是 **content 增量、前端自己累加**（`useChatStream.ts:126` `content: message.content + content`）。因此后端把多个 token 拼成一个大 content 增量发**一个**事件，前端累加结果完全不变——**不需要前端配合**。
- 现状：每 token 一个 SSE 帧（agent/sse.py:264/276/289/300；本地直连 chat.py:1494），从 LLM 到 HTTP 全程无攒批。
- 建议：攒批放 `chat.py` 的 `generate()` 出口（L1 汇聚点，统一覆盖云端/本地/QA 全路径，不影响 scheduler）：
  - 包 yield 包装器：`message`/`think` 进 buffer，其余事件（tool/plan/done/error）立即直通；
  - buffer 按 50ms 定时器 + 字符阈值（64-128）双触发 flush；**首个事件立即 flush**（避免"卡 50ms 才开始输出"）；
  - **取消/异常/finally 三处必须 flush**（避免丢尾字）；
  - buffer 按 generate() 实例闭包隔离，天然支持多会话并发。
- 改动量：40-60 行（集中 `api/chat.py`，不动 agent/sse.py）。
- 收益：React 渲染次数与网络包数同比例下降（每次 message 事件触发全量 map + Markdown 重渲染）。
- 风险：低。think/message 交错需保持相对顺序；协议不变（仍是 `event: message` + 增量 content），旧版前端兼容。

#### 意图分类缓存

**只缓存本地模型 classify，缓存关键词检测无意义**

- 意图识别是纯本地关键词匹配（intent.py:8-10 明示 no LLM call），µs-ms 级。
- 唯一 LLM 调用：`local_llm.py:464-531` `manager.classify()`（本地模型 HTTP 往返，数百 ms）。**`_classifier_cache` 字段已预留但从未使用**（local_llm.py:135）。
- 缓存 key 安全：本地分类只看用户当前消息（local_llm.py:491-493 注释明确不拼上下文）→ 用消息 hash 作 key **不会因上下文变化误判**。注意 `_detect_local_task`/`_is_realtime_request` 的缓存 key 必须用**最终传入文本**（chat.py:384-390 会先做 realtime 注入/指代补全）。
- 实现：classify 外包 `functools.lru_cache`（TTL 5-10 分钟），模型切换时清缓存，失败不缓存。20-30 行，风险低。

#### 本地模型复用（llama-server 常驻）

**现状已是常驻——建议反向优化：加空闲超时自动停止**

- 启动点 3 处（手动 /api/local_llm/start、预整理自动拉起 preprocess.py:251、本地任务路由 chat.py:395-400）；停止点 4 处（服务关闭 main.py:47-52、手动 stop、start 前清理、等待超时）。
- **启动后常驻到显式 stop 或服务退出**，自动拉起后不自动停。
- 建议：加 `last_used` 时间戳 + 空闲 > 5-10 分钟自动 stop（**只停进程、不改 settings 的 enabled/mode**，下次需要时 `_start_local_model` 自动再拉起——链路已存在）。注意"正在流式输出"算活跃；stop 前检查在途请求。
- 改动量：40-60 行（local_llm.py + 各调用点打点）。桌面场景省电/内存收益明确。
- 备选"lifespan 常驻"：0.5B-1.5B 模型常驻 1-2GB 内存，对笔记本不友好，**不推荐默认**。

### 2.3 前端渲染

#### Markdown 渲染优化 ⭐（清单遗漏的最优项）

**可行性：高，改动最小收益最大**

- `MarkdownView/index.tsx:111`：`components={buildComponents(...)}` **每次渲染新建对象** → 破坏 react-markdown 内部缓存 → 流式每 chunk 全量重解析 + 重建 VDOM。
- `linkifyFilePaths(content)` 每次渲染对全文跑 3 遍正则。
- `MessageItem`/`MarkdownView` **无 React.memo**（全项目 memo 仅 3 处）。
- 建议：`MarkdownView` 包 `React.memo`（props 是原始值，浅比较可行）；`buildComponents` 用 `useMemo`；`linkifyFilePaths` 结果 `useMemo(content)`。
- 改动量：3-4 处小改（~30 行），风险低。注意 `choiceState` 对象引用变化会失效 memo（用 message.id + content 长度做 key 或依赖 message 对象引用）。

#### 图片懒加载

**图表已懒加载（echarts/mermaid 动态 import），Markdown 图片是唯一缺口**

- `MarkdownView/index.tsx:289` `loading="eager"`，全项目无 `loading="lazy"`/IntersectionObserver。
- 建议：加 `loading="lazy"`（1 行 + 少量测试）。注意虚拟滚动卸载不可见 DOM → lazy 图片滚回重新加载（有缓存无感）；Tauri WebView 支持基本可用。

#### 代码高亮按需加载

**已达标**（Shiki v4 动态 import + 流式增量 + 37 语言单例 + 主题适配）。可选小优化：37 种语言单 chunk 较大，可按需注册语言（收益取决于语言分布，优先级低）。

---

## 3. 用户体验优化

### 3.1 对话体验

| 项 | 现状 | 可行性 |
|---|---|---|
| 消息搜索增强（模糊/拼音） | FTS5 已存在但每次搜索全量 rebuild（见 2.1）；`tokenize='unicode61'` 对拼音不友好 | 先修 rebuild 问题；拼音搜索需引入拼音转换层（如 pypinyin）或拼音字段，**中改动**，优先级低 |
| 会话历史导出（MD/PDF） | **已实现**（`/sessions/{id}/export` markdown/pdf/text） | 无需做；可加"批量导出"（遍历会话循环调用，前端小改） |
| 快捷指令（"总结这段话"快捷键） | 无快捷键系统（仅 Esc 关闭弹层，UI 组件内 keydown） | 新增快捷键系统需先建统一 keymap（建议 Tauri 全局快捷键 + 应用内快捷键两层），**中改动**，属新功能 |

### 3.2 工具交互

#### 工具执行可视化（进度条）（快速收益项）⭐

**基础设施已存在，接入成本低**

- `base.py:93` `supports_progress` + `progress_callback` 管道已通：`_execute_tool`（tool_runtime.py:224-229）→ `adapter.run(progress_callback)` → `_run_subprocess_with_progress`（base.py:198-247，解析脚本 stderr 的 `{"progress": ...}` JSON 行）。
- **已有完整先例**：`web_fetch_batch`（`supports_progress=True`，execution.py:756-779 `_emit_fetch_progress` → SSE `tool` 事件带 `currentUrl`）。
- 前端 `ToolStatusCard.tsx:100` 已有 `running`/`preparing` 状态 + `currentUrl` 展示，可扩展进度百分比/进度条。
- 建议：为长耗时工具（pdf_generate 300s、image_generate 150s、pdf_render 60s、web_fetch 60s、subagents 300s）逐个加 `supports_progress=True` + 脚本内发进度 JSON；前端 ToolStatusCard 增加 `progress` 字段渲染。**先做 1-2 个工具验证管道，再铺开**。
- 改动量：每工具 20-50 行（脚本层）+ 前端 ~30 行。

#### 工具结果预览（图片放大）

- 现状：FilePreviewModal 已存在（`FilePreviewModal` 组件），工具卡片图表结果已有点击查看（ToolStatusCard 的 chartOption/文件跳转）。
- 建议：确认图片/图表结果是否都走 FilePreviewModal，补齐即可。**小改动**。

#### 批量操作（多文件同时编辑预览）

- 现状：web_fetch_batch、svg_to_png_batch 已有批量工具；DiffView 组件已存在。
- 建议：多文件编辑的批量预览依赖 `edit_files` 返回的多文件 diff，前端 DiffView 已支持。**中改动**，属功能完善。

### 3.3 设置管理

| 项 | 现状 | 可行性 |
|---|---|---|
| 配置导入/导出 | 无 | 后端 settings 已是 JSON（`settings.json`），导出=GET 全量 + 脱敏（去掉 api_key），导入=PUT。**小-中改动**（注意导入时 key 处理：导出不含 key，导入需用户重填或带 key 加密导入） |
| 快捷键自定义 | 无快捷键系统 | 见 3.1，先建 keymap 再谈自定义 |
| 主题预设/自定义模板 | PDF/Word/PPT 主题系统已存在（`pdf_themes.py`、`pdf_theme_manager.py`、`ppt_themes.py`、`word_themes.py`） | PDF 主题已有 API（GET /themes、POST /preview-css、render-preview）；自定义模板=扩展现有主题系统，**中改动**，属功能增强 |

---

## 4. 代码质量优化

### 4.1 类型安全

**types.ts 已零 any（清单假设过时），剩余价值在 SSE 类型黑洞**

- 全项目 8 处 any：MarkdownView 4 个渲染器 `props: any`（可改精确类型）、api.ts 3 处 `trimToolResult`（可泛型化）、DivineBall 1 处。
- **最危险**（`as unknown as` 强转，服务端数据不可信）：
  - `useChatStream.ts:168` `data as unknown as ToolEvent`——服务端字段变更无编译期保护
  - `useChatStream.ts:135` plan items 强转 `TodoItem[]`
  - `sse.ts:102` `handlers[event as keyof SSEHandlers]?.(data as never)`——**类型黑洞**，事件名/数据形状错误无提示
- 建议：SSE 事件改 discriminated union（按 event 名映射 data 类型）+ 补 `isToolEvent` 运行时校验。**0.5-1 人日**，收益大。

#### API 响应校验（Pydantic strict）

- `schemas.py` 19 个 BaseModel，**无 ConfigDict(strict=True)**。
- 注意：`SettingsUpdate` 等模型需要 `exclude_unset=True` 语义（api/settings.py:97），strict 模式（不隐式转型）可能破坏现有宽松校验——**需逐模型评估**，建议只对纯校验模型开 strict（如 Attachment、ChoiceStateUpdate），对 settings 类保持宽松。**小改动**，风险低（有 `tests/test_settings_models.py` 兜底）。

### 4.2 错误处理

#### 统一错误码 ⭐（快速收益项）

**SSE 已带 code 字段但前端忽略——半成品**

- 现状：后端 `error_event(code, message, message_key)` 已发 code（sse.py:12-21）；前端 `sse.ts:29-34` 类型已定义 `{code,...}`，但 `useChatStream.ts:265-291` 的 error handler **只消费 messageKey/message，完全忽略 code**。
- Toast 系统存在但全项目仅 3 处使用。
- 建议：新增 `errors.ts` 统一 `mapErrorCode(code) → { action, i18nKey, retryable }`，在 useChatStream error handler 接入；SSE code 分流（"可重试/需配置/需引导"）。**1 个新文件 + 2 处接入 + i18n key 整理**，中改动、低风险。

#### 重试机制

- 云端 LLM：langchain 底层默认 `max_retries=2`（自动指数退避），代码未显式配置。建议 `_build_llm`（agent/llm.py:98-116）显式传 `max_retries` + 日志。**~10 行**，纯配置收益。
- 本地 LLM：organize 已重试一次（preprocess.py:341-342）；classify/summarize/流式均无重试。流式中途重试不建议（内容重复/乱序）；如需只加"首个 chunk 前"重试 1 次。
- 工具层已有完整退避先例（web_common.py RETRYABLE_STATUS + 指数退避）可参照。

#### 降级策略（云端不可用 → 本地）

- **现状**："本地→云端"降级已相当完善（拒答护栏 `_is_local_refusal`、mark_fallback_pending 留痕、本地动作失败回退 orchestrator.py:276-333、预整理降级）。
- **"云端→本地"不存在**：云端失败只 yield `server_error`（chat.py:588-592）。
- 建议：仅兜底**请求阶段失败**（连接/鉴权/超时，agent 未开始副作用前），不做全量重跑（agent 中途异常可能已执行部分工具）。改动 30-50 行，风险中等。

### 4.3 测试覆盖

| 项 | 现状 | 可行性 |
|---|---|---|
| 前端测试（Vitest+RTL） | **完全没有**；package.json 无 test 脚本、无 vitest 依赖 | 从零搭建：vitest + @testing-library/react；优先覆盖纯逻辑（chatUtils 的 upsertTool/mergeLocalTools、sessionEffort、trimToolResult、consumeSSE 解析），再补 MessageList 虚拟滚动行为。**1-2 人日** |
| E2E（Playwright） | 无；且是 Tauri 桌面壳（WebView2/WKWebView），Playwright 对 WebView 支持弱 | **不建议直接用 Playwright 跑桌面壳**；可行路径：对 Vite 前端跑 Playwright（浏览器模式）+ Tauri 侧保留手动验收，或用 WebDriver（tauri-driver，成本高）。优先级低 |
| 性能监控 | 无 | 后端已有慢请求日志（main.py:70-94 超 1s 打 WARN）；建议加工具耗时/LLM 响应时间结构化日志（tool_runtime.py:238-244 已有 duration 字段）。**小改动** |
| 后端测试 | **41 个测试文件已存在**（agent/工具/数据库/PDF 均有覆盖） | 保留并随改动更新 |

---

## 5. 安全性优化

### 5.1 敏感信息

#### API Key 加密存储 ⭐（快速收益项）

**确认真实问题：明文 + 0644**

- `data/settings.json` 明文存 `api_key`/`glm_api_key`/`models[].api_key`，文件权限 **0644（world-readable）**；keyring 未安装。
- 好消息：API 层 `_public`（api/settings.py:21-71）只回 `has_api_key` 布尔（不回显 key）；前端 password 输入 + "已保存"标记；DB 无 key 落盘；.gitignore 已排除 data/。
- 建议组合：
  1. keyring 优先（service="ai-divine"，按 model entry id 存多 key；macOS login keychain 可用，Windows Credential Manager 可用，**Linux 无 D-Bus 会话时 keyring 抛 NoKeyringError 需回退**）。
  2. 回退：`os.chmod(0o600)`（**现状 0644 必改**）+ at-rest 加密（机器本地派生密钥）或明文+权限兜底。
  3. PyInstaller 下 entry-point 后端发现失效，需显式 import 后端模块 + hiddenimports。
- 注意：keyring 不是安全边界（同用户进程可读 keychain），只防"直接读 settings.json"。
- 新增 `app/security/keyring_store.py`；改 config.py load/save + api/settings.py；requirements.txt + spec + build-sidecar.sh。**1-2 人日**。

#### 日志脱敏 ⭐（快速收益项）

**主要风险点（打印用户输入/敏感信息）**：
- `tool_runtime.py:212-217`：**<80 字符的工具参数原样打印**（终端命令全文、read_file 路径、git commit message、web_fetch URL、write_file 短内容）
- `execution.py:620-626`：`command[:300]`（含 `curl -H "Authorization: Bearer sk-..."` 这类）
- `execution.py:428-433`：external paths 全量（可含 `~/.ssh/...`）
- `bg_process.py:133,154`：后台命令全文
- 未发现直接打印 api_key 的日志（好）；settings.py 只打 has_api_key 布尔（好）。

- 建议：**调用点整改 + logging.Filter 兜底**双管齐下。现有日志是结构化参数式（`command=%s`），纯正则脱敏会漏——命令只打截断+哈希、args 改打摘要。涉及新增 `app/security/redact.py` + entry.py 挂 Filter + 整改 5-6 处调用点。**0.5-1 人日**。

### 5.2 工具执行

#### 终端超时 ⭐（快速收益项，部分已实现）

**已有三层超时，缺口是 in-process 线程泄漏**

- 外层 `tool_runtime.py:224` wait_for；中层 `base.py:161` subprocess timeout；脚本层 `scripts/terminal.py:50-68` clamp。
- **缺口**：in-process 工具（`_run_in_process` → `asyncio.to_thread`，read_file/edit_files/edit_lines/grep_files/directory_tree/sqlite_query）超时后**线程泄漏继续跑**（wait_for 只返回错误不杀线程）。
- 建议：`base.py::_run_in_process` 补超时（in-process 工具包一层 subprocess 超时，或至少记录泄漏）；`bg_process.py` 可选 max_lifetime 上限。
- 改动量：中（需逐工具验证），但**重要性低于下面两个发现**。

#### 文件访问审计 ⭐（发现真实漏洞，最优先）

**🔴 真实漏洞：`edit_lines.py:148-170` 可写任意绝对路径但未声明 external_paths → 零确认直接改 `~/.ssh/config`、`~/.bashrc` 等**

- `edit_lines` 未声明 `allow_external_paths` 也未实现 `external_paths()` → execution.py 视为无外路径 → **任何 approval_mode 下零确认写任意文件**。
- 其他文件工具（write_file/edit_files/read_file）自身无 workspace 检查，外路径确认仅限 `approval_mode=="ask"`（execution.py:427）；assist/full 模式下静默放行。
- 无敏感目录 deny 规则（`~/.ssh`、`/etc`、`~/Library/Keychains` 均可读写）；无专门审计日志（仅 db.tool_runs 间接审计）。
- 建议：新增 `app/tools/path_policy.py`（SENSITIVE_DIRS deny 列表 + workspace 外一律 require-approval 不论模式）在 execution.py:418-482 统一收紧 + 下沉到各工具 run() 第二道防线；**必修 edit_lines 补 external_paths()**；审计日志（敏感路径访问打 WARN，tool_runs 加标记列）。
- 改动量：2-3 人日。需兼容 `approved_paths`（用户拖入文件）与 projects 多目录场景。
- **建议优先级最高**：这是本次勘察发现的唯一"零闸门任意文件写"漏洞。

#### 命令注入防护

- 现状：`terminal_policy.py` 分级（block/confirm/safe）+ shell 控制符正则 + git 只读子命令白名单；确认弹窗 `_ask_interrupt`。
- 弱点：黑名单是子串匹配且命令仅 strip+lstrip+lower（terminal_policy.py:87），`rm  -rf`（双空格）、`rm -r -f` 可绕过 block（落 confirm，属降级非完全绕过）；confirm→safe 自动降级（approval_mode=assist/full 或 plan_approved 时 execution.py:609-618）；后台路径 `_run_background`（adapters/terminal.py:62-96）不二次查 policy。
- 建议：黑名单改 `shlex.split` token 化判断；`_run_background` 补 policy 复查；评估 plan_approved 自动放行 confirm 的合理性。**中改动**。

---

## 6. 功能增强建议（新功能，本轮不实施）

| 方向 | 现状基础 | 可行性评估 |
|---|---|---|
| 多模态（语音输入/输出） | 无；已有 read_image（GLM 视觉）+ image_generate | 语音输入需 Tauri 录音权限 + ASR（本地 whisper 或云端）；语音输出需 TTS。**大改动**，需产品设计 |
| 会话分享/协作编辑 | 无；数据全本地 SQLite | 架构性（需服务端同步）；与"本地优先"定位冲突。**不建议短期做** |
| 插件市场 | 工具插件化（1.2）+ 技能系统（skill_lib，可从 GitHub 安装技能）已有雏形 | 插件市场的后端（仓库索引/版本/签名）是全新系统。**大改动**，先做 1.2 工具插件化打底 |
| 本地知识库（上传文档） | **已有本地 RAG**：`rag_store.py` + rag_index/rag_search 工具 + 工作区文档向量索引 | 已有基础；缺口是"用户显式上传非工作区文档建库"的 UI 与流程。**中改动** |
| 自定义 Agent 工作流 | 计划系统（create_plan/plans.py）+ 子代理（subagents.py）+ 技能系统已存在 | 可在现有"计划+子代理"之上做可视化工作流编排。**大改动** |
| 移动端 | 无 | 与 Tauri 桌面架构不兼容，需重写。**不建议** |

---

## 7. 快速收益优化（建议优先实施）— 重新校准

原始清单的"快速收益 5 项"经勘察后有修正：

| 原清单项 | 校准后结论 | 改动量 | 优先级 |
|---|---|---|---|
| PRAGMA cache_size | 可做但**当前收益≈0**（库仅 0.5MB）；顺手加 cache_size=-16000 + temp_store=MEMORY，1-3 行 | 10 分钟 | 🟡 顺手做 |
| SSE 批量发送（50ms） | **可行且前端零改动**（content 增量语义是根基）；放 chat.py generate 出口，40-60 行 | 1-2 小时 | 🟢 高 |
| 统一错误处理（错误码） | **SSE code 已定义但前端忽略**（半成品）；补 errors.ts 映射 + 2 处接入 | 2-4 小时 | 🟢 高 |
| API Key 加密存储 | **确认真实问题**（明文 0644）；keyring + 0600 回退，含 PyInstaller 适配 | 2-4 小时 | 🟢 高 |
| 工具执行进度条 | **基础设施已存在**（supports_progress + web_fetch_batch 先例）；先接 1-2 个长耗时工具验证管道 | 2-4 小时（首个工具）+ 每工具 0.5h | 🟢 高 |

**新增的高价值快速项（原清单遗漏）**：
| 项 | 依据 | 优先级 |
|---|---|---|
| 🔴 `edit_lines` 零闸门写任意文件漏洞 | 安全勘察 E 节发现 | **最高**（安全） |
| 🔴 日志脱敏（tool_runtime 打参数全文等 5-6 处） | 安全勘察 D 节 | **最高**（安全） |
| MarkdownView memo + buildComponents useMemo（~30 行） | 前端勘察 §3：每 chunk 全量重解析 | 🟢 高（性能） |
| SSE 类型收口（discriminated union + 运行时校验） | 前端勘察 §6：`data as never` 类型黑洞 | 🟢 高（质量） |
| `history_for_model` 尾部窗口化（消除每轮全量扫描） | 数据库勘察 §2 | 🟡 中 |
| FTS5 去掉"每次搜索全量 rebuild" | 数据库勘察 §3 | 🟡 中 |
| settings.json chmod 0600（10 分钟，先行止血） | 安全勘察 C 节 | 🟢 高（可与 keyring 同批） |
| 显式 `max_retries`（langchain 已有默认，显式化+日志） | LLM 勘察 §6 | 🟡 顺手 |

---

## 8. 建议实施顺序（三批）

**第一批（安全止血 + 零成本高收益，0.5-1 天）**
1. 🔴 edit_lines 补 external_paths() 强制 workspace 边界（堵零闸门写任意文件）
2. 🔴 settings.json chmod 0600（keyring 的前置止血）
3. MarkdownView memo + buildComponents useMemo（前端性能最大单项）
4. PRAGMA cache_size + temp_store（1-3 行顺手）
5. 显式 max_retries（10 行顺手）

**第二批（快速收益 5 项，1-2 天）**
6. SSE 批量发送（chat.py 出口 50ms + 字符阈值 + 三处 flush）
7. 统一错误码映射（errors.ts + useChatStream 接入）
8. API Key keyring 加密存储（含 Linux 回退 0600）
9. 日志脱敏（调用点整改 + logging.Filter）
10. 工具进度条（先接 pdf_generate 验证管道，再铺开）

**第三批（结构性优化，按需排期，3-5 人日/项）**
11. SSE 类型收口 + isToolEvent 运行时校验
12. history_for_model 尾部窗口化 + (session_id, created_at) 索引
13. FTS5 增量维护（去每次 rebuild + PRAGMA optimize 挂启动）
14. 终端 in-process 超时补漏 + 命令注入 token 化
15. 统一路径策略层 path_policy.py（敏感目录 deny + 审计）
16. 前端 Vitest 从零搭建
17. agent 层拆包（Phase 0→5，最大项）
18. 工具注册插件化（依赖 PyInstaller 改造）

**明确不做/暂缓**：gRPC/MessagePack 换协议（收益低）、Zustand 迁移（风险中高）、Playwright E2E 桌面壳（WebView 支持弱）、移动端、会话协作（架构冲突）。

---

## 附：证据索引（核心文件:行号）

- 数据库：`connection.py:34-41`（PRAGMA）、`history.py:57-69`（history_for_model 全量）、`history.py:243-316`（游标分页已实现）、`migrations.py:154-161`（FTS5）、`sessions.py:157-162`（每次搜索 rebuild）、`migrations.py:105`（messages 索引）
- LLM/SSE：`agent/sse.py:264-300`（每 token 一帧）、`chat.py:585`（yield 出口）、`useChatStream.ts:126`（content 增量累加）、`local_llm.py:135`（_classifier_cache 未用）、`local_llm.py:464-531`（classify）、`main.py:47-52`（退出停止）
- 前端：`MessageList/index.tsx:49-60`（虚拟滚动已实现）、`MarkdownView/index.tsx:111`（components 每次重建）、`MarkdownView/index.tsx:289`（img eager）、`HighlightedCode.tsx:60`（Shiki 动态 import）、`sse.ts:102`（类型黑洞）、`useChatStream.ts:168`（ToolEvent 强转）、`useChatStream.ts:265-291`（error handler 忽略 code）
- 安全：`data/settings.json`（明文 key 0644）、`tool_runtime.py:212-217`（参数全文日志）、`execution.py:620-626`（command[:300]）、`edit_lines.py:148-170`（零闸门写任意路径）、`terminal_policy.py:86-101`（策略分级）、`base.py:93/144`（supports_progress 管道）、`execution.py:756-779`（web_fetch_batch 进度先例）
- 测试：`tests/` 41 个文件；14 个直接导入 `app.agent.*`（拆包成本）
