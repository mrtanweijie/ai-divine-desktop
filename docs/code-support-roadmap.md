# Agent Code 支持优化规划（项目开发基线）

> 版本：v1.7
> 日期：2026-08-30
> 状态：P0 全部 6 项 + P1 全部 5 项 + P2-1 可写子 Agent + P2-2 轻量代码索引（list_definitions）已实现，**P2-3 MCP 支持已实现（v0 stdio + 设置页）**，P2-4 待实施。另完成性能优化（SQLite WAL + ToolMessage 压缩 + 异步 I/O + SSE 截断）与编码工具补全（edit_lines/apply_patch/move_file/glob_files/format_code/lint_check/run_tests）。
> **P3-0 评测体系 + P3-1 快赢四项 + P3-2 上下文工程 + P3-3 质量闭环 + P4 MCP 接入已实现（2026-08-30）**：eval harness（12 场景，真实模型基线 36/36）；token 预算裁剪 + 工具结果置换 + 编码导向摘要；项目指令文件；编辑后自动语法检查；turn 级 checkpoint + undo_last_turn；终端命令审批记忆 + 回合预算软着陆；MCP 客户端（keeper 任务连接管理、动态工具注入、审批复用、设置页 MCP tab、Claude Desktop 配置导入）。全套件 629 测试通过 + 前端 tsc/vite 构建通过。
> 目标：把 Divine Agent 从"文档生成 + 轻量文件操作"提升到"能流畅用于真实软件项目开发"的基础能力。
> 范围：`divine-server/app/agent/*`、`divine-server/app/tools/*`、`divine-server/app/mcp/*`、`divine-app/src/pages/chat/*`、`divine-server/tests/*`、`divine-server/evals/*`。

---

## 1. 现有能力盘点（Code 相关）

### 1.1 已具备

| 能力 | 实现 | 评价 |
| --- | --- | --- |
| 读文件 | `read_file`（行区间、txt/md/json/csv/docx/pptx/pdf/xlsx） | ✅ 够用 |
| 写文件 | `write_file`（overwrite 保护、append） | ✅ 够用 |
| 批量编辑 | `edit_files`（SEARCH/REPLACE，事务式 staging，一次 50 文件） | ⚠️ 见差距 3 |
| 文件名搜索 | `search_files`（按文件名/路径关键字） | ⚠️ 只能按名搜 |
| 目录浏览 | `directory_tree`（深度≤6、200 条上限） | ⚠️ 浅、无 gitignore 过滤 |
| 执行命令 | `terminal`（子进程、策略审批 safe/confirm/block、超时） | ⚠️ 见差距 4 |
| 交互终端 | WS PTY 终端（`/api/terminal`，用户手动使用） | ✅ 独立于 agent 工具 |
| 计划/审批 | `write_todos`、plan mode（ask/plan_first/direct）、HumanInTheLoop、外部路径审批 | ✅ 机制完善 |
| 上下文 | deepseek-v4-flash 1M 上下文、thread trim、LLM 会话压缩、长期记忆 | ⚠️ 面向聊天，见差距 6 |
| 并行调研 | `run_subagents`（只读、并行≤4、独立上下文） | ✅ 只读足够 |
| 技能系统 | 知识技能 + 可执行技能脚本 | ✅ |
| 持久化 | SQLite 会话/消息/工具运行记录 | ✅ |

### 1.2 关键差距（对照"做项目开发的基线"）

| # | 差距 | 影响 | 严重度 |
| --- | --- | --- | --- |
| 1 | **无内容搜索（grep）**：`search_files` 只匹配文件名 | 无法按内容/符号/正则定位代码，探索效率极低 | 🔴 最高 |
| 2 | **无 git 集成**：无 status/diff/commit/revert | 改动无法自查 diff、无法安全回滚、无法给用户展示改动 | 🔴 最高 |
| 3 | **编辑鲁棒性不足**：SEARCH 必须逐字节精确匹配；无模糊回退；无编辑后 diff 反馈；无 undo | 空白/缩进不一致即失败，反复 read→edit 重试 | 🔴 高 |
| 4 | **终端不适合开发工作流**：每次命令新 shell（无状态）；超时上限 60s；不能跑长驻进程（dev server）；无后台任务；输出无截断（大输出撑爆上下文）；`&&`/`|` 等控制符强制确认 | 跑不了 build/test/dev server，摩擦大 | 🔴 高 |
| 5 | **项目结构感知弱**：不自动注入项目骨架；工作区 RAG 只索引 txt/md/csv/json，不索引代码 | agent 对项目"无感"，每轮从零探索 | 🟠 中 |
| 6 | **上下文策略面向聊天**：thread trim 默认 20 条消息；压缩是"对话摘要"非"代码状态" | 多文件编码时关键文件内容易被裁剪 | 🟠 中 |
| 7 | **前端无 diff 视图**：编辑后只显示文件列表，无 before/after diff、无一键回滚 | 用户无法审查 agent 的改动 | 🟠 中 |
| 8 | **系统提示面向文档生成**：大量篇幅在 PDF/PPT/SVG/旅行手册/简历，编码工作流指引几乎为零 | agent 没有"探索→计划→实现→验证"的习惯 | 🟠 中 |
| 9 | **验证闭环缺失**：改完代码没有自动跑 lint/单测/构建的惯例 | 语法错误要等用户发现 | 🟡 低 |
| 10 | 子 Agent 只读（v2 演进方向） | 不能并行实现独立模块 | 🟡 低（非基线） |

### 1.3 "项目开发基线"定义（目标能力）

- 能浏览项目：`directory_tree` + 内容搜索（grep）+ `read_file`
- 能精确小步修改：`edit_files`（模糊回退 + diff 反馈）+ `git diff` 自查
- 能执行命令并拿到结果：`terminal`（合理超时、截断、可跑测试/构建）
- 能安全回滚：git 或文件快照
- 有明确开发工作流提示：探索 → 说明改动 → 编辑 → 验证 → 汇报
- 上下文不爆：工具结果紧凑化、截断、压缩

---

## 2. 优化路线图

### P0 — 编码基础闭环（建议优先，约 1~2 周）

#### P0-1 新增 `grep_files` 内容搜索工具 🔴 ✅ 已实现

- **后端**：`divine-server/app/tools/adapters/grep_files.py`（新）+ `divine-server/app/tools/scripts/grep_files.py`（新）
  - 参数：`pattern`（正则）、`path`（相对目录，默认工作区根）、`glob`（可选文件过滤）、`context`（上下文行数，默认 0）、`case_sensitive`、`include_hidden`、`max_results`（默认 200，上限 500）
  - 行为：尊重 `.gitignore`（含 `!` 否定与目录规则）、跳过二进制与超大文件（>2MB）、输出 `file:line:content`、命中超限截断并提示
  - 注册进 `registry`；加入 `constants.py::_READ_ONLY_TOOLS`；加入 `subagents.py::_SUBAGENT_READ_ONLY_TOOLS`
- **Prompt**：`constants.py` SYSTEM_PROMPT 增加"定位代码用 grep_files（内容/正则），文件名/路径用 search_files"
- **测试**：`divine-server/tests/test_grep_files.py`（18 个用例：命中/正则/glob/gitignore/否定/隐藏/二进制/截断/外部路径/注册）✅ 通过

#### P0-2 `edit_files` 增强：模糊回退 + diff 反馈 🔴 ✅ 已实现

- `divine-server/app/tools/adapters/edit_files.py`
  - 精确匹配失败时：① 去空白差异后做唯一匹配（必须全局唯一，防止误改，`count` 仅 1/-1 时启用）；② 匹配不唯一时报错并给出附近候选行数；③ 命中后返回该文件的 unified diff
  - 输出 `data.diff`（合并 unified diff）+ `data.files[].diff`（逐文件）+ `fuzzy_used` 标记
- **前端**：`ToolStatusCard.tsx` 对 `edit_files` 渲染 `DiffView.tsx`（新增，可折叠、行级着色、截断保护）
- **测试**：`divine-server/tests/test_edit_files.py`（10 个用例：精确/模糊唯一/模糊多候选拒绝/无匹配/diff 输出/新建 diff/批量/替换全部）✅ 通过

#### P0-3 terminal 增强：可配超时 + 输出截断 + 开发命令降摩擦 🔴 ✅ 已实现

- `divine-server/app/tools/scripts/terminal.py`
  - 超时：命令参数 `timeout` 上限 600s；输出截断：stdout 保留尾部 ≤16KB、stderr ≤8KB，`data` 返回字节数与截断标记
- `divine-server/app/tools/adapters/terminal.py` + `divine-server/app/agent/tool_runtime.py`
  - 新增 `effective_timeout()`：按参数动态计算 60-600s，`_execute_tool` 的 wait_for 与错误提示同步使用
- `divine-server/app/tools/terminal_policy.py`
  - 开发命令白名单降为 safe：pytest/python/python3/node/tsc/eslint/mypy/pnpm/npm/yarn/npx/bun/pip/pip3/uv/poetry；`git` 仅只读子命令（status/diff/log/show/branch/remote/ls-files/rev-parse/stash/tag/blame/grep/help）safe，其余 git 命令 confirm
  - 保留 block：`rm -rf`、`sudo`、`kill -9`、`curl|wget`、heredoc 等
- **测试**：`divine-server/tests/test_terminal_dev.py`（38 个用例：safe/confirm/block 白名单、超时钳制、截断、退出码、stderr）✅ 通过

#### P0-4 git 基础集成：status / diff / log / commit / revert 🔴 ✅ 已实现

- 新增 `divine-server/app/tools/adapters/git_tool.py`（5 个工具）+ `divine-server/app/tools/scripts/git_tool.py`（共享脚本，参数列表调用无 shell 注入）
  - 只读：`git_status`（含 clean 判定）、`git_diff`（path/staged/ref）、`git_log`（safe，加入 `_READ_ONLY_TOOLS` 与子 Agent 只读集）
  - 写：`git_commit`（`git add -A` + commit）、`git_revert`（`git restore`，还原已跟踪文件，未跟踪保留）；写操作在 `execution.py` 中经 `_ask_interrupt` 用户确认，非 git 仓库返回明确提示
- **i18n**：三语言新增 `tool.gitRejected`
- **测试**：`divine-server/tests/test_git_tools.py`（13 个用例：真实 git 仓库的 status/diff/log/commit/revert/非仓库报错/注册）✅ 通过

#### P0-5 前端 diff 视图 + 文件改动展示 🟠 ✅ 已实现

- 新组件 `divine-app/src/pages/chat/components/MessageItem/DiffView.tsx`（unified diff 解析、行级着色、+N/−M 统计、600 行渲染上限）
- `ToolStatusCard.tsx`：`edit_files` 卡片展示可折叠 diff；样式加入 `index.less`（`.diff-view` 系列，适配明暗主题）
- **测试**：前端 `tsc --noEmit` 与 `vite build` 均通过

#### P0-6 系统提示补充"项目开发工作流"章节 🟠 ✅ 已实现

- `constants.py` SYSTEM_PROMPT 新增 `## 项目开发工作流`：
  - 探索（directory_tree + grep_files + read_file）→ 计划 → 编辑（edit_files 一次提交）→ 验证（git_diff 自查 + pytest/tsc 针对改动文件）→ 回滚（git_revert）
  - git 纪律：改动前 git_status、不擅自 commit/push、保持改动小而清晰

### P1 — 开发体验（1~2 周）

#### P1-1 持久 shell + 后台任务 🟠 ✅ 已实现

- 新增 `divine-server/app/tools/bg_process.py`（`BackgroundProcessManager`，in-process 进程注册表）：`asyncio.create_subprocess_shell` 启动、输出环形缓冲（≤64KB/2000 行）、退出码捕获、按 session 隔离、应用关闭时 `shutdown_all()`
- `terminal` 工具支持 `background=true`：立即返回 `bg_id`，不再等待命令结束
- 新增 `bg_status` / `bg_output` / `bg_kill` 三个工具（`adapters/bg_tool.py`）：查询状态/列表、读尾部输出、停止任务；`bg_kill` 在 `execution.py` 中经用户确认（`tool.bgKillRejected` 三语言文案）
- 会话隔离：`execution.py` 为 terminal/bg 工具注入 `session_id`，跨会话不可见
- **测试**：`divine-server/tests/test_bg_process.py`（8 个用例：启动/退出码/输出/kill/会话隔离/端到端/未知 id/注册）✅ 通过
- 未做：与 WS PTY 交互终端打通（可选演进）

#### P1-2 项目骨架自动注入 🟠 ✅ 已实现

- 新增 `divine-server/app/agent/project_context.py`：识别项目（.git 或 README/package.json/pyproject.toml/requirements.txt/Cargo.toml/go.mod），注入 README 摘要 + package.json/pyproject/requirements 关键字段 + gitignore 过滤后的目录树（深度 2、≤60 条、≤1800 字符）
- 按 session 缓存（TTL 300s + 关键文件 mtime 指纹失效），`prompts.py` 动态 prompt 注入，失败不影响主流程
- **测试**：`divine-server/tests/test_project_context.py`（8 个用例：识别/注入内容/gitignore/缓存/失效/pyproject/requirements）✅ 通过

#### P1-3 directory_tree 增强 🟡 ✅ 已实现

- 脚本尊重 `.gitignore`（复用新增共享模块 `divine-server/app/tools/gitignore.py`，grep_files 同步重构复用）并跳过 node_modules 等重目录
- 新增 `show_sizes` 参数（默认 false，返回文件大小）；`max_entries` 上限 500
- **测试**：`divine-server/tests/test_directory_tree.py`（8 个用例：gitignore/重目录/show_sizes/深度/隐藏）✅ 通过

#### P1-4 上下文预算改进 🟡 ✅ 已实现

- `read_file` 超长截断时在 content 尾部追加"继续读取请用 start_line/end_line"提示（含当前行号与总行数）
- `context_limit` 默认 20 → 30（`config.py` + 前端 `chat/index.tsx` 同步）
- **测试**：`divine-server/tests/test_read_file.py`（4 个用例：截断提示/小文件无提示/行区间/缺失文件）✅ 通过

#### P1-5 编辑后验证惯例 🟡 ✅ 已实现（并入 P0-6 + 补充）

- P0-6 工作流章节已规定 pytest/tsc 验证 + 失败重试 2 次；本轮补充"汇报"环节（列出改动文件、关键变化与测试结果）与"长驻任务用 background 启动"指引

### P2 — 进阶（后续，非基线）

- **P2-1 可写子 Agent（v2）** ✅ 已实现：带审批的并行写委托——"并行实现多个独立模块/文件"
  - 子任务级 `write=true` + `write_paths`（workspace 内路径声明，可指文件或目录）；校验：路径必须在工作区内、各写任务声明不得重叠（`subagents.py::_validate_tasks`）
  - 预审批：`execution.py` 在委托前经 `_ask_interrupt`（`subagents_write`）征得用户同意，子 Agent 内不弹窗（沿用 `docs/subagent-feature-design.md` §9 思路）
  - 写工具白名单：`write_file`/`edit_files` 仅对声明了 write_paths 的子 Agent 开放；越界写入被包装器拒绝（`_run_subagent_tool_with_claims`）
  - 每次写入做 before/after 快照并生成 unified diff，随结果返回主 Agent（`changed_files`）；批次汇总"共修改 N 个文件"
  - 前端：`subagents_write` 确认卡片（列出任务与路径）、子 Agent 面板显示"改动 N 个文件"、历史恢复保留 changed_files
  - **测试**：`divine-server/tests/test_subagents_write.py`（12 个用例：校验/越界拒绝/diff 记录/工具集/SSE 映射）✅ 通过
- **P2-2 轻量代码索引** ✅ 已实现（list_definitions）：Python AST 解析 + ts/js/rs/go/java 正则启发式，输出类/函数/接口大纲与行号
- **P2-3 MCP 支持** ✅ 已实现（v0，2026-08-30）：
  - `app/mcp/manager.py`：keeper-task 连接管理——每个 server 一个常驻任务持有
    AsyncExitStack（连接/调用/关闭同任务，规避 anyio cancel-scope 跨任务限制），
    懒连接 + 失败冷却 + 配置指纹变更自动重连 + TTL 工具索引
  - `_build_tools` 动态注入：`mcp_<server>_<tool>` 注册名，inputSchema →
    args_model 复用现有转换；执行走 `_execute_tool` 同一条审批/持久化管线；
    未信任 server 复用 terminal 确认卡片（`mcp:server.tool`），trusted 跳过
  - REST：`GET /api/mcp/servers`（状态+工具清单）、`POST /api/mcp/servers/{id}/test`；
    settings 新增 `mcp_servers`（env 密钥回显置空、回传空值保留已存值）
  - 前端设置页新增 MCP tab（`McpSection.tsx`）：服务器卡片（状态点/启停/
    测试连接/工具清单展开/编辑删除）+ Claude Desktop JSON 配置整段导入 +
    三语言 i18n；`requirements.txt`/`divine-server.spec` 补 mcp 依赖与 hiddenimports
  - 测试：`tests/test_mcp_manager.py` 用真实 stdio fixture server（`tests/fixtures/`）
    走完整协议——发现/调用/复用连接/禁用隔离/坏 server 隔离/配置变更重连/密钥合并
  - 已知边界：v0 仅 stdio（HTTP 传输待后续）；PyInstaller 打包环境 spawn 外部
    server（npx/uvx）需实机验证
- **P2-4 自动 code review**：`git_diff` 结果交给只读子 Agent 做审查，输出问题清单与修改建议

---

## 2.5 P3 — 对照 Codex / Claude Code 的下一阶段（2026-08-30 起）

> 完整差距分析见会话记录；优先级按"执行架构 → 上下文工程 → 自主性闭环"排列。

### P3-0 评测体系（度量先行）✅ 已实现

- 新增 `divine-server/evals/`：harness（场景加载/临时工作区+git 基线/生产栈接管/pytest 评分/JSON 报告）
  + `evals_pytest_plugin.py`（精确 nodeid 采集）+ `fake_model.py`（剧本模型，零 API 成本验证全链路）
- 首批 12 个场景：单文件 bug ×4 / 跨文件 bug ×3 / 小功能 ×2 / 排障 ×2 / 重构 ×1；
  每个场景含 repo/隐藏测试/task.md/config.yaml（fail_to_pass + pass_to_pass + forbidden_paths + 预算 + solution）
- 验收：`check` 夹具自检 12/12（基线 fail_to_pass 全红、pass_to_pass 全绿）；
  `run --fake` 端到端 12/12 resolved；隔离运行（DB_PATH/DIVINE_DATA_DIR 指向 .runs/，真实 settings 只读加载）
- 后续：真实模型跑分基线（`--model <id> --runs 3`）、补充大文件/长任务上下文压力场景

### P3-1 快赢四项 ✅ 已实现

| 项 | 改动 | 文件 |
| --- | --- | --- |
| 工具锁细粒度化 | 只读工具（grep/read/glob/lint 等）免锁并行，可变工具保持串行 | `app/agent/tools/tools.py`（`_LOCK_FREE_TOOLS`） |
| plan_first 只读放行 | 等待方案确认期间允许 read_file/grep 等只读探索，杜绝"盲写方案" | `app/agent/tools/execution.py` |
| 中断线程修复 | 崩溃/取消后合成 ToolMessage 补齐未完成 tool_calls，不再整线清零（补齐失败才回退清零） | `app/agent/orchestrator.py`（`_pending_tool_call_ids` + 修复路径，`tests/test_thread_repair.py` 6 用例） |
| prompt 稳定前缀 | 稳定节（ALWAYS_SECTIONS）前置、意图条件节移尾部，保 DeepSeek/GLM 前缀缓存命中 | `app/agent/intent/intent.py`（`split_rule_sections`）、`app/agent/core/prompts.py`、`app/agent/state/compact.py` |

### P3-2 上下文工程 ✅ 已实现（2026-08-30）

- **token 预算裁剪**：thread trim 从"按条数 30"改为"按 token（窗口 70%，最低 12k）"，
  删除边界仍对齐 HumanMessage；`limit` 语义变为"最近 N 条完整保留"，另有
  limit*4 条数硬上限防结构性膨胀（`orchestrator.py::_thread_context_actions`，6 测试）
- **旧工具结果置换（stub）**：滑出最近尾部（12 条外）的长 ToolMessage（>600 字符）
  用同 id 占位消息原位替换——结构保留、字节缩小，需要时重新调用工具（同上）
- **编码导向摘要模板**：compact 摘要必含 当前任务/代码状态（改了哪些文件）/
  问题与验证（报错与测试结果）/下一步（`state/compact.py::_SUMMARY_SYSTEM`）
- **项目指令文件**：`.divine.md` / `AGENTS.md` / `CLAUDE.md`（按优先级取第一个）
  注入 prompt 顶部，参与缓存指纹，编辑即时生效（`project_context.py`，6 测试）

### P3-3 质量闭环 ✅ 已实现（2026-08-30）

- **编辑后自动语法检查**：edit_files/write_file/edit_lines/apply_patch 成功后
  自动跑 py_compile（批量单进程）/JSON/YAML 检查，错误文本回灌给模型立即修复；
  检查失败绝不影响工具结果（`tools/syntax_check.py` + `execution.py`，8 测试）
- **turn 级 checkpoint + undo_last_turn 工具**：每轮开始前快照工作区
  （gitignore 感知、单文件 ≤512KB/总量 ≤32MB/超限标记 incomplete），
  `undo_last_turn` 恢复最近一个与当前不同的快照——连续调用即 undo→redo
  （恢复前自动存档）；.git 永不触碰；incomplete 快照只覆盖不删除
  （`tools/checkpoint.py` + `adapters/undo_turn.py` + orchestrator 钩子，5 测试）
- **终端命令审批记忆**：用户批准过的命令（规范化空白后精确匹配，不做前缀
  匹配防止 `git push` 放行 `git push --force`）本会话内不再重复确认；
  仅内存存储，重启即清空（`execution.py`，4 测试）
- **回合预算软着陆**：接近 96 回合上限（≤6 剩余）时 prompt 注入收尾指令
  （总结进度/告知用户可"继续"接续），不再被上限静默截断（`prompts.py`）

---

## 3. 实施顺序与验收

| 步骤 | 内容 | 验收标准 | 状态 |
| --- | --- | --- | --- |
| 1 | P0-1 grep_files | 对真实项目（本仓库）"找某个函数定义/配置项"可用 grep 定位 | ✅ 已实现（18 测试） |
| 2 | P0-2 edit_files 增强 | 手改缩进后仍能命中唯一锚点；编辑后返回 diff | ✅ 已实现（10 测试） |
| 3 | P0-3 terminal 增强 | `pnpm build` / `pytest` 跑完拿回结果；输出不爆上下文 | ✅ 已实现（38 测试） |
| 4 | P0-4 git 集成 | 改文件 → git_diff 可见 → 误改 git_revert 可回滚 | ✅ 已实现（13 测试） |
| 5 | P0-5/6 前端 diff + prompt | 用户能看到每次编辑 diff；agent 遵循开发工作流 | ✅ 已实现（tsc + vite build 通过） |
| 6 | P1 各项 | dev server 后台运行、项目骨架自动注入、验证惯例生效 | ✅ 已实现（后台任务 8 + 骨架 8 + 目录树 8 + 读文件 4 测试） |
| 7 | P2-2 list_definitions | 大纲工具可用，行号与 read_file 一致 | ✅ 已实现（3 测试） |
| 8 | 性能优化 | SQLite WAL + ToolMessage 压缩 + 异步 I/O + SSE 截断 | ✅ 已实现 |
| 9 | 编码工具补全 | edit_lines/apply_patch/move_file/glob_files/format_code/lint_check/run_tests | ✅ 已实现（42 测试） |

**端到端验收场景**：在 Divine 会话中打开本仓库作为项目工作区，下达真实任务（如"给 divine-server 加一个只读 API 并补测试"），要求 agent 自主完成：探索 → 定位 → 多文件修改 → diff 自查 → 跑测试 → 汇报，全程无需人工介入读文件。

---

## 4. 风险与注意事项

- **模糊匹配误改**：P0-2 的模糊回退必须"全局唯一才应用"，否则拒绝并给候选，宁可不改不可改错。
- **git 工具与已有工作流冲突**：git 写操作（commit/revert）一律 confirm；commit 只做 `git add -A && git commit` 的简单封装，不推远端。
- **终端安全边界**：放宽的是"开发读/测命令"，`rm -rf`、`sudo`、`kill -9`、下载执行等维持 block/confirm；策略表要有测试锁定。
- **上下文预算**：1M 窗口很大，但多文件编辑仍要"结果紧凑化"，避免工具输出重复读文件全文。
- **测试先行**：每个 P0 项都带独立测试文件，避免破坏现有 30+ 工具的注册与审批链路。
- **兼容性**：`edit_files` 保持原参数契约（新增可选行为不破坏 schema），旧会话可继续回放。
