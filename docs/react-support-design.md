# ReAct（文本推理-行动循环）支持设计

> 版本：v1.0
> 日期：2026-08-22
> 状态：设计方案（待评审）
> 关联模块：`divine-server/app/agent/react.py`（新增）、`divine-server/app/agent/tools.py`、`divine-server/app/agent/prompts.py`、`divine-server/app/agent/context.py`、`divine-server/app/agent/sse.py`、`divine-server/app/agent/orchestrator.py`、`divine-server/app/config.py`、`divine-server/app/schemas.py`、`divine-server/app/api/chat.py`、`divine-server/app/api/settings.py`、`divine-app/src/components/SettingsModal/ModelSection.tsx`、`divine-app/src/types.ts`、三个 locale 文件

## 1. 背景与目标

当前 Agent 走 LangChain v1 `create_agent`（LangGraph）+ **原生函数调用**：模型通过 `bind_tools` 拿到工具 schema，直接输出结构化 `tool_calls`，LangGraph 的 tools 节点执行后以 `ToolMessage` 回填。这条链路有两个硬性前提：

1. 模型/端点必须支持 OpenAI 兼容的 `tools` 参数与 `tool_calls` 返回。
2. 模型必须能稳定地把参数填成合法 JSON（原生调用对 schema 约束很敏感）。

实际场景中这两点并不总能满足：不少本地/第三方 OpenAI 兼容端点（Ollama、LM Studio、各类代理网关）只支持纯文本 chat/completions；个别模型在文本格式下规划多步工具调用反而更稳。此时工具系统完全不可用，体验退化成一个"只会聊天"的助手。

本设计引入 **ReAct（Reasoning + Acting）文本模式**作为原生函数调用之外的第二种工具执行范式：

- 模型以纯文本输出 `Thought: …`（推理）与 `Action: 工具名` + `Action Input: {JSON}`（行动），由系统解析并执行工具，把结果以 `Observation` 形式喂回模型，循环直到输出 `Final Answer`。
- ReAct 只依赖 chat/completions 的纯文本能力，**不要求端点支持函数调用**。
- 在既有 LangGraph Agent 架构内实现：通过一个中间件把"文本 ReAct 轨迹"在模型节点出口改写为标准的 `tool_calls`，**后续工具执行、审批、待办、SSE 全部复用现有链路，零新增协议**。
- 每个模型条目增加 `tool_mode` 配置（`auto` / `native` / `react`），按模型选择执行范式。

### 目标

- 为不支持原生函数调用的模型/端点提供可用的工具调用能力（ReAct 文本模式）。
- 模式切换收敛为模型级配置，默认 `auto`（即原生），不改变现有用户行为。
- 复用全部现有基础设施：中间件审批（写文件确认、终端策略、git、计划审批）、TodoSync、工具轮次上限、检查点、SSE 事件流、历史持久化。
- ReAct 的 `Thought` 以现有 `think` 事件流式展示（ThinkBlock），`Action`/`Action Input` 脚手架不出现在正文。

### 非目标

- 不做"原生调用失败后自动降级 ReAct"的运行时探测（v1.5 演进，见 §9）。
- 不新增 SSE 事件类型、不新增数据库表/字段。
- 不改造子 Agent（`run_subagents` 内部仍用原生模式；v2 可让子任务按主运行继承 `tool_mode`）。
- 不做 ReAct 的多 Action 并行（v1 每轮一个 Action；v2 演进）。

## 2. 使用场景

### 2.1 不支持函数调用的端点/模型

- 本地推理服务（Ollama / LM Studio 等）接入 `base_url`，端点不认 `tools` 参数。
- 代理/网关类 OpenAI 兼容地址，只透传文本对话。
- 自定义模型条目显式选择 `tool_mode: react` 后，`read_file`、`web_fetch`、`search_files`、`calculator` 等工具恢复可用。

### 2.2 需要可观测推理轨迹的场景

- ReAct 的 `Thought` 天然是逐步推理，与 DeepSeek 的 `reasoning_content` 一样在 UI 的 ThinkBlock 里展示，用户能看清"为什么调用这个工具"。

### 2.3 调试/对比

- 开发与评测时对同一模型强制 `tool_mode: react`，对比两种范式的工具调用准确率与 token 消耗。

### 2.4 明确排除

- DeepSeek / 原生支持函数调用的端点：默认 `auto`→原生，不主动切 ReAct（原生更省 token、参数校验更强）。

## 3. 整体架构

ReAct 模式复用 `create_agent` 的同一张图：model 节点 → 条件路由 → tools 节点，中间件栈不变。差异只在两处：**模型调用时不绑定 tools**（强制纯文本输出），以及**模型节点出口把文本轨迹改写为 tool_calls**。

```mermaid
flowchart TB
  A[用户消息] --> B[model 节点<br/>ReActParseMiddleware.wrap_model_call]
  B -->|request.override tools=[]| C[LLM 纯文本流式输出<br/>Thought / Action / Action Input / Final Answer]
  C -->|流式 token| D[SSE 层 ReActStreamProcessor<br/>Thought→think 事件<br/>Action 脚手架→抑制<br/>正文→message 事件]
  C -->|完整消息| E[ReActParseMiddleware<br/>解析轨迹并改写 AIMessage]
  E -->|有 Action| F[tool_calls 注入 AIMessage<br/>thought 保留在消息 id 对应 think_by_id]
  E -->|无 Action 即 Final Answer| G[图结束]
  F --> H[条件路由 → tools 节点]
  H --> I[既有 _handle_adapter_call<br/>审批/终端策略/待办/SSE tool 卡片]
  I -->|ToolMessage Observation| B
  G --> J[持久化：tool_turn + think + 最终回答<br/>与原生模式完全一致]
```

关键机制：

- **执行桥**：`ReActParseMiddleware.wrap_model_call(request, handler)` 先 `request.override(tools=[])` 让模型按纯文本输出（`create_agent` 的 `_get_bound_model` 依 `request.tools` 决定是否 `bind_tools`），拿到完整回复后把 `Action:` 解析成 `tool_calls` 写回 `AIMessage`。对 LangGraph 而言，模型"照常"返回了带 `tool_calls` 的消息 → 条件路由、tools 节点、`HumanInTheLoopMiddleware`（write_todos 审批）、`ToolCallLimitMiddleware`、检查点全部照常工作。
- **流式体验**：`wrap_model_call` 只在模型调用结束时拿到完整消息，token 流已经在路上。因此新增 `ReActStreamProcessor`（参照现有 `DsmlStreamProcessor` 的增量解析模式）挂在 SSE 消费层，把流式 token 实时分类：`Thought:` 内容 → `think` 事件，`Action:`/`Action Input:`/`Observation:` 脚手架 → 抑制（真正的工具卡片由 `_handle_adapter_call` 后续发出），其余正文 → `message` 事件。用户不会看到 `Action:` 文本闪现。
- **持久化零改动**：改写后的 `AIMessage` 保留原始消息 id，`_consume_message` 以该 id 累积的 think 文本进入 `think_by_id`，`_persist_new_messages` 对带 `tool_calls` 的消息走 `save_tool_turn`（think + 调用 + 结果），最终 `Final Answer` 消息走 `add_message`，与原生模式同一套代码。

## 4. 后端设计

### 4.1 模式配置：tool_mode

模型条目新增字段（`divine-server/app/config.py`）：

| 取值 | 含义 |
| --- | --- |
| `auto` | 默认。解析为原生函数调用（当前行为不变） |
| `native` | 强制原生函数调用 |
| `react` | 强制 ReAct 文本模式 |

- `normalize_models` / `merge_model_updates` / `default_model_entry` 增加 `tool_mode` 字段，缺省 `"auto"`，非法值回退 `"auto"`（兼容旧配置：历史 models 条目无此字段，照常通过）。
- 生效顺序（从高到低）：请求级 `tool_mode`（`StreamChatRequest` 新增可选字段，仅调试用）→ 模型条目 `tool_mode` → `"auto"`。
- `AgentRunContext` 增加 `tool_mode: str = "auto"`；`orchestrator.run_agent` 解析生效值后传入（逻辑放 `agent/llm.py` 或 orchestrator 内聚函数 `_resolve_tool_mode`）。
- `app/api/health` 响应增加 `tool_mode` 字段（展示当前生效范式，方便验收）。

### 4.2 ReAct 格式与 Prompt（app/agent/react.py）

固定使用英文关键词，避免中文分词歧义，也便于增量解析：

```text
Thought: 对当前步骤的简要推理
Action: 工具名
Action Input: {"参数名": 值}    # 必须是合法 JSON 对象，可与 Action 同一行：Action: tool_name({...})
```
结束输出：
```text
Final Answer: 最终回答
```

在 `_build_dynamic_prompt` 中，当 `ctx.tool_mode == "react"` 时追加 `REACT_FORMAT_PROMPT` 区块（`react.py` 常量）：

```text
【ReAct 文本工具调用模式】
当前模型不启用原生函数调用，需要调用工具时按以下格式逐行输出（关键词固定为英文）：
Thought: 推理
Action: 工具名
Action Input: {"参数": 值}
工具执行结果会以 Observation 形式返回给你；根据结果继续 Thought → Action，直到完成；
完成时以 “Final Answer: ” 开头输出最终回答。
规则：
- Action 只能使用系统提供的工具名，Action Input 必须是合法 JSON 且与工具参数定义一致；
  参数不确定时先用 read_file / search_files 了解情况，不要编造；
- 每轮只输出一个 Action；不要输出 XML/伪代码形式的调用；不要杜撰工具；
- 正文中的普通解释文字可以正常输出，但不要与 Action 格式混淆。
```

说明：现有 `SYSTEM_PROMPT` 的"不要输出 XML 或伪代码形式的工具调用"与 ReAct 不冲突（Action 行不是 XML），无需改写系统提示；`create_plan` → `write_todos` 的替换逻辑等保持不变。

### 4.3 ReActParseMiddleware（执行桥，app/agent/react.py）

```python
class ReActParseMiddleware(AgentMiddleware):
    """把文本 ReAct 轨迹改写为标准 tool_calls，复用 LangGraph 工具执行链路。"""

    def wrap_model_call(self, request, handler):
        # 1) 模型不绑定 tools，强制纯文本输出
        if request.tools:
            request = request.override(tools=[])
        response = handler(request)
        if not response.result:
            return response
        message = response.result[0]
        if not isinstance(message, AIMessage):
            return response
        trace = parse_react_trace(_content_text(message.content))
        if trace is None or not trace.actions:
            # 无 Action：Final Answer（或纯文本回答），去掉前缀后透传
            if trace is not None and trace.final_answer:
                return response  # 见 4.5 的最终回答改写
            return response
        calls = [
            {
                "id": f"react_{index}_{uuid4().hex[:8]}",
                "name": action.name,
                "args": action.arguments,
                "type": "function",
            }
            for index, action in enumerate(trace.actions)
        ]
        rewritten = AIMessage(
            content="",                       # 脚手架不在正文；Thought 走 think 事件
            tool_calls=calls,
            id=message.id,                    # 关键：与流式消息同 id，think_by_id 才能对上
            usage_metadata=message.usage_metadata,
            additional_kwargs=message.additional_kwargs,
            response_metadata=message.response_metadata,
        )
        return ModelResponse(result=[rewritten], structured_response=response.structured_response)
```

要点：

- 中间件放在 middleware 列表**最前**（最外层），确保 tools 覆盖在链路上游生效；`ModelCallLimitMiddleware` 等计数不受影响（模型仍每轮只调用一次）。
- 中间件 `name` 需唯一（`create_agent` 断言去重），命名 `react_parse`。
- 改写消息 `content=""` + `tool_calls`：持久化走 `save_tool_turn`（不读 content），DeepSeek 请求序列 `assistant(tool_calls) → tool` 合法（现有 `ReasoningChatDeepSeek._get_request_payload` 对"有 tool_calls 的空 content 消息"不会丢弃）。
- 若模型忽略格式直接输出正文（无 Action），中间件原样透传，图正常结束——ReAct 模式对"不守格式的模型"退化为普通聊天，不报错。

### 4.4 轨迹解析器 parse_react_trace

`react.py` 内一个纯函数，行级扫描（`re.IGNORECASE`，允许前导空白与中文冒号）：

- `^Thought\s*[:：]` → 累积到 `thoughts`；后续未命中任何关键词的行追加到上一个 Thought（多行推理）。
- `^Action\s*[:：]\s*(.+)$` → 提取工具名（去尾随标点/代码围栏）；若同行带 `({...})` 一并解析。
- `^Action Input\s*[:：]\s*(.*)$` → JSON 提取：优先整行 `json.loads`，失败则做**花括号配对**截取第一个 `{...}` 再解析；仍失败记 `arguments={}` 并在日志告警（让工具 schema 校验兜底，见 §6）。
- `^Observation\s*[:：]` → 视为模型回显，忽略（真实结果以 ToolMessage 形式给模型）。
- `^Final Answer\s*[:：](.*)$` → 该行及之后所有文本（含后续普通行）为 `final_answer`。
- 其余行 → `prose`（正文）。

返回 `ReActTrace(thoughts, actions, final_answer, prose)`；没有任何关键词时返回 `None`（透传）。

### 4.5 最终回答改写

`Final Answer:` 前缀需要从正文去掉，否则会原样展示给用户。两处配合：

- **SSE 层**：`ReActStreamProcessor` 识别到 `Final Answer:` 行首后，后续文本照常以 `message` 事件输出（前缀本身被抑制）——用户实时看到的就是干净的最终回答。
- **持久化层**：中间件在无 Action 且 `final_answer` 存在时，把消息 content 改写为 `final_answer`（去掉前缀），保证刷新/历史恢复与实时一致。改写同样保留 `id`，think 已由流式层累积。

### 4.6 ReActStreamProcessor（流式过滤，app/agent/react.py）

参照 `DsmlStreamProcessor` 的增量状态机（缓冲 + 游标 + 前缀匹配，天然容忍 token 分片）：

| 输出类型 | 触发 | 动作 |
| --- | --- | --- |
| `think` | `Thought:` 行及续行 | 累积到 `reasoning_parts`（进入 `think_by_id`），发 `sse_event("think", ...)` |
| `suppressed` | `Action:` / `Action Input:` / `Observation:` 行 | 不向客户端转发（真实工具卡片稍后由 `_handle_adapter_call` 发出） |
| `message` | 其余正文 / `Final Answer:` 之后的文本 | 发 `sse_event("message", ...)` |

接入点：`agent/sse.py` 的 `_consume_message` 增加 `react: bool` 参数；`react=True` 时 `drain_text()` 不再直接转发 `message.text`，而是逐 token 喂给 `ReActStreamProcessor`，把返回事件分类转发。`_stream_agent_run` 增加透传参数（由 orchestrator 依据 `ctx.tool_mode == "react"` 传入）。`message.reasoning` 通道不变（`think=True` 时 DeepSeek 的 `reasoning_content` 仍走原路径，与 ReAct 的 Thought 叠加展示，均为 think 事件）。

### 4.7 配置管线改动清单

| 文件 | 改动 |
| --- | --- |
| `app/config.py` | `default_model_entry` / `normalize_models` / `merge_model_updates` 增加 `tool_mode`（缺省 `"auto"`，白名单校验 `{"auto","native","react"}`） |
| `app/schemas.py` | `StreamChatRequest.tool_mode: str | None = None`；`ModelConfigUpdate.tool_mode: str | None = None` |
| `app/api/chat.py` | `run_agent(..., tool_mode=request.tool_mode)` |
| `app/api/settings.py` | `merge_model_updates` 已透传新字段，无需额外改动（核对 `ModelConfigUpdate` 序列化） |
| `app/agent/context.py` | `AgentRunContext.tool_mode: str = "auto"` |
| `app/agent/orchestrator.py` | 解析生效 `tool_mode`（请求覆盖 > 模型条目 > auto）写入 ctx；`_stream_agent_run(..., react=...)` |
| `app/agent/tools.py` | `_build_agent` 在 `tool_mode=="react"` 时把 `ReActParseMiddleware` 置于 middleware 列表首位 |
| `app/agent/prompts.py` | `_build_dynamic_prompt` 在 react 模式追加 `REACT_FORMAT_PROMPT` |
| `app/agent/llm.py` | `_build_llm` 增加 `tool_mode` 参数用于日志/健康上报（模型构造本身不变） |

### 4.8 常量与限制（react.py）

| 常量 | 值 | 说明 |
| --- | --- | --- |
| `REACT_MAX_ACTION_INPUT_LEN` | 8192 字符 | Action Input 超长直接判解析失败，防注入超大 JSON |
| `REACT_MAX_THOUGHT_LEN` | 2000 字符/条 | Thought 截断，防单条推理无限膨胀 |
| 工具轮次 | 沿用 `MAX_TOOL_TURNS=64`、`recursion_limit=256` | ReAct 循环受同一上限约束，天然防死循环 |

## 5. 前端设计

### 5.1 设置：模型工具模式（ModelSection.tsx）

每个模型卡片新增一个下拉/单选："工具调用方式"：

- 选项：`自动`（auto）/ `原生函数调用`（native）/ `ReAct 文本模式`（react）。
- 提示文案：`ReAct 文本模式适用于不支持原生函数调用的模型或接口（如部分本地推理服务），以 Thought/Action 文本循环调用工具。`
- `types.ts` 的 `ModelConfig` 增加 `tool_mode?: "auto" | "native" | "react"`；保存时随 `models` 一并提交（`merge_model_updates` 已透传）。

### 5.2 SSE 与渲染

- **无新事件类型**：think / message / tool 均已存在。Thought 实时进 ThinkBlock，Action 脚手架被服务端抑制，工具卡片照常渲染。
- 历史恢复（`services/api.ts`）：无需改动——持久化结构与原生模式一致（tool_turn + think part + assistant 消息）。

### 5.3 国际化

三个 locale 增加：

| key | zh-CN | en |
| --- | --- | --- |
| `settings.toolMode` | 工具调用方式 | Tool calling mode |
| `settings.toolModeAuto` | 自动 | Auto |
| `settings.toolModeNative` | 原生函数调用 | Native function calling |
| `settings.toolModeReact` | ReAct 文本模式 | ReAct text mode |
| `settings.toolModeHint` | ReAct 文本模式适用于不支持原生函数调用的模型或接口（如部分本地推理服务），以 Thought/Action 文本循环调用工具 | ReAct text mode is for models/endpoints without native function calling (e.g. some local inference servers); it calls tools via a Thought/Action text loop |

## 6. 安全与稳定性

| 风险 | 对策 |
| --- | --- |
| 模型输出 Action Input 非法 JSON | 花括号配对提取 + 白名单校验失败回退 `{}`；`StructuredTool` 的 pydantic `args_schema` 二次校验，错误经 `ToolErrorMiddleware` 作为 Observation 喂回模型重试 |
| 模型杜撰/重复调用工具 | Action 名只在注册表内解析（`registry.list()`），未知名解析为工具错误返回；`ToolCallLimitMiddleware` + `MAX_TOOL_TURNS` + `recursion_limit=256` 封顶 |
| ReAct 死循环 | 模型调用轮次上限与递归上限沿用原生模式同一套 |
| 用户在 react 会话里看到脚手架文本闪现 | `ReActStreamProcessor` 在 SSE 层实时抑制；改写消息与流式展示由同一解析器驱动，语义一致 |
| 流式消息 id 与改写消息 id 不一致导致 think 丢失 | 改写时显式保留 `message.id`；`think_by_id` 以流式输出 id 为键，两者同源 |
| 审批绕过 | 无：工具执行仍走 `_handle_adapter_call` 的完整审批链（外部路径、终端策略、git、写日程、HITL write_todos），ReAct 只是换了一种"表达工具调用"的方式 |
| 会话中途切换 tool_mode | 线程消息结构两种模式一致（assistant tool_calls → tool），可混排回放；若出现异常，沿用现有"不完整 tool_calls 时重置线程"的保护 |
| Mock / 无 Key 模式 | `MockChatModel` 输出不含 Action，ReAct 中间件透传，退化为直接回答，功能可验收 |
| Action Input 超大 | `REACT_MAX_ACTION_INPUT_LEN=8192` 截断判失败 |

## 7. 验收标准

- 模型条目配置 `tool_mode: react` 后，发送"用 calculator 算 12*34，再读一下 notes/某文件"，Agent 以 Thought → Action → Observation 循环完成，正文不出现 `Action:` 脚手架文本，Thought 显示为 ThinkBlock，工具卡片照常渲染。
- 同一模型切回 `auto`/`native`，行为与当前版本完全一致（回归：原生工具调用、审批、计划照常）。
- 请求级 `tool_mode` 覆盖模型条目配置生效（如 `POST /api/stream_chat` 带 `tool_mode: "react"`）。
- `Final Answer:` 前缀不进入正文；刷新会话后历史中的 think、工具卡片、最终回答与实时展示一致。
- Action Input 写错 JSON 时：模型收到工具解析错误后能自行修正重试，或最终在回答中说明失败原因（不崩溃、不死循环）。
- 不支持的模型（如只输出正文）在 react 模式下正常回答，不报错。
- 无 Key 的 Mock 模式可完成端到端冒烟。
- `npx tsc --noEmit`、`pnpm build`、后端 pytest 全部通过；`tests/test_react.py` 覆盖：解析器（多行 Thought、同行/异行 Action、非法 JSON、Final Answer 截断）、中间件改写（id 保留、tool_calls 注入、透传）、配置白名单、流式处理器（token 分片）、Mock 冒烟。

## 8. 实施拆解

1. 后端：`config.py` 增加 `tool_mode` 字段与白名单校验；`schemas.py` 增加 `StreamChatRequest.tool_mode` 与 `ModelConfigUpdate.tool_mode`；`api/chat.py` 透传。
2. 后端：新增 `agent/react.py`——`REACT_FORMAT_PROMPT`、`ReActTrace`、`parse_react_trace`、`ReActStreamProcessor`、`ReActParseMiddleware`、常量。
3. 后端：`context.py` 增加 `tool_mode`；`orchestrator.py` 解析生效值并传给 `_build_agent` / `_stream_agent_run`。
4. 后端：`tools.py` `_build_agent` 在 react 模式把 `ReActParseMiddleware` 置于 middleware 首位；`prompts.py` 追加 `REACT_FORMAT_PROMPT`。
5. 后端：`sse.py` `_consume_message` / `_stream_agent_run` 增加 `react` 分支，接入 `ReActStreamProcessor`。
6. 后端：`api/settings.py` / health 上报 `tool_mode`。
7. 后端：`tests/test_react.py` 单元测试（见 §7）。
8. 前端：`types.ts` `ModelConfig.tool_mode`；`ModelSection.tsx` 增加"工具调用方式"选择器与提示。
9. 前端：三语言 i18n key。
10. 验证：构建、类型检查、后端单测、浏览器双主题手工验收、Mock 模式验收、非法 JSON / 超轮次 / 取消场景。

## 9. 演进建议

- **多 Action 并行**：允许一条消息输出多个 `Action:` 组，一次注入多个 `tool_calls`（tools 节点天然支持并行），进一步贴近原生调用体验。
- **原生失败自动降级**：`auto` 模式下首次请求收到"不支持 tools"类 400 时，自动重置线程并以 react 重试一次，并把该模型条目的 `tool_mode` 记录为 react（需谨慎处理线程重置与用户可见性，建议加开关）。
- **会话级切换**：在输入框（`ModelEffortControl` 附近）提供本次会话的 tool_mode 切换并随会话持久化（`db` 会话表加列或复用 settings），便于同一模型 A/B 对比。
- **Observation 可视化**：在工具卡片里折叠展示喂回模型的 Observation 原文，便于调试多步推理。
- **子 Agent 继承**：`run_subagents` 的子 Agent 复用主运行的 `tool_mode`（子 Agent 用只读工具集，ReAct 同样只读）。
