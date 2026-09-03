# ask_user 中断收集补充信息 · 设计文档

> **状态：已实施（2026-09-03，未提交待审查）。** 4 个待确认项按评审默认定稿（见 §8 标注）；实施记录见 §9。
>
> 目标：让 Agent 在执行任务过程中，当关键信息缺失或需要在多个合理方案间选择时，主动暂停并向用户提问；用户以内联卡片形式补充信息后，Agent 从断点恢复执行，从而提升任务精准度、避免模型"瞎猜"。
>
> 参考机制：LangGraph `interrupt()` / `Command(resume=...)`（即 external HITL 方案一，未引入 `HumanInTheLoopMiddleware`，理由见 §2.3）。

---

## 1. 现状核实（已验证的既有链路）

Divine 已有一套完整的 interrupt 二元审批链路，本方案最大化复用：

| 环节 | 位置 | 说明 |
|------|------|------|
| 中断原语 | `divine-server/app/agent/tools/interrupts.py` | `_ask_interrupt(session_id, marker, payload)` → `interrupt(payload)`，`_ACTIVE_INTERRUPTS` 按 `(session_id, marker)` 去重 |
| 工具内审批 | `divine-server/app/agent/tools/execution.py` | 10 处调用（plan_choice / terminal / external_file / write_calendar / skill_* / subagents_write 等），以 `_handle_adapter_call` 内 plan_choice 分支（L98-137）为参考模板 |
| SSE 下发 | `divine-server/app/agent/core/sse.py` `_interrupt_sse`（L19-216） | 按 `payload["type"]` 分支，统一输出 `tool` 事件 + `status:"confirm"` + `confirm_type` |
| 等待与恢复 | `divine-server/app/agent/orchestrator.py` L560-647 | `interrupts` 分支：`create_terminal_decision(session_id)` 创建 `asyncio.Event` → yield `_interrupt_sse` → `await pending["event"].wait()`（180s 超时）→ 组装 `resume_values` → `Command(resume=...)` |
| 决策回传 | `divine-server/app/api/terminal.py` | `POST /api/terminal/decide` `{session_id, allow}` → 置 `pending["allowed"]` 并 set event；`_PENDING_TERMINAL` 按 session_id 存活 |
| 前端消费 | `divine-app/src/services/sse.ts` | `consumeSSE` 按 event 名分发 handler，`tool` 事件已通用地接入 |
| 前端渲染 | `divine-app/src/pages/chat/components/MessageItem/ToolStatusCard.tsx` L78-105 | `decide(allow)` → `request("/terminal/decide", {session_id, allow})`；确认区已拆到 `ToolConfirmSection.tsx` |
| 类型定义 | `divine-app/src/types.ts` L60-92 | `ToolEvent.confirm_type` 联合类型 |

**关键缺口**：resume 值只有二元语义（`{"allowed": bool}` 或 `{"decisions":[approve/reject]}`）；前端确认区只有按钮，没有输入控件；没有"补充信息型"的工具。

**不引入 `HumanInTheLoopMiddleware` 的理由**：现有 10 处中断全部是自定义 `_ask_interrupt` + 自定义 resume 值的直通路径，orchestrator 对 `action_requests`（middleware 路径）和自定义 payload 是两套分支；ask_user 走直通路径改动最小、语义最清晰（resume 值即用户答案）。

> **2026-09-03 评审定稿**：维持双轨——ask_user 按本文档走自定义 interrupt 路径实施；8 个审批门（subagents_write / skill_migrate / skill_migrate_batch / skill_install / external_file / git / bg_kill / terminal）向 middleware 的迁移作为**独立架构演进**，不与本次绑定，见 `docs/hitl-middleware-migration.md`（含触发条件、风险清单与分期路径）。

---

## 2. 总体时序

```
Agent 判断信息缺失
  → 调用 ask_user 工具（question / options / input_type）
  → execution.py 特判 → _ask_interrupt(payload) → LangGraph interrupt() 暂停
  → orchestrator 捕获 interrupts → 创建 answer pending → SSE 下发
      event: tool  {tool:"ask_user", status:"confirm", confirm_type:"ask_user",
                    question, options, input_type, call_id, session_id}
  → 前端 ToolStatusCard 内联渲染 AskUserForm（text / 单选 / 多选）
  → 用户提交 → POST /api/chat/answer {session_id, call_id, answer}
      （乐观更新：卡片冻结显示答案）
  → pending event 触发 → resume_values = {"answer": ..., "allowed": true}
  → Command(resume=...) → interrupt() 返回 → 答案作为 ask_user 工具结果回到模型
  → Agent 继续执行，后续 SSE 正常流出
```

---

## 3. 后端设计

### 3.1 工具定义与注册 · `app/tools/adapters/ask_user.py`（新增）

```python
ASK_USER_DESCRIPTION = """当需要澄清模糊需求、让用户在多个合理方案间选择、\
或获取只有用户才知道的关键信息时，调用此工具向用户提问并等待回答。

适用：需求有歧义且直接影响执行结果；存在多个都合理的方案需要用户拍板；\
缺失只有用户能提供的信息（预算、偏好、账号、路径等）。
不适用：简单的 yes/no 执行确认（已有确认机制）；你能从上下文推断的信息；\
对结果没有影响的细节。每次只问一个最关键的问题。"""

def ask_user(
    question: str,                      # 具体问题，需说明"为什么问"
    options: list[str] | None = None,   # 提供时渲染为可点选项
    input_type: str = "text",           # text | single_choice | multi_choice
) -> dict:
    ...
```

- 注册方式与现有 adapter 一致（参照 `web_search.py` / `write_calendar.py` 的参数声明 + 注册写法）。
- 加入 `_READ_ONLY_TOOLS` / `_NO_PLAN_TOOLS` 白名单（`execution.py` 顶部已有这两组常量），避免 ask_user 自身触发 plan_choice、也不需要写权限确认。
- 无副作用、轻 IO，走 in-process 路径即可，不进 subprocess。

### 3.2 执行路径 · `app/agent/tools/execution.py`

在 `_handle_adapter_call` 的特判区（plan_choice 分支附近）新增 `name == "ask_user"` 分支：

```python
if name == "ask_user":
    decision = _ask_interrupt(
        ctx.session_id,
        f"ask_user:{call_id}",
        {
            "type": "ask_user",
            "session_id": ctx.session_id,
            "call_id": call_id,
            "question": arguments.get("question", ""),
            "options": arguments.get("options") or [],
            "input_type": arguments.get("input_type") or "text",
        },
    )
    answer = decision.get("answer") if isinstance(decision, dict) else None
    if not answer:  # 超时 / 空回答
        answer = "（用户未在限时内回应，请基于当前信息按最佳判断继续，不要再重复提问）"
    writer({"event": "tool", "tool": "ask_user", "status": "done",
            "call_id": call_id, "session_id": ctx.session_id,
            "message": "已收到补充信息"})
    return {"answer": answer}
```

工具返回值进入 ToolMessage，模型自然拿到答案继续推理；同时受现有"ToolMessage 超 600 字符 stub 化"的上下文治理约束（答案本身通常很短，无风险）。

### 3.3 SSE 事件契约 · `app/agent/core/sse.py` `_interrupt_sse`

新增 `kind == "ask_user"` 分支（放在 `plan_choice` 分支之后）：

```python
if kind == "ask_user":
    return sse_event(
        "tool",
        {
            "tool": "ask_user",
            "status": "confirm",
            "confirm_type": "ask_user",
            "message": payload.get("question", ""),
            "question": payload.get("question", ""),
            "options": payload.get("options") or [],
            "input_type": payload.get("input_type") or "text",
            "call_id": payload.get("call_id", ""),
            "session_id": session_id,
        },
    )
```

沿用既有 `tool` 事件通道（不新增 event 名），前端 `consumeSSE` 零改动即可收到，差异只在 `confirm_type` 与新增字段。

### 3.4 决策回传通道 · `app/api/terminal.py` + 路由

现有 `_PENDING_TERMINAL[session_id] = {"event", "allowed"}` 是二元槽位。扩展为支持携带答案：

- `create_terminal_decision(session_id)` 的 pending dict 增加 `"answer": None` 槽位（向后兼容，`allowed` 语义不变）。
- `TerminalDecision` 模型增加可选字段 `answer: str | list[str] | None = None`；`decide_terminal` 同时写入 `pending["answer"]`。
- 新增语义化路由（挂到 chat router，前端走 `/api` 代理）：

```python
@router.post("/chat/answer")
async def answer_chat_question(request: ChatAnswer):
    """session_id + call_id + answer，内部转写为对同一 pending 的 set。"""
```

> 说明：orchestrator 的等待循环是逐 item 串行 await（L563-577），同一 session 同一时刻只有一个未决 pending，因此**沿用按 session_id 单槽位的设计即可，不需要按 call_id 建索引**。`call_id` 仅用于前端卡片配对校验。
> 备选方案（新建独立 `_PENDING_ANSWERS` 注册表）语义更干净，但会复制 event 生命周期管理代码，收益低；如评审认为 terminal.py 语义混杂，可在实施时把 pending 注册表抽到 `app/api/decisions.py` 共用，行为不变。

### 3.5 orchestrator 恢复分支 · `app/agent/orchestrator.py` L560-647

在 `interrupts` 分支内、读取 `allowed` 之后新增：

```python
if payload.get("type") == "ask_user":
    resume_values[item.id] = {
        "allowed": True,
        "answer": pending.get("answer"),
    }
    continue   # 跳过 approve/reject / action_requests 组装逻辑
```

### 3.6 超时与降级

- 复用 180s 超时（与现有确认一致）。超时 → `answer` 为空 → execution.py 降级为"按最佳判断继续"的工具结果（见 3.2），**不中断会话、不报错**。
- 会话被用户取消（cancel_event）时，现有 `_persist_partial_generation` 逻辑照常生效，无需特殊处理。

### 3.7 持久化与历史回显

- 工具调用本身已由 `tool_runs` 表与既有 message_parts 机制落库（与其它工具一致，无额外工作）。
- **问答对回显**：为让会话重载后 UI 能重建"已回答的 ask_user 卡片"，在 execution.py 拿到答案后、return 之前，把 `{question, answer, options, input_type}` 写入该 ToolMessage 的 `tool_runs` 记录（或 message_parts 的 tool 元数据，实施时对齐现有 `tool_runs` 落库字段）。前端重建历史时，从 tool 元数据渲染冻结态卡片（见 §4.3）。

---

## 4. 前端设计

### 4.1 类型扩展 · `divine-app/src/types.ts`

```ts
confirm_type: ... | "ask_user";
// ToolEvent 新增可选字段：
question?: string;
options?: string[];
input_type?: "text" | "single_choice" | "multi_choice";
```

### 4.2 渲染 · `ToolConfirmSection` 新增 ask_user 分支

`confirm_type === "ask_user"` 时渲染新组件 `AskUserForm`（与 `ToolCommands` / `ToolFileList` 同级，放 `pages/chat/components/MessageItem/`）：

- **text**：单行 input（问题短）/ textarea（问题含上下文，>60 字时），Enter 提交。
- **single_choice**：选项渲染为 `div role="radio"` 列表（沿用 Divine 无原生 button 规范），选中态用主题色 8% 透明度背景填充（低饱和，不做描边 hover），键盘 ↑↓ 移动、Enter 确认。
- **multi_choice**：同上 `role="checkbox"`，可多选，底部"确认选择"用 `@/components/ui/Button`。
- 卡片顶部保留 ToolStatusCard 的工具图标行（tool=ask_user，status=confirm），问题文本即 `statusMessage`，**在问题下方加一行 12px 弱化说明**（i18n key：`tool.askUserHint`："回答后 Agent 将继续任务"），降低认知负担。

### 4.3 交互状态机

```
confirm（待回答）→ answered（已提交，乐观冻结）→ done（收到后端 done 事件，终态）
                              ↘ 超时（后端 done 事件 message="用户未回应…"，同样冻结）
```

- **乐观更新**：点击提交瞬间本地置 `answered` 态——输入控件替换为答案文本（用户答案以对话气泡样式靠右显示在卡片下方，或卡片内引用块，实施时二选一），按钮转 loading；不等待 POST 返回。
- **冻结**：answered 后移除全部输入控件，仅展示问答对；历史重建时直接渲染冻结态（数据来自 §3.7 的 tool 元数据）。
- **防重复提交**：沿用 `deciding` state 模式。
- **输入框**：pending 期间底部输入框不强制禁用（与现有 plan confirm 行为保持一致），但提交新消息会排队到当前轮结束后处理，不做额外拦截。

### 4.4 提交 API

`AskUserForm` 内 `request("/chat/answer", {method:"POST", body: JSON.stringify({session_id, call_id, answer})})`，与 `ToolStatusCard.decide` 的错误处理模式一致（失败显示 `tool.answerFailed` 重试提示，卡片回到可编辑态）。

### 4.5 i18n

新增 key：`tool.askUserHint` / `tool.askUserSubmit`（"发送回答"）/ `tool.askUserTimeout`（"用户未回应，Agent 已按最佳判断继续"）/ `tool.answerFailed`。中英两份 locale 同步补齐。

---

## 5. Prompt 策略（何时该问）

除工具描述（§3.1）外，在 agent 系统提示词中补一段约束：

1. **每轮最多 ask_user 一次**（execution.py 侧硬限：`ctx` 上加计数器，第二次调用直接返回提示文本，不触发 interrupt）。
2. 问题必须"一次一个关键点"，禁止打包多个问题。
3. `question` 中说明为什么问（模板："为了 <目的>，需要确认 <信息>"）。
4. 能从上下文/记忆推断的信息不问；`single_choice` 优先于 `text`（给选项比开放题回答率高）。
5. 用户答案若具长期价值，由模型自行决定是否调用既有 memory 工具沉淀（复用现有 `user_memories` 机制，不新增逻辑）。

---

## 6. 边界与风险

| 风险 | 处置 |
|------|------|
| 用户长时间不回答 | 180s 超时降级为"按最佳判断继续"，会话不卡死 |
| subagent 内调用 ask_user | **禁止**：ask_user 不注册进 subagent 工具集，仅主 Agent 可用（子代理无 SSE 通道到用户） |
| React/middleware 路径冲突 | ask_user 走自定义 payload 路径，`action_requests` 分支不受影响；需回归验证两条分支互不干扰 |
| scheduled task 场景无人应答 | 定时任务上下文无用户在线，180s 必超时 → 降级文本进入结果，可接受；后续可在定时任务执行时禁用 ask_user（列入待确认） |
| 恶意/超长答案 | 答案长度截断 2000 字符（execution.py 侧），走 `_compact_for_context` 兜底 |
| 会话中途刷新页面 | interrupt 状态在 LangGraph checkpointer 中，但 SSE 连接断开后 pending event 等待 180s 超时降级；刷新后历史回显冻结卡片（§4.3），用户可发新消息继续 |

---

## 7. 实施步骤与验证

1. **后端**：adapter → execution.py 分支 → sse.py 分支 → terminal.py answer 槽位 + `/chat/answer` → orchestrator 分支（顺序即依赖序）。
2. **测试**：`tests/` 新增用例——① ask_user interrupt payload 结构；② resume answer 回传后工具结果正确；③ 超时降级；④ 每轮一次硬限；⑤ 与 plan_choice 同轮共存的分支隔离。跑全量 pytest 确认 611 个存量用例无回归。
3. **前端**：types → AskUserForm → ToolConfirmSection 接线 → i18n。`tsc -b` + `vite build` 通过（前端无测试，构建即验证）。
4. **不提交**：全部改动留在工作区，按惯例由用户审查后决定提交。

## 8. 待确认问题（2026-09-03 已全部定稿）

1. `/chat/answer` 挂 chat router 还是复用 `/terminal/decide` 加字段？——**定稿：新路由挂 chat router**（`POST /api/chat/answer`），内部调用 terminal.py 的 `resolve_terminal_answer` 写同一 pending 槽位。
2. multi_choice 场景目前没有明确产品需求，是否首期只做 text + single_choice？——**定稿：首期只做 text + single_choice**，类型与 schema 预留 multi_choice 但不渲染。
3. 定时任务（scheduled task）执行链路是否直接禁用 ask_user？——**定稿：禁用**。scheduler 以 `approval_mode="full"` 调用 run_agent；`_handle_ask_user` 对 full 模式直接跳过提问并提示模型按最佳判断继续（与既有"完全访问模式无确认"语义一致）。
4. 用户答案的 UI 呈现：卡片内引用块 vs 独立用户气泡？——**定稿：卡片内引用块**（`AskUserForm` 提交后冻结渲染"你的回答"引用块，与 confirm 卡片视觉一致）。

---

## 9. 实施完成记录（2026-09-03）

改动全部留在工作区**未提交**，供审查。

**后端**
- `app/tools/adapters/ask_user.py`（新增）：`@register_tool` 注册，schema 为 question(required) + options(≤8) + input_type(text/single_choice)。
- `app/tools/adapters/__init__.py`：注册导入。
- `app/agent/core/constants.py`：`ask_user` 加入 `_READ_ONLY_TOOLS` 与 `_NO_PLAN_TOOLS`（自身不触发 plan_choice、plan-first 门放行）。
- `app/agent/core/context.py`：`AgentRunContext.ask_user_count`（每轮一次硬限）。
- `app/agent/tools/execution.py`：`_handle_ask_user` 特判——full 模式跳过、每轮一次、interrupt payload（question/options/input_type/call_id）、resume answer 解析、2000 截断、超时/空答降级 `_ASK_USER_FALLBACK` + done 事件（messageKey: askUserAnswered/askUserTimeout）。
- `app/agent/core/sse.py`：`_interrupt_sse` 新增 `ask_user` 分支（tool 事件 + confirm_type=ask_user + question/options/input_type）。
- `app/api/terminal.py`：pending 槽位加 `answer`；新增 `resolve_terminal_answer`；`shutdown_terminal` 不受影响。
- `app/schemas.py`：`ChatAnswer{session_id, call_id, answer}`。
- `app/api/chat.py`：`POST /api/chat/answer`（404 会话不存在 / 409 无未决提问）。
- `app/agent/orchestrator.py`：interrupt 循环内 `type=="ask_user"` → resume `{"allowed": True, "answer": pending["answer"]}`（continue 跳过二元组装）。
- `app/agent/tools/subagents.py`：`ask_user` 加入 `_SUBAGENT_FORBIDDEN_TOOLS`（subagent 无 SSE 通道，天然禁用）。
- `app/agent/core/prompt_sections.py`：`_GENERAL_RULES` 追加 ask_user 使用约束（一次一问、选项优先、能从上下文推断的不问）。
- `tests/test_ask_user.py`（新增 12 用例）：注册/schema、白名单、SSE 形状、答案回传、每轮一次、full 跳过、超时降级、截断、端点 409/404/成功、terminal 二元通道回归。全部通过。

**前端**
- `types.ts`：`confirm_type` 增 `"ask_user"`；ToolEvent 增 `question/options/input_type`。
- `AskUserForm.tsx`（新增）：text(textarea)/single_choice(div role=radio，键盘 Enter/Space)内联表单；提交乐观冻结为"你的回答"引用块，失败回退可编辑并提示；Enter 提交。
- `ToolConfirmSection.tsx`：`confirm_type==="ask_user"` 分支渲染 AskUserForm（问题由卡片头部 statusMessage 展示，不重复）。
- `ToolStatusCard.tsx`：tool 名映射"向用户提问"。
- `index.less`：ask-user 表单样式（低饱和选中态、引用块）。
- i18n：zh-CN/en/zh-TW 补 `tool.askUserTitle/Hint/Submit/Placeholder/Answered/Timeout/AnswerFailed/AnswerLabel`。

**验证**
- 后端：`tests/test_ask_user.py` 12/12、`test_user_injection.py` 9/9；全量 pytest 709 通过 / 1 失败（`test_rewrite_routed`，预存失败与本次无关）。
- 前端：`tsc -b` + `vite build` 通过。

**范围裁剪（如实记录）**
- §3.7 问答对历史回显**未实现**：全库目前没有任何 confirm 类型持久化问答元数据（tool_runs 无写入方），V1 与其他确认卡片同级；刷新后 ask_user 卡片不重建冻结态。若要补齐需先建立 tool 元数据持久化通道，属独立改动。
- 定时任务场景用 full 模式跳过实现（见 §8-3），未单独区分 scheduled 标志。

**关键发现（图级集成测试证实，2026-09-03）**
- langchain 1.3.15 对**工具内 interrupt** 的 `Command(resume)` 语义是"整体重放该工具调用"：恢复时工具函数从头再执行一次，resume 值在重放帧的 `interrupt()` 处返回（与文档所说"回到中断点继续"不同；普通图节点内 interrupt 才是回到中断点）。
- 后果：任何"interrupt 之前改变状态/自增计数"的逻辑都会被重放误伤。ask_user 已用 `_ACTIVE_INTERRUPTS` marker 存活状态区分"重放（放行到 interrupt 消费 resume）"与"本轮第二次真提问（拦截）"。
- **对既有 8 个审批门的潜在影响（预存行为，本次未改动，需后续核查）**：execution.py 中 todo 认领发生在部分中断分支之前，若重放导致二次认领同一/下一 todo，可能与用户感知不一致；plan_choice/terminal 等因无 pre-interrupt 副作用（仅 interrupt 后置位）不受影响。建议在 `docs/hitl-middleware-migration.md` 的风险清单中补充该语义事实。
- 验证锚点：`tests/test_graph_level_hitl.py`（真图 + 脚本化模型跑通 ask_user 全链路与 steering 注入）。
