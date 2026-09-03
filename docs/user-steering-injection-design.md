# 用户插话（Steering）设计文档 —— 执行中主动补充信息

> 状态：已评审定稿，**已实施（2026-09-03，未提交，待审查）**。与 `ask-user-feature-design.md`（agent 主动问）互补，本文档描述**用户主动插**的通道。实施记录见 §11。

## 1. 需求与定位

LLM 在执行长任务（多轮工具调用）的过程中，用户看到中间产出后**主动发送补充信息**；该信息进入模型上下文，agent 在**下一个模型调用节点**将其纳入，继续（或修正方向）执行任务。

与 ask_user 的关系：ask_user 是 agent 暂停等输入（拉）；steering 是用户不等提问直接插话（推）。两者共用"信息在任务中途进入上下文"的语义，但触发方向、通道、UI 完全独立，不互相依赖。

## 2. 现状（已核实的代码事实）

| 位置 | 现状 |
|---|---|
| `pages/chat/index.tsx:999` | `ChatInput disabled={streaming}` —— 流式执行中输入框整体禁用，唯一出口是"停止" |
| `app/api/chat.py:22,348` | 每个 session 仅有一张 `_CANCEL_EVENTS` 取消事件表，`generate()` finally 中 pop（即它的存在性 = "该 session 有活跃流"） |
| `app/agent/core/sse.py:326` | `_stream_agent_run` 用 `astream_events` 把整张图跑到底，中途唯一暂停点是 interrupt；**没有"每个模型调用前"的外层钩子** |
| 硬发第二条 `/stream_chat` | 会在同一 checkpointer thread 上并发跑两个 graph，无任何保护 |

物理边界：正在生成的 token 永远看不到新信息。任何方案的生效点是**下一个模型调用**，这是流式生成的固有限制。

## 3. 方案选型

考虑过三条路径：

1. **打断重启（cancel + resume）**：中途 abort graph run，再以新消息重启 astream。❌ 否决——abort 时线程状态可能停在"AIMessage 带 tool_calls 但 ToolMessage 未返回"的悬空点，重启后历史含悬空工具调用，依赖 thread repair 兜底，风险大。
2. **仅在运行结束后续跑**：流结束时检查队列，非空则同一 SSE 连接里再跑一轮。❌ 单独用不够——"执行中插话"退化为"结束后追话"。
3. **✅ middleware 注入（选定）**：项目已有自定义 `AgentMiddleware` 先例（TodoSyncMiddleware 持有 `ctx.session_id`）。langchain 1.3.15 的 `AgentMiddleware.abefore_model` 可返回 state 更新字典，**在每次模型调用前应用**。注入队列是进程内 dict（与 `_CANCEL_EVENTS` 同模式），中间件在 `abefore_model` 里 drain 并以 `HumanMessage` 追加进 state——**不打断图、不改 resume 协议、orchestrator 零改动**。

## 4. 接口契约

### 4.1 后端队列 `app/agent/core/injection.py`（新增）

```python
MAX_PENDING_INJECTIONS = 5        # 每 session 未消费插话上限
MAX_CONTENT_LENGTH = 4000         # 单条插话长度上限（字符）

_INJECT_QUEUES: dict[str, list[str]] = {}

def enqueue_injection(session_id: str, content: str) -> bool  # 队满返回 False
def drain_injections(session_id: str) -> list[str]            # 取走全部（清空）
def pending_count(session_id: str) -> int
def discard_injections(session_id: str) -> None               # 清空（运行收尾兜底用）
```

### 4.2 端点 `POST /api/sessions/{session_id}/inject`（chat.py，与 cancel 同组）

请求：`{"content": "..."}`

响应语义：
- `{"ok": true}` —— 已落库 + 入队，等当前 agent run 消费
- HTTP 409 `{"detail": "no_active_stream"}` —— 无活跃流，前端**降级走常规发送**（此时插话语义上就是新的一轮消息）
- HTTP 404 —— 会话不存在；HTTP 400 —— 内容为空/超长；HTTP 429 —— 队列满

副作用顺序：校验 → `db.add_message(session_id, "user", "[用户补充] {content}")` 落库 → 入队 → `db.touch_session`。

**落库先于入队**：即使队列条目最终没被 agent 消费（见 §6 时序），消息也不会丢——它已在 DB 里，下一轮 `history_for_model` 自然带上。

### 4.3 注入消息格式

```
[用户补充] {content}
```

标记同时服务两端：模型侧（识别这是执行中的方向性补充）与前端侧（历史重建时识别出"补充"气泡样式）。**前缀约定为单一事实来源，前后端共用同一常量语义，不引入新字段。**

## 5. 中间件 `UserInjectionMiddleware`（新增，注册进 tools.py 的 middleware 列表）

```python
class UserInjectionMiddleware(AgentMiddleware):
    """把用户执行中的插话注入下一次模型调用的 state。"""
    def __init__(self, ctx: AgentRunContext) -> None: ...

    async def abefore_model(self, state, runtime):
        items = drain_injections(self.ctx.session_id)
        if not items:
            return None
        return {"messages": [HumanMessage(content=item) for item in items]}
```

- 实现异步钩子 `abefore_model`（与 TodoSync 实现 `awrap_tool_call` 同风格，避免依赖基类同步/异步委托行为）。
- state 的 `messages` 走 langgraph 标准 append reducer，返回即追加。
- react 模式与默认模式共用同一个 create_agent 构建函数（tools.py），一处注册两模式生效。
- **不做** SSE 播报：前端靠乐观渲染呈现气泡（§7），DB 落库保证 `done` 后刷新一致。

## 6. 时序与边界情况

```
插话到达（POST /inject）
  ├─ 无活跃流（409）→ 前端降级常规发送 → 成为正常新一轮
  └─ 有活跃流 → 落库 + 入队
       ├─ agent run 在后续任一 before_model 消费 → 注入本 run 上下文 ✅ 主路径
       ├─ run 在消费前结束/被取消（含本地模型路径、preprocess 路径——
       │   这些路径没有 agent 中间件）→ generate() finally 中
       │   discard_injections 兜底清队，消息留在 DB，
       │   下一轮 history_for_model 自然携带，**不会跨 run 泄漏、不会重复注入**
       └─ 180s 审批等待期间插入 → 审批优先（单槽位不变）；
           批准后下一个 before_model 消费；拒绝/超时则走兜底
```

关键保证：**drain 即消费即删除**，同一条插话最多注入一次；generate() 收尾统一 discard，消除跨 run 残留。

## 7. 前端

1. **`services/api.ts`**：`injectSupplement(sessionId, content)` → POST inject；409/异常由调用方捕获降级。
2. **`useChatStream`**：新增 `sendSupplement(sessionId, content)`：
   - 乐观追加用户气泡（content 带 `[用户补充] ` 前缀，与后端落库格式一致）；
   - 调 inject 失败（含 409）→ 降级调 `sendMessage(content, [])` 走常规流。
3. **`ChatInput`**：拆分 `disabled`（硬禁用：无项目）与新增 `streaming` 属性 + `onSupplement` 回调：
   - 流式执行中输入框保持可用；Enter/发送按钮 → `onSupplement(text)`（纯文本，附件入口在流式期间禁用）；
   - 流式期间同时显示"停止"按钮与"发送"按钮（有内容时）；
   - 模型/深度控制件在流式期间维持禁用。
4. **`MessageItem`**：用户消息 content 以 `[用户补充] ` 开头时，渲染"补充"小徽标并展示去前缀正文。

## 8. 系统提示词

注入消息自带 `[用户补充]` 标记，配合 agent 系统提示追加一句（prompts.py）：

> 执行任务过程中收到 `[用户补充]` 开头的消息时，将其视为用户对当前任务的方向性补充：结合已有进度继续执行，必要时调整 todo 计划；不要当作全新任务重新开始，也不要重复确认已明确的内容。

## 9. 不做的事（V1 边界）

- 附件插话：流式期间附件入口禁用，V1 仅文本。
- 插话的 SSE 实时播报：乐观渲染 + done 后刷新已覆盖单窗口场景；多窗口实时同步不做。
- 本地模型（llama-server 直答）路径的执行中注入：本地路径无 agent/中间件，插话走兜底（下一轮生效）。
- ask_user 与插话的队列互通：两个独立通道，不做合并。

## 10. 测试

- `tests/test_user_injection.py`（新增）：
  - 队列：enqueue/drain/discard、队满、独立 session 隔离；
  - 中间件：drain 后返回 `{"messages": [...]}`、空队返回 None、消费即删除；
  - 端点：无活跃流 409、正常入队且 DB 落库带标记前缀、超长 400。
- 前端：`tsc -b` + `vite build`（前端无测试基建）。

---

## 11. 实施完成记录（2026-09-03）

按定稿方案全部落地，改动留在工作区**未提交**，供审查后由用户决定提交。

**后端（新增 3 文件 + 改动 5 文件）**
- `app/agent/core/injection.py`（新增）：进程内队列（同 `_CANCEL_EVENTS` 模式），`MAX_PENDING_INJECTIONS=5`、`MAX_CONTENT_LENGTH=4000`、`SUPPLEMENT_PREFIX="[用户补充]"`。
- `app/agent/middleware/injection.py`（新增）：`UserInjectionMiddleware.abefore_model` drain 队列 → 返回 `{"messages": [HumanMessage...]}`，在每次模型调用前注入；空队返回 None 不干预。TodoSync 模式（持 ctx.session_id）。
- `app/agent/middleware/__init__.py` / `tools.py`：注册 `UserInjectionMiddleware(ctx)`（排在 TodoSync 之后）。
- `app/api/chat.py`：新增 `POST /sessions/{id}/inject`（校验内容/会话/活跃流/队满 → DB 落库带前缀 + 入队）；`stream_chat`/`retry_cloud` 的 `generate()` 启动清残留 + finally 丢弃未消费插话（消息已在 DB，下一轮 history 自然携带，不跨 run 泄漏）。
- `app/schemas.py`：`InjectRequest { content }`。
- `app/agent/core/prompt_sections.py`：`_GENERAL_RULES` 末尾追加"收到 `[用户补充]` 视为方向性补充，继续执行、必要时调整 todo、不重开任务"。
- `tests/test_user_injection.py`（新增 9 用例）：队列/中间件/端点三组，全通过。

**前端（7 文件）**
- `services/api.ts`：`injectSupplement`。
- `pages/chat/chatUtils.ts`：共享 `SUPPLEMENT_PREFIX` + `parseSupplement`。
- `pages/chat/hooks/useChatStream.ts`：`sendSupplement`（乐观气泡带前缀 → inject；失败降级 `sendMessage`）。
- `pages/chat/components/ChatInput/index.tsx`：新增 `streaming` / `onSupplement` props；流式中发送走补充通道（纯文本），附件入口流式期间禁用，停止/发送按钮并存。
- `pages/chat/components/MessageItem/index.tsx` + `index.less`：`[用户补充]` 前缀消息渲染"补充"徽标 + 去前缀正文。
- `pages/chat/index.tsx`：`ChatInput disabled` 改仅绑定无项目；传 `streaming` + `onSupplement={handleSupplement}`（409/失败降级常规发送）。

**验证结果**
- 后端：`tests/test_user_injection.py` 9/9 通过；全量 `pytest tests/` 698 通过 / 1 失败（`test_local_task_routing.py::test_rewrite_routed`，已 stash 验证为**预存失败**，与本改动无关）。
- 前端：`tsc -b` 通过；`vite build` 通过（665ms）。
- 沙箱环境备注：pytest 的 `tmp_path`/`--basetemp` 会被拦截且 pytest+TestClient 组合被 SIGTERM，端点测试改为直接调用 endpoint 函数 + tempfile 目录 fixture。
