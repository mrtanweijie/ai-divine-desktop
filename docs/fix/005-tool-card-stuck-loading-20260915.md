# 005 · 工具卡 loading 图标不消失（2026-09-15）

> 编号：005 ｜ 类型：fix ｜ 日期：2026-09-15 ｜ 状态：**已修复**
> 现象：工具已执行完成、甚至已经进入下一轮对话，前一轮消息里的工具卡 `tool-icon` 区域仍显示 loading 图标

---

## 一、根因

工具卡的 loading 图标只由 `status` 决定（`ToolStatusCard.tsx:48`）：

```tsx
const running = tool.status === "running" || tool.status === "preparing";
...
{running ? <LoadingOrb state="solving" size={20} speed={3} /> : icon}
```

所以「图标不消失」= 本地 `tools` 数组里存在状态永远停在 `running` / `preparing` 的条目。

存在**两条**互不相关的路径都会造成这个结果：

### 路径 A：`done` 收尾时被本地陈旧状态盖住（主因）

`useChatStream.ts` 的 `done` 处理器会从服务端整段恢复会话，再与本地状态合并：

```ts
const restored = messagesToChatMessages(data.messages, data.tool_runs ?? [], data.todos);
setSessionMessages(sessionId, (prev) =>
  attachUnusedMentions(mergeLocalTools(prev, restored), unusedMentions),
);
```

而 `chatUtils.ts` 的 `mergeLocalTools` 此前**无条件优先本地**：

```ts
tools: local[index]?.tools?.length ? local[index].tools : message.tools,
```

关键在于：**服务端恢复出的状态只可能是 `done` / `error`，永远不会是 `running`**
（`services/api.ts:435`：`status: run.status === "done" ? "done" : "error"`）。

于是——本地 `tools` 是 SSE 事件逐条攒出来的，**任何一条 `done` 事件丢失**
（断流重连、事件竞态、标签页休眠、abort）都会让本地条目永久停在 `running`；
而收尾合并又把本地状态原样保留，服务端那份正确的 `done` 被丢弃。

这解释了一个很反直觉的现象：**刷新一下就好了**——因为刷新走的是服务端状态，不经过这个合并。

### 路径 B：用户主动「停止」时不结算在跑的工具

```ts
if (controller.signal.aborted) {
  // 主动点击停止：中止连接，不显示错误，只结束流式态
  setSessionMessages(sessionId, (prev) =>
    prev.map((item) =>
      item.id === assistantMessage.id
        ? { ...item, streaming: false, thinking: false }   // ← tools 完全没动
        : item,
    ),
  );
}
```

连接已 abort，在跑的工具收不到后续 `done` 事件，状态保持 `running` 直到刷新。

---

## 二、修复

原则：**让实时状态与「刷新后」的状态一致**。刷新后的状态是服务端权威结果，实时状态没有理由与之相悖。

### 2.1 `chatUtils.ts`

新增 `UNSETTLED_TOOL_STATUSES`（`preparing` / `running` / `confirm`）与 `settleInFlightTools`，
并把 `mergeLocalTools` 的整份替换改为**逐条收敛**：

```ts
tools: settleToolStatuses(local[index]?.tools, message.tools),
```

`settleToolStatuses` 的规则：

- **只在「本地未结算 + 服务端已结算」时收敛**——本地已结算的条目原样保留
  （它带着服务端 `tool_runs` 没有的富字段：`urls` / `commands` / `files` / `count`…）
- 匹配键用**工具名**，不是 `call_id`：两侧的 `call_id` 根本不是同一个标识
  （服务端是 `tool_run` 行 id，本地是 LLM 的 `tool_call_id`）
- 同名多次调用时**按出现顺序一一对齐**，已结算的本地条目也占掉一个服务端名额
- 服务端无同名条目 → 保守不动（不臆造状态）

### 2.2 `useChatStream.ts`

abort 分支补上 `tools: settleInFlightTools(item.tools)`，把仍在进行中的工具结算为 `error`——
与服务端刷新后的映射结果一致。无进行中条目时 `settleInFlightTools` 返回**同一引用**，不触发无谓重渲染。

---

## 三、验证

### 3.1 用真实模块跑逻辑验证

前端没有单测框架（`package.json` 无 test 脚本），因此搭了一个最小脚手架：
用 `tsc` 编译**真实**的 `chatUtils.ts`（复制到临时目录并校验 SHA-256 与被测文件**逐字节一致**），
把两个无关的服务依赖（`@/services/workspace`、`@/services/skillNames`）用桩替换，改写产物里的 `require` 后以 node 运行。

**16 项断言全部通过**：

| 用例 | 期望 |
| --- | --- |
| 本地 running + 服务端 done | 收敛为 done（**核心 bug 场景**） |
| 本地 running + 服务端 error | 收敛为 error |
| 收敛时保留本地富字段 | `urls` / `count` 不丢 |
| 本地已结算 | 不被服务端覆盖 |
| 同名多次调用 | 按序对齐（第二个取到 error） |
| 服务端无同名 | 保守不动 |
| 本地无 tools | 用服务端 |
| length 不匹配 | 直接返回服务端 |
| 服务端仍 unsettled | 不误改 |
| `settleInFlightTools` | running/preparing/confirm → error；已结算不动；无 unsettled 时返回同一引用 |

> **这套验证抓到了我第一版修复里的一个真实逻辑错误**：最初只让「未结算的本地条目」消费服务端状态，
> 于是 `本地 [done, running]` + `服务端 [done, error]` 场景下，未结算的那个错位拿到了 `done`。
> 改为「每条本地条目都占一个服务端名额」后通过。

### 3.2 静态检查

| 项 | 结果 |
| --- | --- |
| `tsc -b --force` | 0 错误 |
| `eslint`（改动文件） | 0 告警 |
| `prettier --check` | 通过 |

---

## 四、影响面

- **只改工具卡的状态收敛**，不改变任何工具的语义、不新增/删除卡片、不动服务端。
- 路径 A 的修复是**自愈式**的：无论 `done` 事件因何丢失，下一次 `done` 收尾都会把它收敛回来。
- 保留本地富字段这一点很重要——若图省事直接用服务端整份覆盖，工具卡的 `urls` / 文件列表会丢。

## 五、遗留

- 路径 B 把「用户主动停止」的在跑工具结算为 `error`，与刷新后一致；但严格说这是「已中断」而非「失败」。
  若要更精确的语义，需要给 `ToolEvent.status` 增加 `interrupted` 枚举并同步三语 i18n。
- 服务端 `tool_runs` 的 `call_id` 用的是行 id、与 SSE 事件的 `call_id` 不同源，导致两侧只能按工具名对齐。
  若日后统一标识，可以改成精确匹配（同名多次调用时更稳）。
