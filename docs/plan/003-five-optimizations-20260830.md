# 五项优化实施方案分析

> 编号：003 ｜ 类型：plan ｜ 日期：2026-08-30 ｜ 状态：未实施
> 版本：v1.0
> 性质：方案分析（未实施代码）；每项含现状证据、方案设计、改动清单、风险、工作量
> 建议实施顺序：**5 → 3 → 4 → 1 → 2**（5/3 独立小改先落；4 是 1 的地基；2 是新功能放最后）


---

## 方案 1：消息搜索增强（模糊 / 拼音）

**依赖方案 4**（FTS 增量同步是本次改表的地基，两件事应一起做一次迁移）。

### 现状

- 唯一搜索入口 `GET /api/sessions/search`（api/sessions.py:41-44）→ `db.search_sessions`（db/sessions.py:119-200），FTS5 MATCH，命中返回**会话** + content 列 snippet。
- 索引表 `sessions_fts(session_id UNINDEXED, title, content, tokenize='unicode61')`，一行 = 一条消息（sessions JOIN messages，migrations.py:154-162）。
- unicode61 对中文按**单字**成 token，因此中文只能连续字面匹配；英文只能整词匹配——不支持拼音、不支持模糊容错。
- 前端 `SessionSearchModal.tsx`（300ms 防抖、AbortController 已就绪），展示 snippet `<mark>` 高亮。

### 方案设计

**表结构变更**（一次迁移）：`sessions_fts` 增加第 4 列 `pinyin`（UNINDEXED 不需要，要可检索）：

```sql
CREATE VIRTUAL TABLE sessions_fts_v2 USING fts5(
    session_id UNINDEXED, title, content, pinyin, tokenize='unicode61'
);
```

- 用 **v2 新表 + 后台回填 + `ALTER TABLE ... RENAME` 原子切换**，避免迁移期间搜索空窗；回填放启动后台线程，旧表保留可回滚。

**索引时拼音生成**（在方案 4 的 `sync_session` 内完成）：

- 新依赖 `pypinyin`（纯 Python）；音节用无声调形式。
- 每行写入两种形式：分写 `"zhi fu"` + 连写 `"zhifu"`（连写让整词 MATCH，分写支持跨音节短语）。
- 成本控制：**title 全量 + content 截前 2000 字符**参与拼音列（长消息拼音价值低、生成成本高）；存量回填后台进行，增量写入天然摊薄。
- PyInstaller：spec hiddenimports 加 `pypinyin`（onefile 体积 +约 2MB）。

**查询改写器**（新增 `db/fts_query.py`，纯函数可单测）：

| 输入 | 改写策略 |
| --- | --- |
| 纯中文 | 原词 AND（现状）→ **0 命中时降级为词间 OR + rank 排序**（模糊召回的主手段） |
| 纯 ASCII 且合法拼音序列（如 `zhifu`、`zs`） | MATCH pinyin 列：`"zhi fu" OR zhifu`，**末音节加前缀 `*`**（`zhif*`）；缩写（`zs`）逐音节 phrase + 前缀 |
| 混合 | 两路 OR 合并去重 |
| FTS 语法错误 | 维持现有 LIKE 降级（sessions.py:186-199 不动） |

拼音合法性判定用内嵌音节表正则（查询串极短，无性能问题；pypinyin 只用于索引侧）。

**前端**：占位符文案提示"支持拼音"（i18n ×3）；拼音命中时 snippet 取自 content 列仍可高亮原文（MATCH 命中 pinyin 列时 FTS snippet 仍按列参数取 content，可能无 `<mark>`——fallback 显示标题 + 内容首行截断即可）。

### 改动清单

`requirements.txt`、`db/migrations.py`（v2 表 + 切换迁移）、新增 `db/fts_query.py`、`db/sessions.py`（search_sessions 用改写器）、`db/fts.py`（方案 4 的 sync 内写拼音列）、前端 `SessionSearchModal` + i18n、`tests/test_fts_query.py` + 回填测试。

### 风险

- **可选不做**：trigram 模糊容错（错字编辑距离类）。本机 SQLite 3.53.4 已验证支持 trigram tokenizer，但要求 ≥3 字符查询且索引翻倍——建议作为 Phase 2 设置项开关，v1 不做。
- pypinyin 对多音字取默认读音（如"重庆"→chong qing），可接受；词典数据使 PyInstaller onefile 增大约 2MB。

### 工作量：2 天（含回填迁移与测试）

---

## 方案 2：快捷键系统 + 统一 keymap（新功能）

### 现状（含 3 个顺手可修的问题）

- 已有 4 个硬编码 combo：Ctrl+N 新会话 / Ctrl+F 聚焦搜索 / Ctrl+K 聚焦输入框 / Ctrl+Shift+T 切换深度思考（`pages/chat/index.tsx:541-570`）：
  1. **macOS bug**：只判 `event.ctrlKey`，macOS 用户按 ⌘ 无效、按字面 Ctrl 才触发——应按平台归一化（mac→metaKey）。
  2. `useEffect` **无依赖数组**，每次渲染重挂监听器（功能正常但浪费）。
  3. 散落无登记，用户不可见、不可配置。
- **ChatInput 回车发送无输入法合成态防护**（`ChatInput/index.tsx:312-316`：`event.key === "Enter" && !event.shiftKey` 直接 send）——中文输入法选词确认的回车会**误发消息**，应加 `event.isComposing` 防护。
- Modal Esc / Dropdown 方向键属于控件局部语义，**不进 keymap**，保持现状。
- Tauri 侧：无 global-shortcut 插件（Cargo.toml:25-28 仅 dialog/notification/process/updater；capabilities 无相关权限）。

### 方案设计（两层）

**第 1 层：应用内统一 keymap（前端）**

```
src/config/keymap.ts     —— 唯一事实源
src/hooks/useShortcuts.ts —— 单一 window keydown 监听 + action registry
```

- `ShortcutDef`：`{ id, keys: { mac, win, linux }, scope: 'app' | 'composer', i18n 描述, enabled }`；默认表导出为 const（可被 settings 覆盖）。
- `matchShortcut(event, def)` 工具：mod 归一化（darwin→metaKey / 其他→ctrlKey）、`isComposing`/keyCode 229 防护、editable target 防护（scope 判定用）。
- action registry：`ShortcutProvider` 提供 `registerAction(id, fn)` context，特性组件自持回调（避免 keymap 反向依赖业务模块）；单一监听器按 scope 窄→宽解析，命中即 `preventDefault`。
- 迁移现有 4 combo 进 keymap（修 1/2 两个 bug）；ChatInput 的 Enter/Shift+Enter 属文本编辑语义，留局部但复用 `isComposing` 判定工具。

**第 2 层：Tauri 全局快捷键（系统级）**

- Cargo.toml 加 `tauri-plugin-global-shortcut = "2"`，lib.rs `.plugin(tauri_plugin_global_shortcut::init())`，capabilities 增加 `global-shortcut:allow-register / allow-unregister / allow-is-registered`。
- **Phase 1 只做内置动作 `toggle_window`（默认 CmdOrCtrl+Shift+D）**，建议 Rust 侧 setup 注册（webview 未就绪也生效）：handler 判断主窗口 visible+focused → hide，否则 show+set_focus（复用 lib.rs:68-81 的关窗隐藏逻辑语义）。
- Phase 2（可选）：JS API `@tauri-apps/plugin-global-shortcut` 运行时注册，支持用户改键并持久化到 settings。

**设置 UI**：SettingsModal basic tab 增加「快捷键」分组：应用内快捷键列表（只读展示 + i18n 描述）+ 全局唤醒开关与键位展示；i18n ×3。

### 改动清单

`src/config/keymap.ts`（新）、`src/hooks/useShortcuts.ts`（新）、`pages/chat/index.tsx`（4 combo 迁移 + 修监听器）、`ChatInput/index.tsx`（isComposing）、`SettingsModal` + i18n ×3、`src-tauri/Cargo.toml`、`lib.rs`、`capabilities/default.json`、`package.json`（Phase 2 才需要 JS API）。

### 风险

- WebView 吞键：`Cmd+W/Cmd+T` 等被 WebView 拦截的键位要避开，选键时逐一真机验证。
- 全局快捷键与其他应用冲突（尤其截图/输入法类），需可关闭。
- Tauri 2 global-shortcut 插件权限 schema 与 macOS 辅助权限无关（无需额外授权），但 Windows 上注册失败要静默降级 + 日志。

### 工作量：keymap 层 1 天 + 迁移修 bug 0.5 天 + 全局插件与设置 UI 1-1.5 天 ≈ **2.5-3 天**

---

## 方案 3：history_for_model 尾部窗口化（消除每轮全量扫描）

### 现状

`db/history.py:57-69`：每轮对话 `SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC, rowid ASC` **全量拉取该会话所有消息**，内存切片 `messages[-limit:]`（limit=context_limit，默认 20）。会话上千条消息后，每轮（含每轮 compact 检查、上下文用量环 build_context_breakdown compact.py:172、定时任务 scheduler.py:156、云端重答 chat.py:651）都重复全表解码。

### 方案设计（保持签名与输出逐字节等价）

```python
# history_for_model 内部改为尾窗 SQL，签名不变：
if until_message_id:
    target = conn.execute(
        "SELECT rowid FROM messages WHERE id = ? AND session_id = ?",
        (until_message_id, session_id),
    ).fetchone()
# target 不存在 → 与现状一致：不做截断，走无 until 分支（现在的循环查不到也不截断）
sql = ("SELECT * FROM messages WHERE session_id = ? "
       + ("AND rowid <= ? " if target else "")
       + "ORDER BY created_at DESC, rowid DESC LIMIT ?")
rows = conn.execute(sql, params).fetchall()
messages = [dict(r) for r in reversed(rows)]
```

- **等价性关键**：用 `(created_at DESC, rowid DESC)` 复合键排序再反转，与现状"升序全量 + 尾切片"结果逐条一致（rowid 全局唯一，无并列歧义）。
- 尾窗起点可能落在 tool 消息上——现有裁剪 `while messages[0]["role"] == "tool": pop(0)`（history.py:82-83）**原样保留**，行为与全量版一致（防悬空 tool 结果触发 API 400）。
- `parts` 的 IN 查询（history.py:71-80）天然只查窗口内 id，不动。
- **配套索引**：messages 目前仅有 `idx_messages_session(session_id)`（migrations.py:105），尾窗查询仍需过滤后排序；加 `CREATE INDEX idx_messages_session_time ON messages(session_id, created_at)` 消除排序，尾窗即 O(log n + limit)。

### 改动清单

`db/history.py`（SQL 改写 ~20 行）、`db/migrations.py`（1 个索引）、新增 `tests/test_history_window.py`。

### 测试要点（等价性优先）

1. **新旧对比**：构造含 tool_calls/tool_result/空 assistant/附件分块的会话，断言窗口版与"全量+切片"参考实现输出一致。
2. `until_message_id` 截断（含 id 不存在回退全量语义）。
3. 窗口首条为 tool 消息时裁剪正确。
4. session_summaries 前置注入不受影响。

### 风险

低。唯一隐患是排序语义假设（created_at 与 rowid 单调一致性）——用复合键排序后已无此假设。compact 摘要走的是编排层传入的 history 参数（compact.py:92,120），不经 DB 全量读，不受影响。

### 工作量：0.5 天

---

## 方案 4：FTS5 去掉"每次搜索全量 rebuild"

### 现状

- `db/search_sessions` **每次搜索**都执行 `rebuild_fts5(conn)`（db/sessions.py:157-161）：`DELETE FROM sessions_fts` 全表 + `INSERT SELECT sessions JOIN messages` 全量重插（migrations.py:164-178）。搜索是前端 300ms 防抖高频操作，每次键入都全库重写索引。
- 全部写路径（FTS 需要感知的只有 4 处，已核实无遗漏）：
  - `add_message`（db/messages.py:39）
  - `clear_messages`（db/messages.py:30 删该会话消息 + 改标题）
  - `update_session` 改标题（db/sessions.py:77-89；:109 的 touch 只动 updated_at，无需钩子）
  - `delete_session`（db/sessions.py:113，messages 级联删）
  - messages 上仅有的 UPDATE 是 choice_state（db/messages.py:133），不改变 content，**无需钩子**。

### 方案设计（增量同步 + 水位线自愈）

新增 `db/fts.py`：

```python
def sync_session(conn, session_id):
    # 删该会话的 FTS 行，再从该会话重插（方案 1 落地后此处同时生成 pinyin 列）
    conn.execute("DELETE FROM sessions_fts WHERE session_id = ?", (session_id,))
    conn.execute("INSERT INTO sessions_fts(session_id, title, content) "
                 "SELECT s.id, s.title, m.content FROM sessions s "
                 "JOIN messages m ON m.session_id = s.id WHERE s.id = ?", (session_id,))

def catchup(conn):
    # 水位线兜底：fts_state 表存 last_rowid
    # MAX(messages.rowid) == 水位线 → 无事（热路径零成本）
    # > 水位线 → 插入增量行并推进水位线
    # < 水位线 → 存在绕过钩子的删除 → 全量 rebuild 一次（自愈）
```

- **写钩子**：上述 4 处在各自事务内调用 `sync_session`（必须复用传入的共享连接 conn，禁止函数内新开 `get_conn()`，否则嵌套事务提交错乱——connection.py 的既有约定）。
- **搜索路径**：删掉"每次 rebuild"（sessions.py:157-161），改为 `catchup(conn)` 后直接 MATCH。正常情况下 catchup 是一次 `SELECT MAX(rowid)`，纳秒级。
- `rebuild_fts5` 保留，仅用于初始化迁移与水位线自愈。
- 会话删除后 FTS 行清理：delete_session 钩子里按 session_id 删（不再依赖全量 rebuild）。

### 改动清单

新增 `db/fts.py`、`db/migrations.py`（fts_state 表 + 初始化）、`db/messages.py` / `db/sessions.py`（4 个钩子 + search 改造）、`tests/test_fts_sync.py`（新增消息立即可搜、删除后消失、绕钩子删除触发自愈 rebuild、标题改名生效）。

### 风险

- 钩子遗漏：靠水位线自愈兜底（发现 rowid 回退即全量重建一次），最坏情况等价于现状。
- 旧触发器教训（migrations.py:181-193：TEXT session_id 当 rowid 用导致 SQL logic error）：本方案不使用 FTS5 'delete' 特殊命令与触发器，按 UNINDEXED 列普通 DELETE，不踩同一坑。

### 工作量：1 天（含测试）；与方案 1 合并实施时共享迁移

---

## 方案 5：显式 max_retries（顺手项）

### 现状

- `ChatDeepSeekProvider.__init__` 的 `llm_kwargs`（llm/langchain.py:188-195）未传 `max_retries` → 走 `ChatDeepSeek`（继承 BaseChatOpenAI）的**隐式默认 2 次**，版本升级行为可能漂移，且无任何日志可见。
- `OpenAIChatProvider`（llm/langchain.py:335-389）同样未显式。
- 顺带发现：`request_timeout` 也未设置（客户端级无超时；目前靠 tool_runtime 的 wait_for 兜底）。

### 方案设计

1. settings.json 增加可选字段 `max_retries`（默认 2）；`ChatDeepSeekProvider` / `OpenAIChatProvider` 构造时 `llm_kwargs["max_retries"] = int(entry.get("max_retries") or 2)`。
2. 同一行顺手显式 `"timeout"`（默认 60s，流式场景指首包/请求超时语义按 openai client 定义）。
3. 初始化打一行结构化日志：provider/model/base_url/max_retries/timeout（复用现有慢请求日志中间件的 logger）。
4. 运行期重试日志无需新代码：openai/httpx 客户端对重试自带 WARNING（"Retrying request..."），仅需确认日志配置未过滤 httpx logger。
5. `data/settings.json` 字段在 README「多模型配置」小节补一行说明。

### 改动清单

`app/llm/langchain.py`（两处 kwargs + 1 行日志）、`tests/`（断言构造后 `self.llm.max_retries` 生效）、README 一行。

### 风险

无。Mock provider 不涉及；重试发生在 openai 客户端内部，SSE 流中断恢复语义不变。

### 工作量：0.5 天

---

## 汇总

| # | 方案 | 工作量 | 风险 | 依赖 |
| --- | --- | --- | --- | --- |
| 5 | 显式 max_retries（+timeout） | 0.5 天 | 无 | 独立 |
| 3 | history_for_model 尾窗化 + 复合索引 | 0.5 天 | 低（等价性测试兜底） | 独立 |
| 4 | FTS 增量同步 + 水位线自愈 | 1 天 | 低（自愈兜底 = 最坏现状） | 独立 |
| 1 | 拼音/模糊搜索（pypinyin + 查询改写器 + v2 表切换） | 2 天 | 中（回填迁移需原子切换） | **依赖 4** |
| 2 | 统一 keymap + Tauri 全局快捷键（两层） | 2.5-3 天 | 中（吞键/冲突需真机验证） | 独立 |

合计约 **6.5-7 人日**。推荐批次：**第一批（半天，立即可交）5+3；第二批（1 天）4；第三批（2 天）1；第四批（2.5-3 天）2**。2 里顺带修复的两个现存 bug（macOS ⌘ 快捷键失效、中文输入法回车误发送）与 1/4 无耦合，可随第一批先出 hotfix。
