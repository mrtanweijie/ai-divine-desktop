# 审批门迁移 HumanInTheLoopMiddleware · 架构演进文档

> 状态：**不排期**。2026-09-03 评审定稿：ask_user 按自定义 interrupt 路径先行落地（见 `ask-user-feature-design.md`），本文档记录"8 个审批门迁移 middleware"的目标形态、触发条件、风险与分期路径，满足触发条件后再启动。

---

## 1. 现状分类（2026-09-03 核实）

`app/agent/tools/execution.py` 共 10 处自定义 `_ask_interrupt`，按性质分两类：

| 类别 | 中断点 | 长期归属 |
|------|--------|----------|
| **审批门**（工具执行前拦截放行/拒绝，语义与 middleware 同构） | `subagents_write` L189、`skill_migrate` L266、`skill_migrate_batch` L341、`skill_install` L400、`external_file` L467、`git` L553、`bg_kill` L606、`terminal` L728 | 迁移候选 → `HumanInTheLoopMiddleware` |
| **问题/分支选择**（决策词汇表表达不了） | `plan_choice` L98（模式选择三态 + plan_mode 落库副作用）、`write_calendar` L787（工具执行**后**追问，middleware 是 pre-call 拦截，时序够不着） | **永久保留**自定义 interrupt 轨 |
| 新增 | `ask_user`（信息收集型，见 ask-user-feature-design.md） | **永久保留**自定义 interrupt 轨 |

另有 1 处已在 middleware 上：`write_todos` 计划审批（`tools.py` L229-242，approve/reject + `when` 条件）。

**目标形态**：审批走 middleware（9 个工具统一 `interrupt_on` 配置），提问走 `interrupt()`（3 个问题型）——即 langchain 官方 HITL 文档主张的分工。

---

## 2. 启动触发条件（满足其一才启动）

1. 需要给审批增加 **edit 决策**（用户改参数后再执行）；
2. 审批策略需要做成 **per-tool 可配置权限**（用户可对某类工具关闭确认）；
3. 审批类工具数量增长，`_handle_adapter_call` 里的逐工具特判开始互相纠缠、单点修改成本明显上升。

无触发条件不迁移——统一本身不产生用户可见价值。

---

## 3. 风险清单（2026-09-03 分析，启动前逐条复核）

| # | 风险 | 严重度 | 说明 |
|---|------|--------|------|
| 1 | 多 action 并发 vs 单槽位回传通道 | **正确性级** | middleware 一次 interrupt 可携带多条 `action_requests`，恢复契约是 `decisions` 列表按索引对齐（orchestrator L634-643 按位生成）；现回传通道 `_PENDING_TERMINAL` 按 session_id 单槽位，同断点多确认卡时撑不住。错位 = 把放行发给另一个工具 |
| 2 | 行为等价性验证无锚点 | 高 | 现有 8 处中断的超时降级（180s → allowed=False）、`shutdown_terminal` 强制 reject 旁路均为显式代码；middleware 的超时/崩溃恢复行为由 checkpointer 机制决定，需验证框架超时后是自动降级还是永久挂 checkpoint（后者会导致会话僵死）。断言 resume 值格式的存量测试全部重写 |
| 3 | 决策语义错配 | 中 | `plan_choice` 三态 + 副作用、`write_calendar` post-call 时序，均无法迁入——双轨消不掉，全量迁移达不到"统一"字面目标 |
| 4 | langchain 版本耦合面 ×9 | 中 | middleware 决策合成、`when` 回调签名、ToolMessage 生成属框架内部行为；押上 9 条链路后每次 langchain 升级（1.3.x 迭代快）全部重验 |
| 5 | 同步发版、回滚成本高 | 中 | resume 格式变化可能迫使前端 decide 通道改动；桌面端 sidecar + Tauri 壳同步发版、无灰度 |

---

## 4. 分期路径

### Phase 0 · 前置验证 spike（不碰生产代码）
用 fake_model + evals harness（`evals/`）回答两个未知数：
- middleware 超时/进程重启后 resume 的确切行为（风险 2 的核心）；
- 多 action 并发下 `decisions` 按位对齐的实现方式（风险 1 的核心）。
产出结论写入本文档，若行为不可接受则终止迁移。

### Phase 1 · 试点 `bg_kill`
选它的理由：单 action、无 ctx 副作用、无专属回传旁路、影响面最小。
**硬约束：SSE 外层协议不变**——`_interrupt_sse` 继续从 `action_requests` 翻译出 `confirm_type: bg_kill` 卡片，前端零改动；变化仅限后端内部 resume 格式。

### Phase 2 · 分批迁移（每批独立回归）
顺序按风险从低到高：`git` → `external_file` → `terminal` → `skill_migrate` / `skill_migrate_batch` / `skill_install` → `subagents_write`。
每批：存量 interrupt 相关测试重写为 middleware 等价断言 + 全量 pytest 绿 + 手动验证一条前端确认链路。

### Phase 3 · 通道升级（仅当多 action 并发确需）
`_PENDING_TERMINAL` 从 session 单槽位改为按 `call_id` 索引（或前端合并决策，二选一在 Phase 0 结论后定）。这是唯一可能触碰前端的环节，安排在末尾。

### 明确不迁
`plan_choice` / `write_calendar` / `ask_user`——在 execution.py 留注释标明归属，防止后人"顺手统一"。

---

## 5. 验收标准

- [ ] 全量 pytest 绿（含重写后的 interrupt 等价用例）；
- [ ] SSE 外层 payload 对前端零改动（Phase 1-2 期间）；
- [ ] 8 个审批门逐一手动回归：触发 → 前端卡片 → 放行/拒绝/超时三路径；
- [ ] langchain 升级回归清单新增"9 条 middleware 链路"检查项；
- [ ] `plan_choice` / `write_calendar` / `ask_user` 确认仍在自定义轨且行为不变。

## 6. 明确不做

- 不为迁移而迁移；触发条件不满足时不启动；
- 不在 ask_user 落地的同一批改动里做任何迁移动作（两件事隔离，各自可独立回滚）。

---

## 7. 补录：interrupt resume 语义事实（2026-09-03 图级测试证实）

langchain 1.3.15 对**工具内 interrupt** 的 `Command(resume)` 是"整体重放工具调用"而非"回到中断点继续"（普通图节点内 interrupt 才是回到中断点）。这对 8 个审批门的迁移/现状核查意味着：

1. **pre-interrupt 副作用会被重放执行两次**。execution.py 里 todo 认领（`_claim_next_todo`）发生在部分中断分支之前——若工具因审批中断后 resume，存在二次认领风险。这是**预存行为**（与 ask_user 无关，本次未改动），迁移前须逐门核查并把"todo 认领挪到审批结果之后"纳入改动范围。
2. **middleware 的审批是 pre-call 拦截**（工具尚未执行），天然不受该语义影响——这是迁移的一个额外收益点，可写进触发条件的"收益"一侧。
3. Phase 0 spike 时把该语义纳入验证项：确认 middleware 路径下 resume 后工具确实只执行一次。
