# Agent 执行过程可观测性实施方案

> 编号：015 ｜ 类型：design ｜ 日期：2026-09-04 ｜ 状态：P0/P2 已实施，P1 已回退
> 实施日期：2026-09-04
> 范围：`divine-server`（SSE 事件层 / 计划状态层）+ `divine-app`（chat 页渲染层）
> 起因：外部 LangGraph 教程（画流程图 + 实时追踪）对照本项目后的差距分析
> 
> ## 实施记录（与原方案的偏差）
> 
> 1. **P1（phase 意图标签）实施后被用户否决，已全链路回退**。实测结论：
>    意图标签本质是 prompt 裁剪用的内部路由信息，实体化成对话内的 chips
>    与消息内容无从属关系，是视觉噪音。`ctx.intents` 数据仍在，若将来
>    需要「本轮能力提示」（如输入框上方轻量提示），从后端重新出网约半天。
> 2. **phase 事件**：曾按「后端只发 intents、前端 i18n 翻译」实施，随 P1
>    一并回退。
> 3. **abort 收敛确认**：取消路径走 `orchestrator.py` 的 `cancel_event` 分支
>    提前 return，不经过 `_sync_todos_from_state`。已在取消 / GraphRecursionError /
>    agent_error 三个 return 点前调 `db.abort_todos`（running→skipped，
>    pending 保留）。Q1 按「选项 a」落地。
> 4. **TurnCounterMiddleware 可用性**：`awrap_model_call` 钩子在已装
>    langchain 版本中存在（`model_retry.py` 等内置中间件在用），按方案正常落地。
> 5. **Q2（settled 字段）**：事件保留 `settled`，前端暂未消费（留作「N 步未
>    执行」提示的扩展点）。
> 6. **P2 补充决策**：轨迹面板仅 `!streaming` 且调用数 ≥2 时渲染（单次调用
>    无对比价值；流式期间卡片列表本身就是实时进度）。
> 7. **追加实施（用户实测反馈驱动，超出原方案）**：
>    - **失败重试链合并**（`MessageHelpers.tsx`）：相邻同工具且上一卡以
>      error 收尾时合并（error→error 续链、error→done 收链），`result`
>      保留最后非空（重试成功后图表正常展示）。纯成功链不合——多次成功
>      调用有各自结果，不能吞。第一版条件含 `failed_count > 0` 导致合并卡
>      永久吸附后续调用（多图表只显示一张），已被实测抓出并修正。
>    - **轨迹持久化**：turn/duration_ms 落库 tool_runs 表（migration + 写入
>      + api.ts 恢复映射），修复 TracePanel 刷新消失。历史恢复走
>      `history.py` 的 tool_runs 时间窗口归属，不走 message_parts。


---

## 0. 结论摘要

1. **教程的"结构化事件流 + 状态建模"Divine 已超额完成**；"画 Mermaid 流程图 / LangGraphics / `useStream`" 那条主干在 Divine 上不成立——`create_agent` 是预置 ReAct 图，只有 `agent ⇄ tools` 两节点，没有具名业务节点。
2. **Divine 已有三层"节点"素材（意图 / 轮次 / 工具耗时），一层都没往外发**。数据全在库里或已在算，缺的只是出网。
3. 审计中发现 **D1 是一个真实的状态归零缺陷**，优先级高于所有可视化需求。
4. 建议走「暴露意图层 + 画 ReAct 轨迹图」，**明确否决把手写 `StateGraph` 替掉 `create_agent`**。

---

## 1. 目标与非目标

### 目标

| 编号 | 目标 |
|---|---|
| G-1 | run 结束后，计划进度在 DB 与 UI 上一致，刷新会话不丢进度 |
| G-2 | 前端能拿到每次工具调用的轮次号与耗时 |
| G-3 | 前端能展示本轮命中的能力意图标签 |
| G-4 | 前端能画 ReAct 执行轨迹（轮次 × 工具 × 耗时），可看出循环与卡点 |

### 非目标

- 不改造 agent 图结构（`create_agent` 保持不变）
- 不引入 LangGraph Platform / LangGraphics / `@langchain/react`
- 不引入 Mermaid 渲染依赖
- 不改 `PlanCard` 的既有视觉风格

---

## 2. 现状盘点（已核实到行号）

### 2.1 已有能力

| 能力 | 位置 |
|---|---|
| SSE 自定义事件分发 | `divine-server/app/agent/core/sse.py:12-17` `_custom_sse` |
| `plan` 事件（计划全量 items） | `sse.py:53-55`（`create_plan`）、`:188-220`（`write_todos` HITL 审批） |
| `todo_update` 事件（单条状态） | `divine-server/app/agent/tools/execution.py:272` / `:1110` / `:1127` |
| `subagent` 事件（并行子任务） | `subagents.py:738` 起 |
| 计划落库 | `divine-server/app/db/todos.py:9-59` |
| 前端统一消费 | `divine-app/src/services/sse.ts:49-103` `consumeSSE` |
| 前端状态归并 | `divine-app/src/pages/chat/hooks/useChatStream.ts:136-160` |
| 计划卡片渲染 | `divine-app/src/pages/chat/components/MessageItem/index.tsx:403-445` `PlanCard` |
| 计划 HITL 审批 | `divine-server/app/agent/tools/tools.py:229-242` `HumanInTheLoopMiddleware` |
| 失败回流待办 | `divine-server/app/agent/state/plans.py:58-83` `_spawn_recovery_todo`（同类去重 + 上限 5 双闸） |

### 2.2 三层未暴露的素材

| 层 | 数据在哪 | 现状 |
|---|---|---|
| **意图层** | `app/agent/intent/intent.py:393-468` `classify_intents`，18 个标签；`:471-487` `intents_from_tool_history` 从工具历史反推 | 只喂给 `split_rule_sections` 裁剪 system prompt，结果存进 `ctx.intents`（`orchestrator.py:322`）后**算完即丢** |
| **轮次层** | `db/tool_runs.py:11-38` `save_tool_turn`（存 tool_calls + think，有 `order`） | **无轮次号，未发 SSE** |
| **工具耗时层** | `db/migrations.py:48-57` `tool_runs` 有 `started_at/finished_at`；`tool_runtime.py:210` `started = time.monotonic()`，耗时在 `:242`/`:263`/`:284` **已经算出来了** | 耗时只进 `logger.info`，**未进 SSE** |

> 这三个标签是 Divine 最接近"具名业务节点"的数据，且比教程里的 `classify/research/analyze/synthesize` 更贴合真实场景。

### 2.3 缺陷清单

#### D1（P0 · 数据正确性）run 结束时 todo 状态被整体归零

调用链：

```
orchestrator.py:678  _sync_todos_from_state(session_id, final_state)
  └─ persistence.py:145-156  只取 todo["content"]，丢弃 status
       └─ db/todos.py:9-25  replace_todos：DELETE 全部 + INSERT 全部 'pending'
```

后果：

1. 每轮 run 结束后，DB 里所有 todo 回到 `pending`（无论 `done` / `error`）
2. 该路径**不发任何 SSE**，前端 `PlanCard` 仍显示 `done/N` → 内存态与 DB 态分叉
3. 刷新会话后 `history.py:270` / `:344` 用 `list_todos` 恢复 → `PlanCard` 显示 **0/N**

测试覆盖：无。`tests/` 中仅 `test_recovery_loop.py:51,64` 直接调用了 `replace_todos`，未覆盖 `_sync_todos_from_state`。

#### D2（P0）进度粒度错位

`execution.py:265-276` 在**每次工具调用前**认领下一个 pending todo，`:1094-1114` 在该调用返回后**立即**置 done。语义被硬编码为「1 次工具调用 = 1 步完成」。

- 一步需多次调用 → 首次调用即标 done，后续调用顺延认领下游步骤 → 进度提前跑满，之后无 todo 可领
- 纯思考 / 纯回答不调工具 → 进度不动，末步可能永远卡 `running`

#### D3（P1）工具事件缺轮次号与耗时

`execution.py:912-934` 发出的 `tool` 事件只有 `tool / status / message / messageKey / call_id`，而 `tool_runs` 表与 `tool_runtime.py` 里这些数据都已存在。

#### D4（P1）意图标签算完即丢

见 2.2 意图层。

#### D5（P2）`skipped` 状态从未赋值

`state/plans.py:14` 与 `divine-app/src/types.ts:185` 都定义了 `skipped`，全代码库无赋值点（已 grep 确认）。

---

## 3. 路线取舍

### 路线 A · 暴露意图层（1–2h）

run 开始时发一次 `phase` 事件，前端渲染能力标签条。

> **诚实评价**：这是**静态标签，不是流程图**。它能说"这轮涉及 PDF 生成 + 图片生成"，但说不了"走到第几步"。单独做意义有限，须配路线 B。

### 路线 B · 把 ReAct 轨迹本身画成执行图（半天 ~ 1 天）← 推荐

ReAct 循环本身就是图，且是运行后才存在的动态图：节点 = 每轮模型决策 + 调用的工具，边 = 执行顺序 / 数据依赖（某工具输出的文件路径被下一个工具读取）。

比固定 pipeline 信息量更大，因为它能显示**循环、回溯、卡住**——正是教程夸 LangGraphics 的价值所在。

缺口：轮次号（现无）、耗时下发（库里有）、依赖边（可从 `tool_runs.input/output` 的路径推断，P2 再做）。

### 路线 C · 手写 `StateGraph` 替掉 `create_agent` → **否决**

- `tools.py:219-251` 挂着 7–8 个中间件，其中 **`TodoListMiddleware` 是 LangChain 内置的**，它提供 `write_todos` 工具 + `todos` state reducer + 引导模型使用它的 prompt 注入。手写图这三样要全部自己实现，还要重接 `HumanInTheLoopMiddleware` 的中断语义。
- 更致命的是**能力退化**：ReAct 的全部价值是让模型自主决定循环次数。真实任务是「读了再想 → 改了再测 → 测挂了再改」，固定 pipeline 做不到。
- 教程的 `classify→research→analyze→synthesize` 是**教学示例**，不是生产架构。

---

## 4. 事件协议规范

### 4.1 新增 `phase`

| 字段 | 类型 | 说明 |
|---|---|---|
| `intents` | `string[]` | 原始标签，如 `["pdf","image"]` |
| `labels` | `string[]` | 已本地化的展示名，如 `["PDF 生成","图片生成"]` |

时机：`run_agent` 内，`ctx.intents` 赋值（`orchestrator.py:322`）之后，**每 run 一次**。

### 4.2 扩展 `tool`

在现有字段基础上**追加**（不删改任何现有字段，向后兼容）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `turn` | `int` | 轮次号，从 1 开始 |
| `run_id` | `string` | `tool_runs.id`，前端可回查 |
| `started_at` | `string` | ISO8601，调用开始时发 |
| `duration_ms` | `int` | 仅 `done`/`error` 事件携带 |

### 4.3 新增 `plan_sync`

| 字段 | 类型 | 说明 |
|---|---|---|
| `items` | `TodoItem[]` | 全量计划（含 `id/index/title/status/result`） |
| `settled` | `int` | 本次被终态收敛的条数 |

时机：`run_agent` 内 `_sync_todos_from_state`（`orchestrator.py:678`）之后，每 run 一次。

---

## 5. 实施阶段

### P0-A · 修 D1 + D5：终态收敛（约 2h）

| 文件 | 改动 |
|---|---|
| `divine-server/app/db/todos.py` | 新增 `sync_todos(session_id, items)`：按 `(index, title)` 匹配**保留本地已有 status**，新增的置 `pending`，已消失的删除；替代 `replace_todos` 在收口路径的使用 |
| `divine-server/app/db/todos.py` | 新增 `settle_todos(session_id)`：`running → done`、`pending → skipped`，`done`/`error` 保持不变；返回被收敛条数 |
| `divine-server/app/agent/state/persistence.py:145-156` | `_sync_todos_from_state` 改为解析 `todo["status"]`（`in_progress→running`、`completed→done`）后调 `sync_todos`，再调 `settle_todos` |
| `divine-server/app/agent/orchestrator.py:678` 后 | `yield sse_event("plan_sync", {"items": items, "settled": n})` |
| `divine-app/src/services/sse.ts:10-35` | `SSEHandlers` 加 `plan_sync` |
| `divine-app/src/pages/chat/hooks/useChatStream.ts` | 加 `plan_sync` handler，复用 `plan` 的归并逻辑 |
| `divine-server/tests/` | 新增 `_sync_todos_from_state` 的状态保留与终态收敛两个用例 |

**收敛规则**：`running → done`（agent 已输出最终回答，视为该步收尾）、`pending → skipped`（未被认领，agent 判断无需执行）。这条规则顺带让 D5 的 `skipped` 有了真实语义。

**已知待确认**：用户中途停止（`cancel_event`）时走的是异常中断路径，`running → done` 不成立。见 §8 开放问题 Q1。

### P0-B · 修 D3：工具事件补轮次号与耗时（约 2h）

| 文件 | 改动 |
|---|---|
| `divine-server/app/agent/core/context.py:40-67` | `AgentRunContext` 加 `turn_index: int = 0` |
| `divine-server/app/agent/middleware/middleware.py` | 新增 `TurnCounterMiddleware(ctx)`，在 `awrap_model_call` 中自增 `ctx.turn_index` |
| `divine-server/app/agent/tools/tools.py:219-251` | 中间件栈中注册 `TurnCounterMiddleware`（须排在 `TodoSyncMiddleware` 之前） |
| `divine-server/app/agent/tools/tool_runtime.py:195-290` | `_run_adapter` 增加入参 `run_meta: dict`，回填 `run_id` / `started_at` / `duration_ms`（耗时已在 `:242`/`:263`/`:284` 算过，改成同时写进 `run_meta`） |
| `divine-server/app/agent/tools/execution.py:912-934` | `tool` 事件追加 `turn` / `run_id` / `started_at`；完成与失败事件追加 `duration_ms` |
| `divine-app/src/types.ts` | `ToolEvent` 加 `turn?` / `run_id?` / `started_at?` / `duration_ms?` |

**设计取舍**：不改 `_run_adapter` 的返回类型（避免波及 `subagents.py` 等其他调用方），改用入参 `run_meta` 字典就地回填。

### P1 · 修 D4：意图标签出网（约 1h + i18n）

| 文件 | 改动 |
|---|---|
| `divine-server/app/agent/orchestrator.py:323` 后 | `yield sse_event("phase", {"intents": sorted(intents), "labels": [...]})` |
| `divine-server/app/agent/intent/intent.py` | 新增 `INTENT_LABELS: dict[str, str]`（18 个标签 → 中文名） |
| `divine-app/src/services/sse.ts` | `SSEHandlers` 加 `phase` |
| `divine-app/src/pages/chat/hooks/useChatStream.ts` | 加 `phase` handler，写入 `message.intents` |
| `divine-app/src/types.ts` | `ChatMessage` 加 `intents?: string[]` |
| `divine-app/src/i18n/locales/*/translation.json` | 加 intent 展示名（zh-CN / zh-TW / en 三份） |

**标签映射建议**：只展示 `CONDITIONAL_SECTIONS`（`intent.py:59-74`）里那 14 个领域标签，`open_app/screenshot/lock_screen/search_file` 四个本地动作类不展示（对进度追踪无意义）。

### P2 · 执行轨迹甘特图（约 1 天，纯前端）

在 P0-B 数据到位后，chat 页新增可折叠的「执行轨迹」面板：

- 按 `turn` 分组，组内按 `started_at` 排序
- 每行 = 一次工具调用，横条长度 ∝ `duration_ms`
- 超过同轮中位数 3 倍的调用标琥珀色（疑似卡点）
- 依赖边（P2.5，可选）：从 `tool_runs.input/output` 提取文件路径，同路径的「写 → 读」连虚线

---

## 6. 风险与回滚

| 风险 | 等级 | 缓解 |
|---|---|---|
| P0-A 改 `replace_todos` 调用路径，影响计划重建 | 中 | `replace_todos` 保留不动（HITL 确认路径仍用它），只在收口路径改用新的 `sync_todos` |
| `awrap_model_call` 钩子在当前 langchain 版本不可用 | 中 | 实现前先验证；不可用时退化为「工具调用中 `call_id` 变化即视为新一轮」的启发式 |
| `tool` 事件加字段撑大 SSE 体积 | 低 | 新增字段均为标量，单事件增量 < 100 字节 |
| 前端无测试，改动靠构建验证 | 中 | 每阶段改完必须跑 `tsc -b` + `vite build` |

回滚：三个阶段互不耦合，任一阶段可独立 revert。P0-A / P0-B 均为「追加字段 + 新增函数」，无破坏性改写。

---

## 7. 验证清单

**后端**（每个阶段跑一次）

```bash
cd /Users/tanweijie/Desktop/TAN/ai-divine-desktop/divine-server
python -m pytest tests/ -q
```

**前端**（每个阶段跑一次）

```bash
cd /Users/tanweijie/Desktop/TAN/ai-divine-desktop/divine-app
npx tsc -b && npx vite build
```

**手工冒烟**

| 阶段 | 用例 | 期望 |
|---|---|---|
| P0-A | 发一个多步任务 → 等完成 → 刷新会话 | `PlanCard` 进度保持 `N/N`，不归零 |
| P0-A | 计划中途工具失败 | 该条保持 `error`，未被收敛成 `done` |
| P0-B | 发一个多轮工具任务 | 前端能拿到 `turn` 递增、`duration_ms` 非零 |
| P1 | 发「帮我做个 PDF 攻略」 | 出现 `pdf` 能力标签 |
| P2 | 同上 | 轨迹面板按轮次分组，耗时条长度合理 |

---

## 8. 开放问题

**Q1（阻塞 P0-A）**：用户中途点停止（`ctx.cancel_event`）时，run 走异常中断路径。此时 `running` 的 todo 应该收敛成什么？

- 选项 a：统一 `skipped`（保守，不谎报完成）
- 选项 b：`done`（与正常结束一致，但会高估进度）

我倾向 **a**，但需要确认现有取消路径是否会走到 `orchestrator.py:678`。

**Q2**：`settled` 字段前端要不要用？可用于提示「本轮有 N 步未执行」。若不做提示，可以从协议里去掉。

**Q3**：P2 的依赖边推断（从 input/output 提取路径）性价比如何？如果工具输出的 JSON 结构不统一，推断准确率可能很低。建议先做甘特条，依赖边留到实际用起来后再评估。

**Q4**：D2（进度粒度错位）是否在本方案范围内修？

- 治本方案是新增 `update_todo` 工具，让 LLM 显式标记步骤开始/结束 —— 但会新增工具 schema 与 prompt 指令，影响 token 预算与 agent 行为，建议**单独立项评审**。
- 本方案**不包含** D2 的修复。

---

## 9. 建议执行顺序

```
P0-A 终态收敛（2h）  →  P0-B 工具事件补字段（2h）  →  P1 意图标签（1h）  →  P2 甘特图（1d）
   修 D1+D5              修 D3                        修 D4                G-4
```

前三阶段都是「把已有的数据送出去」，不碰 agent 决策逻辑，回归风险低；P2 是纯前端新增。

按项目惯例：**先改不提交，审查后再提交。**
