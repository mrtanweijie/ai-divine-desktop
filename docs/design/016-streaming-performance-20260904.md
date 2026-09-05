# 流式渲染性能优化方案

> 编号：016 ｜ 类型：design ｜ 日期：2026-09-04 ｜ 状态：未实施（B1–B6 待实施）
> 针对 Divine 桌面端「长回答 / 含代码块回答流式输出时客户端卡顿」的落地方案。


---

## 一、结论先行

外部流传的那份 SSE 优化文档（节流/防抖/服务端攒批/Nginx 关缓冲）讲的是**通用套路**，对本项目**命中率很低**：

- 文档主推的 4 项（虚拟滚动、memo、代理层关缓冲、EventSource 限制）里，前两项 Divine 早已做全，后两项**架构上根本不适用**。
- 文档真正的盲区：全程只谈「SSE 事件频率」，却没意识到**下游渲染链路里的 per-item setState** 才是放大器。本项目最大的卡顿源在 shiki 代码高亮的逐 token 更新上，比 SSE 频率严重一个数量级——**只做 SSE 攒批治不了它**。

实测代码后定位到 6 个瓶颈（B1~B6），其中 **B1 单独一项就贡献了大部分卡顿体感**。

---

## 二、现状盘点

### 2.1 Divine 已经做对的（不要再动）

| 项 | 位置 | 说明 |
|---|---|---|
| 虚拟滚动 | `divine-app/src/pages/chat/components/MessageList/index.tsx:52` | `@tanstack/react-virtual`，`overscan: 12`，`useFlushSync: false`（规避 commit 期 flushSync 报错） |
| 消息级 memo | `MessageItem/index.tsx:48` | `memo` 包裹，阻断历史消息重渲染 |
| Markdown 级 memo | `MarkdownView/index.tsx:103` | `memo` + `useMemo` 固化 `components`（避免 react-markdown 引用缓存失效）+ `useMemo` 缓存 `linkifyFilePaths` |
| 引用稳定性 | `MessageList/index.tsx:67` | 注释已点明「内联箭头函数会让 memo 失效」，并给 `onUserInteract` 加了 `useCallback` |
| 响应头 | `divine-server/app/api/chat.py` 各 `StreamingResponse` | 已带 `Cache-Control: no-cache` + `X-Accel-Buffering: no` |

这一层做得很扎实，说明之前的优化方向是对的。**问题不在「要不要 memo」，而在「memo 拦不住的那一层」。**

### 2.2 文档里不适用于本项目的部分

| 文档建议 | 为什么不适用 |
|---|---|
| Nginx `proxy_buffering off` / CDN / 边缘节点 | Tauri 桌面端直连本地 sidecar（8019），链路里**没有反向代理** |
| EventSource 1MB 事件上限、同源 6 连接限制 | `services/sse.ts` 用的是 `fetch` + `response.body.getReader()` 手动解析，不走 `EventSource` |
| 换 WebSocket | 单向流 SSE 已足够；本地回环延迟极低，换 WS 只增加复杂度 |
| 背压机制（客户端慢时阻塞服务端） | 客户端「消费慢」的根因是**渲染重**，不是网络慢。加背压不对症，是治标 |
| HTTP/2 多路复用 | 单会话单流，本地场景无并发连接瓶颈 |

### 2.3 文档自身的错误（引用时需注明）

1. `useRef` 示例末尾调用 `flushRef.current.flush?.()`，但其上方给出的 `throttle` 实现**根本没有返回 `flush` 方法** → 照抄会静默失效，最后几个字丢失。
2. `stream_with_backpressure` 代码片段是 JS 函数签名 + Python `asyncio.Queue` 的混写伪代码，**不可运行**。
3. 核心盲区：只谈 SSE 事件频率，未覆盖下游渲染链路的 per-item setState（见 B1）。

---

## 三、瓶颈清单

按严重度排序，全部已核实到文件与行号。

### B1（P0，最严重）shiki 逐 token setState → O(n²)

**位置**：`divine-app/src/pages/chat/components/MarkdownView/HighlightedCode.tsx:116-124`

```ts
const applyToken = (token: ThemedToken | RecallToken) => {
  if ("recall" in token) {
    if (token.recall > 0) setTokens((prev) => prev.slice(0, -token.recall));
    return;
  }
  setTokens((prev) => [...prev, token]);   // ← 每个 token 一次 setState
};
```

**为什么这是最严重的**：

- `CodeToTokenTransformStream` 的 sink 是**每个语法 token 回调一次**。一个 200 行的代码块轻松产生 2000+ 个 token。
- 这些回调经 `ReadableStream` 管道**异步**到达。React 18/19 的 automatic batching **只覆盖 React 事件处理器与同一同步执行块**，对异步微任务/宏任务中的 setState **不合并** → 2000+ 次独立渲染。
- 每次 `[...prev, token]` 是 **O(n) 数组拷贝** → 累计 **O(n²)**。
- 渲染产物是 2000+ 个 `<span>`，每次 setState 都要重建整棵 span 列表。

**数量级对比**：SSE 层面是 80 次/秒；这里是 **2000+ 次/代码块**。差一个数量级以上。

---

### B2（P0）每 SSE chunk 一次全量重解析 → O(n²)

**位置**：`divine-app/src/pages/chat/hooks/useChatStream.ts:100-135`（`think` / `message` handler）

```ts
message: ({ content }) => {
  setSessionMessages(sessionId, (prev) =>
    prev.map((message) =>
      message.id === assistantId
        ? { ...message, content: message.content + content }
        : message
    )
  );
},
```

每个 chunk 触发：

1. `prev.map()` **重建整个消息数组**（新数组 + 新对象引用）。
2. 正在流式的那条消息 `content` 变化 → `MarkdownView` 的 `useMemo(() => linkifyFilePaths(content), [content])` **必然失效**。
3. `linkifyFilePaths` 对全文跑 **3 遍正则**（掩码 → linkify → 还原），其中 `ABS_PATH_RE`（`MarkdownView/index.tsx:48-49`）是条非常复杂的正则。
4. `react-markdown` **全量重新解析**整篇 Markdown → 重建整棵组件树。
5. 若含代码块，还会叠加 B1。

长回答（如 5000 字）到达后半程时，每个 chunk 都要重解析 5000 字 → 累计 O(n²)。`memo` 在这个层级**拦不住**，因为 content 确实变了。

---

### B3（P1）tool 事件单次触发两次 setState

**位置**：`useChatStream.ts:169-199`

`tool` handler 里连做两次 `setSessionMessages`：

- `:172-178` 清 `preprocess_pending`
- `:192-198` `upsertTool`

两次都会走一遍 `prev.map()` 全量重建。工具事件虽不如文本 chunk 密集，但在工具密集调用时会成倍放大。

---

### B4（P2）依赖 `[messages]` 的 effect 里做整数组拷贝

**位置**：`MessageList/index.tsx:139-141`

```ts
const lastUser = [...messages].reverse().find(
  (message) => message.role === "user"
);
```

该 effect 依赖 `[messages, streaming, sessionId]`，**每个流式 chunk 都会重跑** → 每 chunk 一次「拷贝整个数组 + 反向遍历」。会话越长开销越大，且与 B2 叠加。

---

### B5（P3）`done` 收尾串行 await 4 个请求 → 结束瞬间卡顿尖峰

**位置**：`useChatStream.ts:232-266`

```ts
const data = await getSession(sessionId);       // 必要
// ...
await Promise.all([refreshSessions, refreshProjects, refreshWorkspace]);
// ...
await loadChangedFiles(sessionId);
```

`getSession` 是正确性必需的（从服务端恢复权威消息），但后面 3 个刷新属于侧边栏/工作区元数据，同步阻塞会造成**流结束瞬间的明显顿挫**。

---

### B6（P3）服务端零攒批：1 delta = 1 SSE 事件

**位置**：`divine-server/app/agent/core/sse.py:257-323`

```python
async for delta in message.text:
    for event in think_processor.push(delta):
        await queue.put(("sse", sse_event("message", {"content": event["content"]})))
```

每个 LLM delta 立刻序列化成一个完整 SSE 帧。客户端侧 `consumeSSE`（`services/sse.ts:49-80`）也是解析一帧派发一帧，**两端都没有缓冲**。

本地传输下网络本身不是瓶颈，但它是 B1/B2 的**放大器**：事件越密，下游 O(n²) 触发次数越多。

---

## 四、修复方案

### 4.1 B1 — shiki token 攒批（收益最大，优先做）

**思路**：异步 sink 只往 ref 数组里 push，用 `requestAnimationFrame` 按帧提交，一帧内所有 token 合并成**一次** `setState`。

**改动点**：`HighlightedCode.tsx:116-124` 及相关 effect。

```tsx
const pendingRef = useRef<Array<ThemedToken | RecallToken>>([]);
const rafRef = useRef<number | null>(null);

const scheduleFlush = useCallback(() => {
  if (rafRef.current !== null) return;
  rafRef.current = requestAnimationFrame(() => {
    rafRef.current = null;
    const batch = pendingRef.current;
    if (!batch.length) return;
    pendingRef.current = [];
    setTokens((prev) => {
      const next = prev.slice();          // 每帧一次 O(n)，而非每 token 一次
      for (const token of batch) {
        if ("recall" in token) {
          if (token.recall > 0) next.splice(-token.recall, token.recall);
        } else {
          next.push(token);
        }
      }
      return next;
    });
  });
}, []);

const applyToken = (token: ThemedToken | RecallToken) => {
  pendingRef.current.push(token);
  scheduleFlush();
};
```

**必须处理的三个边界**：

1. **顺序性**：`recall` 与 push 的相对顺序必须保持，攒批内按数组顺序处理即可满足。
2. **卸载/流结束兜底**：effect cleanup 与 `streaming` 由 `true → false` 的切换点必须调用一次同步 flush，否则最后几个 token 会丢失（这正是外部文档示例里 `flush` 没实现的那个坑）。
3. **cancel 时清空**：`handle.cancel()` 时丢弃 `pendingRef`，避免已取消流的残留 token 混入。

**预期效果**：单个代码块的 setState 次数从 2000+ 降到约等于「代码块流式持续的帧数」（200 行代码块约 1~2 秒 → 60~120 次），数组拷贝从 O(n²) 降到 O(n × 帧数)。

---

### 4.2 B2 — SSE 事件缓冲 + 单次提交

**思路**：`think` / `message` handler 只累加到 ref 缓冲区，rAF 到点时**合并成一次** `setSessionMessages`。

**改动点**：`useChatStream.ts` 的 `buildStreamHandlers`。建议抽一个独立小模块（如 `pages/chat/hooks/streamBuffer.ts`），保持 `useChatStream` 可读性。

```ts
interface PendingText { think: string; content: string }

export function createStreamBuffer(
  commit: (pending: PendingText) => void
) {
  let pending: PendingText = { think: "", content: "" };
  let raf: number | null = null;

  const flushNow = () => {
    raf = null;
    if (!pending.think && !pending.content) return;
    const batch = pending;
    pending = { think: "", content: "" };
    commit(batch);
  };

  const schedule = () => {
    if (raf === null) raf = requestAnimationFrame(flushNow);
  };

  return {
    pushThink(text: string) { pending.think += text; schedule(); },
    pushContent(text: string) { pending.content += text; schedule(); },
    flush() { if (raf !== null) cancelAnimationFrame(raf); flushNow(); },
    dispose() {
      if (raf !== null) cancelAnimationFrame(raf);
      raf = null;
      pending = { think: "", content: "" };
    },
  };
}
```

handler 侧改为：

```ts
message: ({ content }) => buffer.pushContent(content),
think:   ({ content }) => buffer.pushThink(content),
```

`commit` 里做**一次** `setSessionMessages`，同时应用 think 与 content 的增量。

**关键风险控制**：

| 风险 | 处理 |
|---|---|
| `done` handler 会用服务端数据覆盖消息，若缓冲区未 flush 会丢字 | `done` 与 `error` handler **第一行**先调 `buffer.flush()`，再走 `getSession` |
| 用户点停止 / 组件卸载 | `finally` 块与清理逻辑中调 `buffer.dispose()` |
| 会话切换导致 `assistantId` 变化 | buffer 生命周期与单次 `buildStreamHandlers(sessionId, assistantId)` 绑定，随流创建/销毁 |

**预期效果**：渲染次数从 80 次/秒降到 ≤60 次/秒（帧对齐），且每帧只做一次 Markdown 全量解析，砍掉重复计算。

> 注意：这一项**不能消除**「每帧一次全量 Markdown 解析」。若长回答仍卡，下一步应做「已闭合块冻结」——只重新解析最后一个未闭合的 Markdown 块，前面稳定段落走缓存。那是更大的改造，建议 B1/B2 上线测效后再评估。

---

### 4.3 B3 — 合并 tool 的两次 setState

**改动点**：`useChatStream.ts:169-199`

把 `preprocess_pending` 的清除与 `upsertTool` 合并进**同一次** `prev.map()`；文件变更收集改为纯计算、不触发状态更新，最后单独调一次 `setAgentChangedFiles`。

```ts
tool: (data: unknown) => {
  const event = data as unknown as ToolEvent;
  const added: string[] = [];
  if (event.status === "done" && event.result) {
    const projectPath = projects.find((i) => i.id === selectedProjectId)?.path;
    if (projectPath) {
      for (const filePath of changedFilePathsFromResult(event.result)) {
        const rel = changedFileRel(projectPath, filePath);
        if (rel && workspacePanelOpenRef.current) added.push(rel);
      }
    }
  }
  setSessionMessages(sessionId, (prev) =>
    prev.map((message) =>
      message.id === assistantId
        ? {
            ...message,
            preprocess_pending: false,
            tools: upsertTool(message.tools, event),
          }
        : message
    )
  );
  if (added.length) {
    setAgentChangedFiles((prev) => {
      const next = new Set(prev);
      for (const rel of added) next.add(rel);
      return next;
    });
  }
},
```

---

### 4.4 B4 — 去掉整数组拷贝

**改动点**：`MessageList/index.tsx:139-141`

```ts
let lastUser: ChatMessage | undefined;
for (let i = messages.length - 1; i >= 0; i -= 1) {
  if (messages[i].role === "user") { lastUser = messages[i]; break; }
}
```

> 说明：`Array.prototype.findLast` 语义更简洁，但为稳妥起见（避免依赖 WebView 版本）建议用上面的显式倒序循环，零依赖、零分配。

---

### 4.5 B5 — `done` 收尾错峰

**改动点**：`useChatStream.ts:232-266`

- `getSession` 保持 `await`（正确性依赖它，必须优先完成）。
- `refreshSessions` / `refreshProjects` / `refreshWorkspace` / `loadChangedFiles` 改为**不阻塞主链路**：用 `setTimeout(..., 0)` 或 `requestIdleCallback` 错峰触发，让流结束的视觉收尾先落地。

---

### 4.6 B6 — 服务端 delta 攒批（优先级最低）

**改动点**：`divine-server/app/agent/core/sse.py:257-323` 的 `drain_text`

**思路**：不要序列化后再合并（那样要反复 parse/merge/serialize），应在**入队前**按类型缓冲。

```python
# 伪代码：累积同类型事件，按 50ms 或 N 字符 flush
pending_type: str | None = None
pending_parts: list[str] = []

async def flush_pending():
    nonlocal pending_type, pending_parts
    if pending_type and pending_parts:
        await queue.put(("sse", sse_event(pending_type, {"content": "".join(pending_parts)})))
    pending_type, pending_parts = None, []
```

**必须注意**：`ThinkTagProcessor.push(delta)` 会在 `<think>` 边界处**切换事件类型**，攒批时必须**在类型切换点立即 flush 前一段**，否则思考内容与正文会被错误合并。

**建议**：这是最后一步，且应等 B1/B2 上线测效后再决定——客户端攒批已经把渲染次数压到 60Hz，服务端再攒批的边际收益有限，主要价值是减少本地 IPC 帧数。

---

## 五、实施顺序

| 步骤 | 内容 | 预估工作量 | 风险 |
|---|---|---|---|
| 1 | **B1** shiki token 攒批 | 小（单文件） | 低，注意三个边界（顺序/flush/cancel） |
| 2 | **B2** SSE 事件缓冲 | 中（新抽 1 个小模块 + 改 handler） | 中，需处理 done/error/abort 三处 flush 时机 |
| 3 | **B3 + B4** | 小（各一个函数） | 极低 |
| 4 | **B5** 收尾错峰 | 小 | 低 |
| 5 | **B6** 服务端攒批 | 中 | 中，think/message 类型切换点是坑 |

**建议**：1+2 一起做完先测效，再决定 3/4/5。

---

## 六、怎么验证有效

### 6.1 埋点计数（最直接）

改码前后各跑一次**同一条含长代码块的提问**（如「用 TypeScript 写一个 200 行的 LRU 缓存」），在两处加临时计数：

```ts
// HighlightedCode.tsx applyToken 内
(window as any).__shikiSetState = ((window as any).__shikiSetState ?? 0) + 1;

// useChatStream.ts message handler 内
(window as any).__sseCommit = ((window as any).__sseCommit ?? 0) + 1;
```

控制台读这两个值对比。预期：`__shikiSetState` 从 2000+ 降到 100 量级，`__sseCommit` 从 每分钟回答 1000+ 降到 60×秒数。

### 6.2 Performance 面板

录制一次完整长回答，看 **Main thread 的长任务（>50ms）数量**与 **Scripting 占比**。改前通常会有密集的连续长任务，改后应显著稀疏。

### 6.3 体感校验

- 流式输出过程中，输入框打字是否还有延迟。
- 回答结束后，最后几个字/最后几行代码是否完整（验证 flush 兜底是否写对）。

---

## 七、验证清单（改完必须过）

- [ ] 长回答（纯文本）流式过程无掉帧
- [ ] 长回答（含多个代码块）流式过程无掉帧
- [ ] 流式结束后内容完整，无丢字、无丢代码尾部
- [ ] 流式中点「停止」，残留 token 不混入、状态干净
- [ ] 流式中切换会话，两个会话状态互不污染
- [ ] 推理模型的 `<think>` 思考块与正文分离正确（验证 B6 若实施）
- [ ] `tsc -b` 与 `vite build` 均通过（本项目前端无测试，靠类型与构建兜底）

---

## 八、附：为什么不做这几件事

| 不做 | 理由 |
|---|---|
| 换 WebSocket | 单向流，本地延迟极低，纯增复杂度 |
| 引入 `useDeferredValue` / `startTransition` | 本项目流式内容本身就是最高优先级更新，降级它没有意义；且 rAF 攒批已解决频率问题 |
| Web Worker 跑 Markdown 解析 | 收益不如先消除 O(n²)；且 react-markdown 依赖 DOM 组件树，搬进 Worker 需换渲染方案，改造量极大 |
| 服务端背压 | 客户端慢的根因是渲染重，不是网络慢；先修渲染 |
| 限制最大行数截断头部 | 本项目已有分页加载历史（`hasMoreOlder` / `onLoadOlder`）与虚拟滚动，不需要粗暴截断 |
