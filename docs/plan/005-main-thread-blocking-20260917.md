# 主线程阻塞点隔离方案（全栈）

> 编号：005 ｜ 类型：plan ｜ 日期：2026-09-17 ｜ 状态：已实施（2026-09-19）
> 版本：v1.0（实施记录见 [§十](#十实施记录2026-09-19)）
> 性质：方案（未实施代码）；每项含现状证据、改动设计、风险、验证方式
> 前序：[review/009-app-freeze-diagnosis-20260915](../review/009-app-freeze-diagnosis-20260915.md)
> 上一轮已修复「文件树刷新路径」；本方案处理**剩余**未隔离的阻塞点
> 建议实施顺序：**B1 → B2 → B3 → A1 → A2/A3 → B4 → C1 → B5 → C2/C3**
> （先补一行改动的漏网点，再动需要并发审查的部分，最后做前端与低优先项）

---

## 一、范围与判定基线

本方案的目标不是「消除所有慢操作」，而是**消除会阻塞事件循环/主线程的同步慢操作**。
慢但已卸载到线程池/子进程的操作不在范围内（见 §七）。

三层「主线程」的判定基线如下，后续所有结论都据此推导：

| 层 | 判定规则 | 依据 |
| --- | --- | --- |
| **Tauri 主线程** | `#[tauri::command]` 的**同步 `pub fn` 跑在主线程**；只有 `async fn` 才被卸载到 `async_runtime`。全仓**零**处 `#[tauri::command(async)]` | Tauri 2 语义；`commands/workspace.rs:314` 的项目注释（「同步命令在**主线程**执行，会让整个应用转彩虹圈」） |
| **sidecar 事件循环** | `app/api/*.py` **全部是 `async def`**（26 处，0 处同步 `def`），路由里任何同步阻塞都是事件循环级冻结 | 实测统计 |
| **WebView JS 主线程** | 无 Web Worker（`grep "new Worker"` 零命中），前端一切计算都在 JS 主线程 | 实测统计 |

**关键推论**：因为 `app/api/*.py` 没有同步 `def`，FastAPI 不会把任何路由自动放进 Starlette 线程池。
每一个在 async 路由里裸调的同步函数，都直接阻塞事件循环。

### 为什么这件事值得单独做一份方案

`app/sse.py` 与 `app/agent/core/sse.py` **都没有心跳事件**（全仓 `grep heartbeat|keepalive|ping` 零命中），
而 `chat.py` 有 8 处 `StreamingResponse`。这意味着事件循环一旦被占住：

- 所有进行中的 SSE 流会**静默卡死**——不输出、不报错、不超时；
- 前端表现为「模型没响应」，用户与开发者都会去查模型侧，而真正的原因在后端事件循环。

这是一个**高误诊成本**的故障形态，因此值得系统性清理，而不是等它复现再逐个排查。

---

## 二、上一轮已修复（不重复处理）

`review/009` 已解决「代码任务期间应用整体冻结」，本方案与其**无重叠**，列出以便划清边界：

| 已修复项 | 做法 |
| --- | --- |
| 逐条目 `git check-ignore` 子进程 | 改 `--stdin` 批量入口，实测 23.2× |
| 5 个重 I/O 命令占主线程 | `get_file_tree` / `get_dir_children` / `get_file_diff` / `get_binary_preview` / `get_external_file_preview` 改 `pub async fn` + `spawn_blocking` |
| `workspace:changed` 无防抖 | `FileTree.tsx:19` 加 200ms 合并窗口 |
| `document_reader` 顶层 langchain 导入 | 改延迟导入，`read_file.py` 启动 3.518s → 0.044s |

`review/009 §4.5` 的遗留项（`scan_dir` 每目录一次 `rev-parse`）**仍有效**，但属「再压性能」而非「阻塞主线程」，不在本方案范围。

---

## 三、本轮新增发现（9 处未隔离阻塞点）

严重度按「触发频率 × 单次阻塞时长 × 影响面」综合排序。影响面分三档：
**全后端停摆**（事件循环）> **窗口无响应**（Tauri 主线程）> **界面掉帧**（JS 主线程）。

### 汇总表

| # | 位置 | 阻塞内容 | 最长阻塞 | 影响面 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| B1 | `api/chat.py:559` | `_start_local_model` 同步调用（内含 40s 轮询） | **~50s** | 全后端停摆 | **P0** |
| B2 | `agent/tools/execution.py:1034` | `py_compile` 子进程（`timeout=20`） | **20s** | 全后端停摆 | **P0** |
| B3 | `api/local_llm.py` 7 处 | `get_status()` / `detect_hardware()` / `stop()` | **~20s** | 全后端停摆 | **P0** |
| A1 | `commands/system.rs:110,143` | `osascript` 阻塞等 JXA（遍历全部日历事件） | **秒级~数十秒** | 窗口无响应 | **P0** |
| A2 | `commands/paste.rs:30,69,112` | 最多 100MB base64 解码 + 哈希 + 落盘 | **1~2s** | 窗口无响应 | P1 |
| A3 | `commands/workspace.rs:566` | 20MB base64 解码 + 哈希 + 落盘 | ~0.5s | 窗口无响应 | P1 |
| B4 | `api/chat.py:401` | `read_file_text` 附件解析（PDF/Word/Excel） | 0.2s~数十秒 | 全后端停摆 | P1 |
| C1 | `services/api.ts:379` | 会话重建 O(N×M) + 内层 `JSON.parse` | 数百 ms~秒 | 界面冻结 | P1 |
| B5 | `api/chat.py` 6 处 / `api/sessions.py` 3 处 | 同步 SQLite（`timeout=10.0`） | 最坏 10s | 全后端停摆 | P2 |
| C2 | `MarkdownView` / `ChoiceBlock` | 流式每帧全文正则 / O(n²) 引号扫描 | 每帧数十 ms | 掉帧 | P2 |
| C3 | `HighlightedCode.tsx:203` | 同步 `codeToTokens`（2000+ 行） | 200~800ms | 界面冻结 | P2 |

> C2/C3 与 B5 之外还有若干 P3 次级项，见 §六。

---

## 四、方案设计

### B1 · `api/chat.py:559` — 一行漏网（收益/成本比最高）

**现状证据**（`api/chat.py:553-560`）：

```python
if task:
    manager = get_manager()
    if not await asyncio.to_thread(manager.is_ready):   # ← 558 已隔离
        _start_local_model(manager)                     # ← 559 漏了
    if await asyncio.to_thread(manager.is_ready):       # ← 560 已隔离
```

上下两行都包了 `to_thread`，唯独中间这行没有。`_start_local_model`
（`agent/middleware/preprocess.py:251-310`）内部是：

1. `manager.get_status()` → 含 `detect_hardware()` 的多个 `subprocess.run`（各 `timeout=5`）；
2. `manager.start(model_id, path, wait_s=10.0)` → 内部 `time.sleep(0.2)` 忙等最多 10s；
3. 再叠一个 **40s** 的 `while time.time() < deadline: ... time.sleep(2)` 轮询。

最坏路径 ≈ 10s + 40s = **50s** 事件循环冻结。

**改动**：

```python
if not await asyncio.to_thread(manager.is_ready):
    await asyncio.to_thread(_start_local_model, manager)
```

**顺带收口**：`_start_local_model` 的 40s 轮询上限偏大（`start` 已经等了 10s）。
建议降到 20s，并在 `manager.process is None`（启动快速失败）时立刻返回——该分支**已经存在**
（`preprocess.py:302-304`），只是上限仍留 40s。

**风险**：低，但有一个必须处理的点——见 §五「并发语义变化」。

---

### B2 · `agent/tools/execution.py:1034` — 高频路径

**现状证据**：在 `async def _handle_adapter_call`（`:189`，由 `agent/tools/tools.py:96/100` `await` 进入）里：

```python
if name in _EDIT_TOOLS and output.get("success"):
    problems = syntax_check_paths(edited_paths(name, arguments, ctx.workspace))
```

`tools/syntax_check.py:67` 最终是
`subprocess.run([sys.executable, "-m", "py_compile", ...], timeout=_PY_TIMEOUT=20)`。

单次 0.3~1s 不算大，但它挂在 `edit_files` / `write_file` / `edit_lines` / `apply_patch`
**成功后的必经路径**上，一次代码任务会触发数十次——**累计影响可能超过 B1**。

**改动**：

```python
problems = await asyncio.to_thread(
    syntax_check_paths, edited_paths(name, arguments, ctx.workspace)
)
```

`edited_paths()` 只是纯路径计算，很轻，保持同步即可；只把 `syntax_check_paths` 卸载。
现有 `try/except` 已包住整段，异常语义不变。

**风险**：低（`syntax_check_paths` 无共享状态，纯子进程 + 文件读取）。

---

### B3 · `api/local_llm.py` — 与同文件既有写法不一致的 7 处

**现状证据**（全部在 `async def` 路由体内裸调同步方法）：

| 行 | 所在路由 | 调用 | 成本来源 |
| --- | --- | --- | --- |
| 63 | `get_status` | `manager.get_status()` | 见下 |
| 74 | `get_hardware` | `detect_hardware()` | 多个 `subprocess.run(timeout=5)` |
| 96 | `get_recommended` | `detect_hardware()` | 同上 |
| 148 | `start_model` | `manager.get_status()` | 同上 |
| 197 | `stop_model` | `manager.stop()` | `_free_orphan_port(wait_s=3.0)`，固定 ≥3s |
| 218 | `install_model` | `manager.get_status()` | 同上 |
| 244 | `uninstall_model` | `manager.uninstall_model(...)` | 文件删除 |

`get_status()`（`agent/core/local_llm.py:683-780`）= `is_ready()`（`requests.get timeout=0.5`）
+ `detect_hardware()`（`sysctl` / `vm_stat` / GPU 检测，各 `timeout=5`）
+ `get_installed_models()`（遍历模型目录）。

**决定性证据**：同一文件 `:164` / `:223` / `:266` / `:290` 都**正确**用了 `await asyncio.to_thread(...)`，
且 `:163` 就写着注释「阻塞调用（含最多 20s 的就绪等待）放入线程池，避免卡住事件循环」。
**作者完全知道该怎么做，这 7 处是遗漏而非设计决策。**

**改动**：统一改为 `await asyncio.to_thread(...)`，与同文件既有写法对齐。

**风险**：中低。`manager.stop()` / `uninstall_model()` 有状态，需与 B1 共用锁（见 §五）。

---

### A1 · `commands/system.rs` — 日历命令（Tauri 主线程，最严重）

**现状证据**：`add_calendar_event`（`:110`）与 `remove_calendar_event`（`:143`）都是同步 `pub fn`，
内部经 `run_osascript`（`:98`）调用：

```rust
Command::new("osascript").args(["-l", "JavaScript", "-e", script]).output()
```

`output()` 会阻塞到 osascript 退出。两个放大因素：

1. 首次调用需拉起 Calendar.app + 触发 **TCC 授权弹窗**（用户不点就一直等）；
2. `remove_calendar_event` 的 JXA 是**双重遍历所有日历的所有事件**（`:150-160`），
   在事件量大的日历上是 O(全部事件)。

**改动**：两个命令改 `pub async fn` + `tauri::async_runtime::spawn_blocking`，
把 `run_osascript(&script)` 移进闭包（`script: String` 先构造好再 move）。

**附加建议**：`remove_calendar_event` 的 JXA 加时间窗过滤（Calendar 的 `whose` 谓词）
或先按 `startDate` 缩小范围，把 O(全部事件) 降下来。**这一项独立于主线程问题**，可单独评估。

**风险**：低（`run_osascript` 无共享状态）。

---

### A2 / A3 · base64 解码类命令

**现状证据**（均为同步 `pub fn`，跑主线程）：

| 命令 | 位置 | 上限 | 主线程上的工作 |
| --- | --- | --- | --- |
| `save_paste_file` | `paste.rs:112` | **100MB** | base64 解码 → 对 100MB 字符串 SipHash → 落盘 |
| `save_paste_image` | `paste.rs:69` | 10MB | base64 解码 → 哈希 → 落盘 |
| `save_paste_text` | `paste.rs:30` | 2MB | 哈希 → 落盘 |
| `save_export_file` | `workspace.rs:566` | 20MB | base64 解码 → 哈希 → 落盘 |

`save_paste_file` 的 100MB 上限意味着：base64 解码（约 133MB 输入字符串）+ `DefaultHasher`
（SipHash，全量扫一遍 100MB）全在主线程，实测量级 **1~2s 冻结**。

**改动**：改 `pub async fn` + `spawn_blocking`。

**实现要点（避免 Send/Sync 顾虑）**：不要在闭包里用 `AppHandle`。
在命令体（主线程、极快）先解析出目标目录 `dir: PathBuf`，再把 `dir` + `base64: String`
move 进 `spawn_blocking` 闭包。这样闭包只捕获 `PathBuf` / `String`，干净且可测。

**风险**：低。**唯一行为差异**：解码/哈希/写盘不再是原子地发生在主线程，
但这些都是「同一命令内的一次性动作」，无并发语义依赖。

---

### B4 · `api/chat.py:401` — 附件正文解析

**现状证据**（`async def stream_chat` 主体，非生成器，仍在事件循环）：

```python
if not is_image_path(attachment.file_path):
    meta["content"] = read_file_text(Path(attachment.file_path))[:12000]
```

`document_reader.read_file_text` 对 PDF / Word / Excel 走 `anydoc.to_markdown()`（Rust 原生解析），
失败回退 `PyPDFLoader`。`review/009 §5` 已经把**导入开销**降到 0.044s，
但**解析本身**（几十 MB 的 PDF/PPT）仍是同步的，且这次是发生在事件循环里。

**改动**：

```python
text = await asyncio.to_thread(read_file_text, Path(attachment.file_path))
meta["content"] = text[:12000]
```

`_read_text_fallback`（`:46`）在异常分支里，同样处理。

**风险**：低（无共享状态）。

---

### C1 · `services/api.ts:379` — 会话重建 O(N×M)

**现状证据**：外层 `messages.forEach` × 内层 `toolRuns.filter(...).map(...)`，
内层 map 里对**每条 run** 做 `JSON.parse(run.output)`：

```ts
tools.push(
  ...toolRuns
    .filter((run) => { /* 时间窗判断 */ })
    .map((run) => {
      result = run.output ? trimToolResult(JSON.parse(run.output)) : undefined;  // ← 截断在 parse 之后
      ...
      const input = run.input ? JSON.parse(run.input) : undefined;               // ← 每轮再 parse 一次
    }),
);
```

三个叠加问题：

1. **O(N×M)**：每条消息都全量扫一遍 `toolRuns`；
2. **截断顺序错了**：`trimToolResult` 在 `JSON.parse` **之后**才截断，
   4MB 的 `read_file` 结果照样先被完整 parse；
3. **时间戳重复解析**：`new Date(user.created_at).getTime()` 等在外层循环里反复求值。

调用点：`useChatStream.ts:274`（**每次流结束**）、`useSessionLoader.ts:86/93/130`（切会话、上翻历史）。
`getSession` 只对 messages 限 80 条，**`tool_runs` 无上限**——长会话必然劣化。

**改动（三步，可分批落地）**：

1. **先截断再 parse**：`run.output` 超过阈值（如 64KB）时不 parse，或先切字符串再 parse；
2. **降复杂度**：因 `start/end` 是**单调时间窗**，可先把 `toolRuns` 按 `started_at` 排序，
   再用单指针游标扫描分配，把 O(N×M) 降为 O(N+M)；
3. **预解析时间戳**：进循环前建一次索引表。

**附带**：`useSessionLoader.ts:155-166` 的 `loadChangedFiles` 又把所有 `run.output`
重新 `JSON.parse` 一遍 → 应复用同一份解析结果。

**风险**：**中**（本方案中风险最高的一项）。工具归属哪条消息是**用户可见语义**
（决定工具卡片挂在哪条回复下），改动必须逐项等价，需专门回归。

---

### B5 · 同步 SQLite

**现状证据**：`async` 路由内裸调同步 db 函数：

| 位置 | 调用 |
| --- | --- |
| `api/chat.py:831` / `:844` / `:875` | `db.history_for_model` / `db.session_workspace` / `db.touch_session`（均在 `retry_cloud`） |
| `api/chat.py:901` | `db.get_session`（`answer_question`） |
| `api/chat.py:922` / `:935` | `db.get_session` / `db.touch_session`（`inject_message`） |
| `api/sessions.py:158` / `:171` / `:185` | `db.get_session` / `build_context_breakdown`（`compact_session`，后者含全量 token 估算） |

同文件其他位置（`chat.py:219/248/293/467`）**都已用 `to_thread`**——同样是遗漏。

**可行性已确认**：`db/connection.py:31` 用 `_local = threading.local()`，
**连接是按线程缓存的**（`get_conn()` 每线程一个连接，keyed by DB path）。
因此搬到 `to_thread` 是**天然线程安全**的，且线程池复用线程还会命中连接缓存。

**改动**：统一 `await asyncio.to_thread(db.xxx, ...)`。

**风险**：低。两点备注：

1. 每个线程池线程会各持一个 SQLite 连接（WAL 模式，正常）；
2. `sessions.py:171/185` 的 `build_context_breakdown` 是 CPU 型（全量 token 估算），
   搬进线程池后仍占一个 worker，但不占事件循环——符合目标。

---

### C2 / C3 · 前端流式渲染残留 O(n²)

| 位置 | 问题 | 改动方向 |
| --- | --- | --- |
| `MarkdownView/index.tsx:112` | `linkifyFilePaths` 对全文跑 3 遍正则，`useMemo` 依赖 `content` → **流式每帧全文重算** | 流式期间跳过 linkify，结束后一次执行（流式已有「冻结前缀」机制可复用） |
| `MarkdownView/index.tsx:117` | `findUnclosedFenceIndex` 每帧 `content.split("\n")` 建全文数组 | 维护增量状态（当前是否在围栏内），避免每帧全文扫描 |
| `ChoiceBlock/index.tsx:74-90` | `sanitizeJsonQuotes` 对每个引号 `raw.slice(i+1)` → **O(n²)** | 改单趟字符扫描（游标 + 拼接，不切剩余全文） |
| `MarkdownView/index.tsx:264` | 每次渲染都调 `parseOptionsBlock`；streaming 时只 `return null` **隐藏**结果，解析已发生 | 加 `useMemo`；streaming 时提前 return，不解析 |
| `HighlightedCode.tsx:203` | `codeToTokens` 同步（2000+ 行 = 200~800ms） | 超阈值（如 500 行）降级不染色，或分片渲染 |

> 注：`HighlightedCode.tsx:108` 已有 rAF 攒批、`streamBuffer.ts` 已有 rAF 合批、
> `StableMarkdown` 已有冻结前缀——这些都是**已优化项**，本项是它们覆盖不到的残留。
> `ChoiceBlock` 那条尤其值得修：**它连「隐藏」都没省掉解析**。

---

## 五、并发语义变化（本方案最容易被忽略的坑）

把调用从事件循环卸载到线程池，会**同时移除一个隐式保证**：原先这些调用是被事件循环
**天然串行化**的，改为 `to_thread` 后**可以并发执行**。

对本方案影响最大的两处，都涉及**有状态单例** `manager`（`get_manager()`）：

| 调用 | 共享状态 | 并发风险 |
| --- | --- | --- |
| `_start_local_model`（B1） | `manager.process`（`subprocess.Popen \| None`） | 两个并发请求同时拉起 → 重复 spawn llama-server / 端口冲突 / `process` 句柄互相覆盖 |
| `manager.stop()`（B3） | 同上 | 与 start 并发 → 杀掉刚拉起的进程 |

**结论**：B1 与 B3 的 `start`/`stop` 卸载必须**同时**加一把模块级
`threading.Lock`（如 `_manager_lock`）串行化，而不是只改 `to_thread`。
这是「只加 `to_thread` 就完事」的常见翻车点。

其余各项（`syntax_check_paths`、`read_file_text`、`db.*`、base64 解码命令、`osascript`）
**均为无共享状态的纯操作**，无此问题。

---

## 六、不处理项与理由

| 项 | 位置 | 不处理理由 |
| --- | --- | --- |
| WeasyPrint / PDF / PPT 渲染 | `docgen/**` | 只在 `tools/scripts/pdf_*.py` 等**子进程**中执行，已隔离 |
| 图片生成 / 视觉重试的累加 `time.sleep` | `tools/scripts/image_generate.py`、`read_image.py`、`web_common.py` | 同上，全部作为子进程运行 |
| `urllib.request.urlopen`（timeout 5/6s） | `docgen/pdf/cover_builder.py:628,701` | 仅经子进程路径进入，已隔离 |
| `git clone`（timeout 180s） | `skill_lib/github.py:106` | 已用 `to_thread` |
| 工具脚本 `subprocess.run` | `tools/base.py:149/161` | 已用 `run_in_executor` |
| 定时器 | `scheduler.py` | 全部 `to_thread` + `asyncio.sleep` |
| **`watch_workspace` / `unwatch_workspace`** | `commands/workspace.rs:497/543` | **维持 `review/009 §4.2` 原判**：notify 在 macOS 走 FSEvents，递归注册是单次路径级订阅（非逐文件遍历），开销可忽略。**本方案撤回初稿中「watch 递归注册会卡主线程」的判断。** 仅保留一个边界条件：`canonicalize()` 在网络卷上可能变慢，属极端场景，不排期 |

### P3 次级项（记录，不排期）

| 位置 | 问题 |
| --- | --- |
| `MessageItem/index.tsx:354` | `ThinkBlock` 内 `split/map/filter` 未 memo，流式思考每帧重算 |
| `GraphBlock/layouts.ts:108` | `build()` 递归内 `filter` + `new Set([...seen, id])` → O(n²~n³) |
| `GraphRenderer.ts:202` | `computeLayout` 同步跑 dagre/force |
| `ChartBlock/index.tsx:105` | `setOption` 未关动画；`chartOptions.ts` 无 `large`/`progressive`/`sampling` |
| `ConversationMinimap.tsx:259` | hover 时同步渲染整条长回答 |
| `MermaidBlock.tsx:215` | `mermaid.render` 同步 |
| `MessageHelpers.tsx:209` | `grouped.findIndex` 在循环内 → O(tools²) |
| `ProjectList.tsx:86` | 每项目 `sessions.filter` 全量扫描 → O(P×S) |

---

## 七、验证方案

**目标不是「感觉不卡了」，而是给出可复现的量化证据。**

### 7.1 后端（B1–B5）：事件循环可用性压测

这是本方案最核心的验证手段，可统一度量所有后端项：

> 在**触发阻塞操作的同时**，以 100ms 间隔并发请求 `GET /api/health`，记录响应延迟分布。

- **改造前**：应能观察到与阻塞时长同量级的延迟尖峰（B1 可达数十秒）；
- **改造后**：应稳定在 ~10ms（无尖峰）。

`/api/health`（`main.py:181`）本身很轻，是理想探针。逐项验证：

| 项 | 触发方式 | 期望 |
| --- | --- | --- |
| B1 | 停掉 llama-server，发一条命中本地路由的消息 | 健康检查全程不超时 |
| B2 | 让 agent 写一个含语法错误的 `.py` | 同上 |
| B3 | 打开设置页本地模型面板 / 点启停 | 同上 |
| B4 | 上传一个大 PDF 并发消息 | 同上 |
| B5 | 反复重答 / 插话 / compact | 同上 |

### 7.2 Tauri（A1–A3）

- `cargo check` 通过（`src-tauri/target/` 有预热缓存，增量约 1–2s）；
- 手测：加日历事件 / 粘贴大文件时，**窗口是否仍可拖动**（主线程未被占的直接判据）。

### 7.3 前端（C1–C3）

- Performance 面板统计 long task（>50ms）数量与最大时长；
- C1 专项：构造长会话（80 消息 + 上千 `tool_runs`），对照改前/改后耗时，
  并**逐项核对工具卡片归属未变**（这是 C1 唯一的语义风险点）。

### 7.4 回归

```bash
cd divine-server && python -m pytest --basetemp=/tmp/pt -p no:cacheprovider
```

> 环境备注：`review/009 §6.1` 记录的 Xcode 许可问题**已解决**
> （`/usr/bin/git --version` 现正常返回 2.54.0），此前受影响的 13 个 git 用例应可正常跑，
> 可作为本次回归的额外收益确认。

---

## 八、工作量与实施顺序

| 阶段 | 项 | 改动量 | 风险 | 说明 |
| --- | --- | --- | --- | --- |
| **一** | B1 | 1 行 + 锁 | 低 | 收益/成本比最高，先落 |
| | B2 | 1 行 | 低 | 高频路径，累计收益大 |
| | B3 | 7 行 + 锁 | 低 | 与同文件既有写法对齐 |
| **二** | A1 | 2 个命令改 async | 低 | 主线程最严重项 |
| | A2 / A3 | 4 个命令改 async | 低 | 同型，可一次做完 |
| **三** | B4 | 2 处 | 低 | |
| | C1 | 三步重构 | **中** | 需专门回归工具归属语义 |
| **四** | B5 | 9 处 | 低 | 连接模型已确认安全 |
| | C2 / C3 | 5 处 | 中 | 渲染行为需目视确认 |

**阶段一、二建议合并为一次提交**（后端 3 处 + Tauri 6 个命令，全部是「补上漏掉的隔离」，
语义零变化）；**C1 建议独立提交**，因其含唯一的用户可见语义风险。

---

## 九、结论

项目在阻塞隔离上**已有大量正确实践**（`spawn_blocking`、`to_thread`、
工具子进程化、SSE 攒批、rAF 合批、虚拟滚动），本方案发现的 9 处
**集中在「遗漏」而非「架构缺陷」**——多处都能看到「同文件相邻代码已正确处理，唯独这几处漏了」的模式
（B1 上下两行、B3 同文件 4 处、B5 同文件 4 处）。

因此本方案的性价比很高：**大部分改动是补上一行 `await asyncio.to_thread(...)`
或把 `pub fn` 改成 `pub async fn`**，不涉及架构调整。

唯一需要额外设计的是 **§五的并发串行化**（B1/B3 的 `manager` 有状态单例），
以及 **C1 的工具归属语义回归**。这两点是本方案真正的风险所在，其余为机械改动。

---

## 十、实施记录（2026-09-19）

**11 项全部落地**（B1–B5、A1–A3、C1–C3），按 §八 拆成三个提交：

| 提交 | 内容 | 说明 |
| --- | --- | --- |
| ① `fix(perf): 隔离后端与 Tauri 主线程的同步阻塞点` | 阶段一+二：后端 B1/B2/B3 + Tauri A1/A2/A3 + B4 + B5 + 新增回归测试 | 全部是「补上漏掉的隔离」，语义零变化 |
| ② `perf(chat): 会话重建由 O(N×M) 改为预解析 + 二分窗口` | C1 | 含唯一的用户可见语义风险，独立提交便于回溯 |
| ③ `perf(chat): 流式渲染消除重复扫描与重复解析` | C2 / C3 | 渲染行为需目视确认，同样独立 |

C1 独立是 §八 的明确要求；C2/C3 另立一个提交，是因为它们改动的是**渲染路径**
（流式期间的围栏切分与文件路径 linkify），与 C1 的数据层重构不是一回事，
混在一起会让「C1 出问题」时的回滚粒度变粗。

### 10.1 与方案原文的三处偏差（均已按实际代码为准实施）

| # | 方案原文 | 实际情况 | 处理 |
| --- | --- | --- | --- |
| 1 | §一：「`app/api/*.py` **全部是 `async def`**（26 处，0 处同步 `def`）」，据此推出「FastAPI 不会把任何路由自动放进线程池」 | 实测 **104 处同步 `def` + 21 处 `async def`**。FastAPI/Starlette 会自动把同步 `def` 路由放进线程池 | 结论方向不变（async 路由里的裸调仍然阻塞事件循环），但**范围大幅收窄**：`sessions.py` 11 个路由里只有 `compact_session` 是 async，**只有它需要改**。其余 10 个若改成 `async def` 而不补 `to_thread`，等于**把阻塞搬到事件循环上**——是新增缺陷，故不动 |
| 2 | §五：加一把**模块级** `threading.Lock`（如 `_manager_lock`） | `LocalLLMManager` 已有细粒度 `self._lock`（只护 `self.process` 句柄，且注释明确「不能在持有 `_lock` 时调 `stop()`」）；全仓 `grep _manager_lock` 零命中 | 改为在类内新增**粗粒度 `self._op_lock = threading.RLock()`**，用 `@_serialized` 装饰器套在 `start` / `stop` / `uninstall_model` 上。**必须是 `RLock`**：`start()` 内部会调 `stop()`，普通 `Lock` 直接死锁 |
| 3 | §四 C2：`sanitizeJsonQuotes` 的 `raw.slice(i + 1)` 是 **O(n²)** | V8 的 `String.prototype.slice` 返回 **SlicedString（O(1) 视图，不复制）**，实测 2KB→140KB 只放大 1.0–1.4×，非二次 | 改动照做（少一次分配、意图更清楚），但按**微优化**对待；因它是行为敏感代码，另做了 40,009 例逐字节等价对拍 |

### 10.2 方案未写、实施时新增的两项设计

1. **`install_model` 有意不加锁**。它是分钟级网络下载，与进程句柄无关；持锁会把
   `stop_model` 一起卡住。已在方法 docstring 与测试里双向锁定（加锁/不加锁都会红）。
2. **B1 的轮询上限 40s → 20s**。`manager.start` 内部已等 `wait_s=10s`，再叠 40s
   会让最坏路径到 50s，期间线程池工作线程一直被占。改后最坏 30s，
   `tests/test_main_thread_offload.py::test_start_local_model_polling_cap_is_20s` 锁定该数值。

### 10.3 验证证据

**新增回归测试** `divine-server/tests/test_main_thread_offload.py`（14 个用例）：

- §五并发锁：并发探针验证 `start`/`stop`/`uninstall_model` 互斥（`max_active == 1`）；
  「`start` 内部调 `stop`」路径验证可重入（普通 `Lock` 会在 10s 后判失败）；
  `install_model` 不持锁（下载中 `stop()` 必须能立刻返回）。
- 事件循环可用性：用「阻塞期间循环还能跑多少个 10ms tick」当指标——被冻住时
  tick 停在 0~1，卸载后接近 `block_s / 0.01`。覆盖 `local_llm.stop` / `local_llm.status` /
  `sessions.compact_session`（db 与 breakdown **分别单独量**）。
- 端到端探针（§7.1 的方法，落到测试里）：起真实 ASGI 栈（`TestClient` + 真实路由），
  一边 `POST /api/local_llm/stop` 一边循环打 `GET /api/health`。冻住时第一条探测就要 2s
  （实测样本 `[2.032, 0.002, 0.002]`），卸载后全程毫秒级。
- 静态兜底：AST 解析收集各文件 `asyncio.to_thread(X, ...)` 的目标名，防止卸载点被改回裸调用。

**变异验证（8/8 全部被捕获，确认测试非空转）**：去掉 `@_serialized`、`RLock`→`Lock`、
给 `install_model` 加锁、`/stop` 改回裸调用、轮询上限改回 40s、
`chat.py` 的 `_start_local_model` 与 `execution.py` 的 `syntax_check_paths` 改回裸调用——
每一处都让对应用例失败。端到端探针单独验过：把 `/stop` 改回裸调用后它报
「`/api/health` 最差 2.03s——事件循环被 `manager.stop` 冻住了」。

**前端**（C1–C3）：项目无 vitest/jest，采用「拷贝真实源码 + 只改模块说明符 + 打桩运行时依赖 +
Node 22 原生 TS 擦除」的对拍方式：

| 项 | 结果 |
| --- | --- |
| C1 工具归属等价性 | 随机对拍 4000 例 + 闭区间边界 + 重答窗口 + 空输入 + 缓存失效，**全部一致**；顺序还原（`hits.sort`）单独覆盖 |
| C1 性能 | 80 消息 / 1200 `tool_runs` / 每条 4038B：**5.4ms → 0.8ms（6.4×）** |
| C2 围栏扫描 | 增量 vs 全量对拍 **78,712 次全部一致**（该对拍在实施中抓出过一个「末尾半行被重复计数」的真实 bug）；200 帧 9.0ms → 6.3ms |
| C2 `sanitizeJsonQuotes` | 40,009 例全部一致 |
| C3 `HighlightedCode` | 超 500 行降级纯文本 |

`tsc -b`、`eslint`（6 个改动文件）、`cargo check`（3 个 Rust 文件）、`ruff check` 均通过。

**回归**：后端全套 **6 failed / 1398 passed / 3 skipped**。这 6 个失败**全部为既有环境问题**，
已在 HEAD 干净树上复现同一组失败：3 个是 `test_llm_thinking.py` 缺 `OPENAI_API_KEY`，
3 个是 `test_react.py` 的 `workspace.mkdir(exist_ok=True)` 被 IDE 的 Python 文件操作
shim（`sitecustomize.py` 的 host-op broker）以 `EEXIST` 拒绝。**本方案未新增任何失败**。
