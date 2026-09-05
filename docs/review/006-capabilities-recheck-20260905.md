# Divine 项目功能分析与优化点（2026-09-05 重审版）

> 编号：006 ｜ 类型：review ｜ 日期：2026-09-05 ｜ 状态：现行有效（最新复盘）
> 方法：3 路并行代码勘察（后端 / 前端 / 工程化·桌面壳），对《[002-project-capabilities-20260830.md](002-project-capabilities-20260830.md)》(08-30) 与《[项目健康度复盘](004-project-health-20260901.md)》(09-01) 的旧结论逐条核验，并盘点 09-01 之后的新增功能与新暴露问题。全部结论附 `文件:行号` 证据。


## 0. 当前体量与功能全景

| 层 | 规模（09-05 实测） | 职责 |
| --- | --- | --- |
| 后端 sidecar | `app/` 260 个 .py、50,336 行 | Agent 编排、**64 个工具**、RAG、调度器、本地模型、文档生成 |
| 后端测试 | `tests/` 72 文件（732 个 test 函数）+ `evals/` 12 场景 | 工具域为主 |
| 前端 | `src/` 121 个 TS/TSX、23,891 行 + 45 个 .less、8,510 行 | 聊天 UI、虚拟滚动、会话/项目/设置/任务/技能页 |
| 桌面壳 | Rust 9 个 .rs、1,532 行（unsafe 1 处、unwrap 0 处） | sidecar 监管、托盘、粘贴落盘、日历桥接、更新器、全局快捷键 |

**能力域不变**（对话/意图路由/工具/计划子代理/RAG·记忆·技能/文档生产力/任务日程/终端代码/会话管理/桌面集成/工程化，详见旧分析第 1 节），09-01 后**新增能力**：

| 新功能 | 核心实现 | 说明 |
| --- | --- | --- |
| Agent 进度可观测 | `db/todos.py:161-178`（settle/abort 计划终态）、`agent/tools/tool_runtime.py:216-241`（轮次耗时落库 tool_runs.turn/duration_ms）、`agent/core/constants` 超时重试 `_RETRYABLE_TOOLS`；前端 `TracePanel.tsx:26-120`（分轮耗时条+慢调用检测）、`ToolStatusCard.tsx:148-176`（徽标/失败合并） | 09-04 |
| 执行中插话（steering） | `agent/core/injection.py`（队列上限 5 条）+ `middleware/injection.py:23-33` + `POST /sessions/{id}/inject`（chat.py:748-776）；前端 `useChatStream.ts:571-596` sendSupplement | 09-03 |
| ask_user 主动提问 | `tools/execution.py:87-180 _handle_ask_user`（每轮限 1 次、超时降级、full 模式跳过）+ `POST /chat/answer`；前端 `AskUserForm.tsx` | 09-03 |
| html_generate 工具 | `tools/adapters/html_generate.py` + `tools/scripts/html_generate.py`（153 行，与 ux_html 分工）；提示词 `_HTML_PAGE_RULES`（+211 行） | 09-03/04 |
| 孤儿 tool_calls 全链路清洗 | `db/history.py:259-330 _sanitize_tool_groups` + `llm/langchain.py:172-221` 请求级兜底 + `orchestrator.py:94-111 _repair_tool_groups` 线程修复 | 09-02/04 |
| 会话历史回溯检索 | `db/history.py until_message_id`（窗口外提问自动检索早期对话注入） | — |
| 全局快捷键 | `tauri-plugin-global-shortcut`，`lib.rs:33-42`（⌘⇧D 唤起/隐藏，可设置开关） | 08-30 |
| 设计 token 化 | `styles/index.less:2-46` CSS 变量全套 + `styles/uiPalette.ts` JS 镜像（Chart/Mermaid 跟随主题） | 09-03 |
| 其他 | mermaid 深色对比色自适应（`MermaidBlock.tsx:135-179`）、消息 diff 视图、文件面板树列拖拽收起、md 预览默认渲染、冻结 sidecar 冒烟脚本 `smoke-sidecar.sh`、`evals/` 场景评测框架、后端 ruff 引入 | — |

工具数：实际注册 **64 个**（新增 `html_generate`、`ask_user`），README「62 个」已过期。

## 1. 旧问题修复核验（对照 09-01 复盘）

| 旧问题 | 状态 | 证据 |
| --- | --- | --- |
| P0 自动更新链路断裂 | ❌ **未修，09-02 重发仍坏** | 见 §2 P0-1 |
| P0 CI 无质量门禁 | ❌ 未修 | 两个 workflow 均无 pytest/ruff/tsc |
| P1 api/chat.py 巨型化 | 🟡 移位未瘦身 | 1616→819 行，拆出 chat_local.py 942 行，合计 1761 行；**意图双轨仍在** |
| P1 chat/index.tsx 巨型化 | 🟡 进行中 | 1347→1117 行，state/hooks 已抽出（35e3d7b），仍全项目第 3 大文件 |
| P1 orchestrator classify 同步阻塞 | ✅ 已修 | `orchestrator.py:409-418` `await asyncio.to_thread(...)` |
| P1 TodoSyncMiddleware 同步 SQLite | ✅ 已修 | `middleware.py:27-29,36` to_thread |
| P1 ToolStatusCard 933 行 | ✅ 已修 | →309 行 + 8 个子文件（ToolConfirmSection 375/MessageHelpers 466/TracePanel 120 等） |
| P2 异常处理统一 | ✅ 大部分 | `main.py:88-113` 全局 exception handler；SSE error_event 属协议约束合理保留 |
| P2 storage.ts 封装落地 | ✅ 已修 | 全 src 仅 5 处 localStorage 且全在封装内（c0b63e8） |
| P2 死代码/重复函数 | ✅ 已修 | groupLabel 0 引用；pad 唯一实现在 `utils.ts:51-53` |
| P2 前端 eslint | ❌ 仍缺 | package.json 无 lint/format 脚本与 devDeps |
| P2 后端 ruff | ✅ 新增 | `divine-server/ruff.toml`（但未进 CI）；mypy 仍缺 |
| 旧清单 checkpointer InMemorySaver | ❌ 未修 | `tools/tools.py:30,264`、`subagents.py:638` |
| 旧清单 审批 180s 硬超时 | ❌ 未修 | `orchestrator.py:659-661`、`chat.py:531`，且 ask_user 复用同一机制 |
| 旧清单 魔法值收敛 | 🟡 大部分 | 端口 8016/阈值 0.75 已入 config；残留 180s×2、`_CHUNK_CHARS`、`_CACHE_TTL` |
| 旧清单 全局快捷键 | ✅ 已修 | 见上表；单实例/开机自启仍缺 |

**小结**：16 项旧问题中 6 项修复、4 项进行中、6 项未动。P0 两项（更新链路、CI 门禁）原样未动，且 09-02 发布 v0.2.1 时重新踩了同一个坑。

## 2. 当前优化点清单（重排优先级）

### P0 —— 断链路 / 红基线（先修）

1. **自动更新链路三处叠加断裂**（用户永远收不到更新）：
   - `scripts/publish-macos.sh:142-146` REPO 推断 sed 只认 github.com，Gitea remote 不匹配时 REPO 变成垃圾非空值，绕过「为空才报错」防线；
   - `release-assets/latest.json:7` url 为 `https://github.com/https://git.duguying.net/...`（pub_date 2026-09-02，v0.2.1 重发仍坏）；
   - `tauri.conf.json:35` updater endpoint 仍指旧仓库 `github.com/mrtanweijie/...`；
   - `.gitea/workflows/release-macos-universal.yaml:397-537` 只传 DMG，**根本不产出 latest.json** → 即使 endpoint 改对也无源。
   - 修法：REPO 推断兼容 Gitea 或强制 `--repo` 并校验格式；endpoint 切 Gitea；workflow 补「签名 tar.gz + latest.json 生成上传」。
2. **测试基线是红的且无门禁**：`divine-server/.pytest_cache/v/cache/lastfailed`（09-04）**28 条失败**未清（travel_theme/terminal_dev/bg_process/checkpoint/evals s01-s09 等）；最低成本组合 = Gitea workflow 加 pytest + `ruff check app/` + `pnpm build`（含 tsc -b）三个 job，并把 `smoke-sidecar.sh` 挂到 build-sidecar.sh 成功尾部（现在纯手动、无人引用）。
3. **版本治理缺位**：0.2.1（08-28）之后大量 feat 合入但版本零推进，`release-notes.md` 只写到 v0.2.1；tag 序号与时间线错乱（v0.3.0 创建于 08-13、v0.4.0 于 08-15，早于 v0.2.0）；Gitea workflow 在 CI 内改写版本（:84-96）与 publish 脚本的三处一致性校验（:121-130）口径不一。

### P1 —— 性能与结构（收益最大）

4. **《流式渲染性能优化方案》B1-B6 一项未落地**（方案 430 行已写好，代码零改动，这是当前最大的性能欠账）：
   - B1 shiki 逐 token setState（最大卡顿源）：`HighlightedCode.tsx:122-130` 仍每 token 一次 `setTokens`，无 rAF 攒批；
   - B2 SSE 无缓冲：`useChatStream.ts:122-135` 每 chunk 全量 `prev.map()` 重建；
   - B3 tool 双 setState（:182-188 与 :202-208）、B4 `[...messages].reverse().find()`（MessageList/index.tsx:139-141）、B5 done 收尾未错峰、B6 服务端 1 delta = 1 事件（`sse.py drain_text`）。建议先做 B1（单文件小改）。
5. **InMemorySaver 换 AsyncSqliteSaver**（`tools/tools.py:30,264`、`subagents.py:638`）：重启后线程态恒空 → 每轮都走 DB 重建 + 全量 `_repair_tool_groups`，compact 跨重启失效，子代理每次重建 agent。一换解决持久化 + 重建开销两个问题。
6. **async 阻塞「残余双轨」**：已修路径与未修路径并存，规范未统一——`chat.py:417-419` `manager.is_ready()` 内部是**阻塞式 requests.get(timeout=0.5)**（local_llm.py:192-199）；stream_chat 端点主体大量同步 SQLite（chat.py:117-333、:462,505,609,617，含重查询 `db.history_for_model` :333）；`orchestrator.py:347,392,497,513`；`scheduler.py:71,120-156`。
7. **意图双轨合一**：本地路由用 `chat_local.py` 的 6 个 `_detect_*`，工具裁剪用 `intent/intent.py:393 classify_intents`（545 行），两套关键词库语义重叠，是拆分后真正该收口的结构问题；顺带拆 `chat.py:361-617` 约 250 行的 generate() 内嵌函数。
8. **chat/index.tsx 二次拆分**：`resolveModelTarget` 重复逻辑（:694-706 vs :716-728）、启动恢复 effect 90 行（:281-371）可抽 `useAppBootstrap`；**ChoiceBlock 用中文 label 做协议判断**（`ChoiceBlock/index.tsx:110-119` `label === "暂时不用"`）——英文 locale 或模型换输出语言即失效，应改按 value/key 判断。

### P2 —— 健壮性与工程化补课

9. **审批 180s 硬超时**（orchestrator.py:660、chat.py:531）：收进 constants + 可配置，理想方案是持久化待审批队列（重启后可恢复决策）。
10. **Rust monitor 线程治理**（`services/sidecar.rs:149-214`、`commands/sidecar.rs:5-8`）：无停止标志、可重复 spawn 多条监控线程、用户 stop 后 5s 探活会静默重启（停止形同虚设）；`spawn():101-104` 无条件认领端口占用者。补 single-instance 插件（多开双 sidecar 抢 8019 现无防护）。
11. **前端补课**：eslint+prettier 缺位；MessageList onScroll 每次 3 个 setState 无节流（MessageList/index.tsx:76-97）、Minimap filter 未 memo（:73-74）；工具卡 key 用 `${tool}-${index}`（MessageItem/index.tsx:223，有 run_id 可用）；storage key 常量未集中；双 DiffView 重复实现（MessageItem 94 行 vs FilePreviewPanel 176 行）；`as unknown as` 6 处、any 9 处、SSE 事件无运行时校验；**前端零测试**。
12. **后端测试补盲**：HTTP 层仅 3 个文件，sessions/projects/files/git/skills/stream_chat 云端主链路全无覆盖；无 conftest.py/pytest.ini/覆盖率；`evals/` 与 `tests/` 双体系未与 CI 打通；db 写放大无 retention（tool_runs 每调用一行、附件 12000 字符 JSON 整段入库）。
13. **收尾清理**：README 工具数 62→64；`app/github_skills.py`、`app/skills.py` re-export 壳与 `chat.py:779-819` 兼容层可删；`.github/workflows/build.yml` 是死配置（remote 为 Gitea 从不生效）建议删除；CSP `script-src 'unsafe-inline'` 与 Entitlements `allow-unsigned-executable-memory` 复核最小化；8019 固定端口问题仍在（前端已走 env，主端口与 CSP 硬编码）。

## 3. 一句话总结

09-01 之后团队执行力很强——8 项新功能全部带测试落地、6 项旧问题修复、两个巨型文件都动了一刀；但**发布侧完全停摆**（更新链路三处断裂 + 09-02 重发仍坏、CI 无门禁、28 条测试失败、版本号 8 天未动），性能侧最大的《流式渲染优化方案》写完即封存。下一轮先把 P0 三件事打通「能发出去」，再按 P1 顺序还性能与结构债。
