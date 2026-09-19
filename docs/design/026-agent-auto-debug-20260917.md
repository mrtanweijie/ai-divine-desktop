# Agent 自动调试能力 · 方案设计

> 编号：026 ｜ 类型：design ｜ 日期：2026-09-17 ｜ 状态：**已实施（P1–P3）**，P4 未实施
> 实施日期：2026-09-19 ｜ 实施记录见 §12（含 4 处与本文设计的偏差及原因）
> 目标：把 Agent 的"改完跑一遍测试"升级为**故障驱动的调试闭环**——运行崩溃或测试失败后，能自动定位到源码行、识别"同一个错第几次出现"、在收敛上限内自主修复，修不动就如实汇报而不是无限打转。
> 前置：`docs/plan/002-code-support-roadmap-20260830.md` 的 P0–P4 已全部实施，**执行腿齐备**（能跑测试、能改代码、能回滚）。本方案只补**定位腿**与**收敛刹车**。

---

## 0. 现状与约束（代码事实）

### 0.1 已具备

| 能力 | 位置 |
| --- | --- |
| 编辑后自动语法检查，错误以 `[语法检查警告]` 回灌模型 | `app/tools/syntax_check.py`、`app/agent/tools/execution.py:1027` 起 |
| 结构化测试结果（pytest/jest/vitest/npm） | `app/tools/adapters/run_tests.py`、`command_output.parse_test_output` |
| 结构化静态检查（ruff/mypy/eslint/tsc） | `app/tools/adapters/lint_check.py`（`_LINTERS`）、`command_output.parse_lint_output` |
| 命令安全分级 safe/confirm/block | `app/tools/terminal_policy.py::terminal_command_policy` |
| 长驻进程管理（dev server / 长测试） | `app/tools/bg_process.py`、`adapters/bg_tool.py`（`bg_status`/`bg_output`/`bg_kill`） |
| 失败回流成计划项 | `app/agent/state/plans.py::_spawn_recovery_todo` |
| 回合上限与优雅收尾 | `app/agent/core/constants.py::MAX_TOOL_TURNS=96`、`ModelCallLimitMiddleware(exit_behavior="end")` |
| 改动可回滚 | `app/tools/checkpoint.py`、`adapters/undo_turn.py`、git 工具集 |
| 自动 code review | `app/tools/adapters/code_review.py`（`review_changes`） |
| 调试场景评测基建（12 场景 + fail_to_pass/pass_to_pass） | `divine-server/evals/` |
| 开发工作流提示词 | `app/agent/core/prompt_sections.py::_PROJECT_WORKFLOW` |

### 0.2 关键缺口

| # | 缺口 | 影响 |
| --- | --- | --- |
| 1 | **没有 traceback / 栈帧解析器**。`command_output.py` 的 7 个 `parse_*` 只覆盖 pytest 汇总行与 `FAILED` 行、jest、ruff、tsc、mypy 这几类文本（`parse_pytest_output` / `parse_jest_output` / `parse_ruff_output` / `parse_tsc_output` / `parse_mypy_output` 为具体解析器，`parse_test_output` / `parse_lint_output` 为分派入口），异常栈帧被当纯文本塞进 content | 模型只知道"这个测试挂了"，不知道挂在哪一行，只能重新全仓 grep 猜——这是"无法自主定位"的根因 |
| 2 | **失败去重按 `tool_name`，不按错误指纹**。`plans.py:74` 的 `_is_recovery_title(title, failed.get("tool_name"))` | 同一个 `AssertionError` 换成 `terminal` 跑就绕过了去重，防不住打转 |
| 3 | **重试上限只在提示词里**（`_PROJECT_WORKFLOW` 的"最多重试 2 次"） | 软约束，模型不遵循即失效；无计数、无强制退出 |
| 4 | **没有复现固化** | prompt 里写了"先写最小验证再动手改"，但没有机制让复现脚本沉淀下来复用 |

### 0.3 约束

- **不引入 embedding / 向量库**（项目原则）。定位靠结构化栈帧解析，不靠语义检索——栈帧本身就是精确的 `file:line`。
- 失败路径改动**不能让成功路径增加任何开销**。
- 解析失败绝不能把一次成功的工具调用变成失败（沿用 `syntax_check` 的既有约定）。
- 前端渲染契约与历史会话回放兼容性不得破坏。

---

## 1. 设计：五环闭环

```
运行复现 → 解析定位 → 假设确认 → 最小修补 → 回归验证
   ↑                                          │
   └──────────── 验证失败，回到定位 ────────────┘
```

现有能力覆盖第 1、4、5 环；本方案补第 2、3 环，并为整个循环加收敛刹车。

---

## 2. 诊断层：`app/tools/diagnostics.py`（新）

### 2.1 数据结构

```python
@dataclass
class Frame:
    file: str          # workspace 相对路径（越界时保留绝对路径）
    line: int
    func: str
    code: str          # 该行源码，≤200 字符，读取失败为空
    is_user_code: bool

@dataclass
class FailureReport:
    kind: str              # "python_traceback" | "node_stack" | "compile" | "unknown"
    exception: str         # "KeyError"
    message: str           # 归一化消息，≤300 字符
    frames: list[Frame]    # 业务帧在前，最多 8 帧
    fingerprint: str       # 12 位十六进制
```

### 2.2 解析器

| 函数 | 覆盖 |
| --- | --- |
| `parse_python_traceback(text)` | `Traceback (most recent call last):` 块 → 逐帧 `File "path", line N, in func`；末行 `ExceptionType: message`；支持一次文本内多个 traceback（pytest 每个失败用例一段）、嵌套异常（`During handling of the above exception`）、`ExceptionGroup` |
| `parse_node_stack(text)` | `at fn (/path/file.ts:10:5)` 与 `at /path/file.ts:10:5`；兼容 vitest / jest 输出 |
| `parse_compile_errors(text)` | 复用 `syntax_check.py` 的 py_compile / tsc 文本格式 |
| `parse_failures(text, runner, workspace)` | 统一入口，按 runner 分派，未知则逐个嗅探 |

### 2.3 指纹算法

```
fingerprint = sha1(f"{exception}@{首个业务帧 file}:{line}")[:12]
```

- **不带 message**：消息里常有变量值（`KeyError: 'user_id'` vs `KeyError: 'uid'`），带上会让同一个 bug 的指纹漂移。
- 无业务帧时退化为 `{exception}@<no_user_frame>`，仍可用于去重，但提示语改为"错误发生在依赖内部，考虑版本/用法问题"。

### 2.4 `is_user_code` 判定

排除：`site-packages/`、`node_modules/`、`dist-info/`、`sys.prefix` 下的标准库路径、`<frozen ...>` / `<string>` / `<stdin>` 等伪文件。不在 workspace 内的路径标 `False`，但仍保留在 `frames` 中（可能是依赖内部逻辑，对根因判断有用）。

### 2.5 输出预算

单次最多解析 10 个 traceback；每帧 `code` ≤200 字符；回灌总量 ≤2000 字符（与 `syntax_check._MAX_PROBLEM_CHARS` 同量级）。超出标注"（已截断，完整日志见 content）"。

---

## 3. 回灌接线（`app/agent/tools/execution.py`）

现状是只有编辑类工具触发语法检查（`execution.py:1027` 起）：

```python
if name in _EDIT_TOOLS and output.get("success"):
    problems = syntax_check_paths(edited_paths(name, arguments, ctx.workspace))
    if problems:
        tool_content += "\n\n[语法检查警告] 刚写入的文件存在语法错误，请立即修复后再继续其他步骤：\n" + ...
```

**新增**：命令类工具失败时的诊断回灌，位置在 `output` 拿到之后、`payload` 组装之前。

```python
if not output.get("success") and name in _COMMAND_TOOLS | {"terminal"}:
    try:
        reports = parse_failures(tool_content, ctx.workspace)
    except Exception:  # noqa: BLE001 — 解析失败不影响工具结果
        reports = []
    if reports:
        tool_content += "\n\n" + format_failure_block(reports, ctx)
```

约束：

- 仅在 `success=False` 时触发，**成功路径零新增开销**；
- 整段 try/except，解析异常不影响工具结果；
- 回灌段固定前缀 `[诊断]`，便于测试断言与前端识别；
- **只加 content 尾注，不动 `data` 结构**，保持前端渲染契约与历史回放兼容。

**双通道**：同时给 `run_tests` 的 `data.failures[]` 补 `trace` 字段（frames + fingerprint）。`data` 给人看 / 给前端渲染，`content` 给模型看——两条独立通道，互不替代。

回灌样例：

```
[诊断] 1 个失败，首个异常定位如下：
  AssertionError: expected 200, got 401
  frames:
    tests/test_api.py:42    test_login
    app/api/auth.py:88      verify_token        <- 业务代码
    app/db/user.py:130      get_by_id
  fingerprint: a3f9c21b7e04（本会话第 2 次）
  → 直接 read_file app/api/auth.py 第 88 行附近，不要重新全仓 grep。
```

---

## 4. 收敛控制：`DebugLoopMiddleware`（新）

### 4.1 为什么不复用 `_spawn_recovery_todo`

`plans.py::_spawn_recovery_todo` 的去重键是 `tool_name`（缺口 2），且它只挂一条计划项、**不做"停止自动重试"的硬刹车**。两者职责不同：recovery todo 面向用户可见的计划，中间件面向模型的收敛控制。二者共存，不互相替代。

### 4.2 中间件设计

新文件 `app/agent/middleware/debug_loop.py`。

- 状态放 `ctx.debug_state: dict[str, int]`（会话级，随 ctx 生命周期），`ctx.debug_halt: bool` 作刹车标志；
- 每次工具失败 → 取 `fingerprint` → 计数；
- **第 2 次**：在 ToolMessage 追加 —— "该错误第 2 次出现，上一次的修改没有解决它。不要重复同样的改法：先加日志/断言确认假设，或换个方向定位。"
- **第 3 次**：追加硬指令 —— "已连续 3 次未能修复同一错误，停止自动重试，向用户如实汇报：错误信息、已尝试的改法、你判断的根因与建议的下一步。"并置 `ctx.debug_halt`；
- **P2 可选**：第 3 次时直接 `jump_to="end"` 收尾，不依赖模型遵循。

### 4.3 接线位置

插在 `app/agent/tools/tools.py::_build_agent` 的中间件列表中，位于 `TodoSyncMiddleware` 之后、`ToolErrorMiddleware` 之前——保证工具结果已成型、且异常格式化仍由 `ToolErrorMiddleware` 兜底。

---

## 5. 复现固化（第 3 环）

| 方案 | 内容 | 成本 | 建议 |
| --- | --- | --- | --- |
| A（轻） | prompt 引导：崩溃类问题先落一个最小复现（`repro.py` 或一个失败测试）再改，改完复跑同一脚本 | 零代码改动 | ✅ 先做 |
| B（重） | 新增 `pin_repro` 工具，把复现命令登记到会话级 registry，每轮收尾自动复跑作为"回归未破坏"守门 | 高 | ⏸ 列 P4 |

---

## 6. 提示词改造

`app/agent/core/prompt_sections.py::_PROJECT_WORKFLOW` 的"验证"条目改写为"验证与调试"：

```
- 验证与调试：编辑后用 git_diff 自查，再跑 lint_check / run_tests。
  失败时按「定位 → 假设 → 最小修改 → 复跑」循环处理：
  · 定位：工具返回的 [诊断] 段已给出异常类型与业务代码栈帧（file:line），
    直接 read_file 该位置附近，不要重新全仓 grep 猜；
  · 假设：改之前先确认根因。不确定就加一行日志/断言跑一次，让证据说话；
  · 最小修改：一次只改一个假设，改完立即复跑同一命令；
  · 收敛：同一个错误（指纹相同）不要用同样的改法重试第 2 次；
    连续 3 次未解决就停止，向用户如实汇报错误、已试改法、判断的根因与建议下一步。
  绝不谎报成功。
```

---

## 7. 改动清单

### 后端（divine-server）

| 文件 | 改动 |
| --- | --- |
| `app/tools/diagnostics.py`（新） | 故障解析层：三类解析器 + `parse_failures` + `FailureReport` / `Frame` + `fingerprint` + `is_user_code` + `format_failure_block` |
| `app/tools/command_output.py` | **不改**。职责是"CLI 汇总 → 计数"，诊断是"异常 → 栈帧"，混在一起会让现有 7 个解析器的测试变脆 |
| `app/tools/adapters/run_tests.py` | `data.failures[]` 补 `trace` 字段（frames + fingerprint） |
| `app/tools/adapters/lint_check.py` | 同上（可选；lint 多为编译期错误，收益低于运行时崩溃） |
| `app/agent/tools/execution.py` | 新增诊断回灌分支（命令类工具失败时追加 `[诊断]` 段） |
| `app/agent/middleware/debug_loop.py`（新） | `DebugLoopMiddleware`：指纹计数、二次注入提示、三次硬刹车 |
| `app/agent/middleware/__init__.py` | 导出 `DebugLoopMiddleware` |
| `app/agent/tools/tools.py` | `_build_agent` 中间件链插入 `DebugLoopMiddleware` |
| `app/agent/core/context.py` | `AgentRunContext` 新增 `debug_state` / `debug_halt` |
| `app/agent/core/prompt_sections.py` | `_PROJECT_WORKFLOW` 验证段改写为调试循环（§6） |
| `app/agent/state/plans.py` | （可选 P4）`_is_recovery_title` 去重键从 `tool_name` 改为 error fingerprint |

### 前端（divine-app，P4）

| 文件 | 改动 |
| --- | --- |
| `pages/chat/components/MessageItem/ToolStatusCard.tsx` | 失败工具卡渲染 `[诊断]` 段：栈帧列表，点击跳到文件预览 |
| i18n 三语（`zh-CN` / `zh-TW` / `en`） | `tool.diagnosis`、`tool.fingerprintRepeat` 等，缺一不可 |

### 测试

| 文件 | 内容 |
| --- | --- |
| `divine-server/tests/test_diagnostics.py`（新） | 解析 / 指纹 / 业务帧过滤 / 截断 / 畸形输入 |
| `divine-server/tests/test_debug_loop.py`（新） | 计数 / 二次注入 / 三次刹车 / 成功路径零影响 |
| `divine-server/tests/test_run_tests.py` | 补 `trace` 字段断言 |

---

## 8. 关键决策与取舍

| 决策 | 选择 | 理由 |
| --- | --- | --- |
| 定位机制 | 结构化栈帧解析，**不做** embedding 语义检索 | 项目原则不引入向量库；栈帧本身就是精确的 `file:line` |
| 解析层归属 | 独立模块 `diagnostics.py`，不进 `command_output.py` | 后者职责单一（CLI 汇总 → 计数），混入栈帧解析会让 7 个现有解析器的测试变脆 |
| 回灌通道 | 只加 content 尾注，不动 `data` 结构 | 保持前端渲染契约与历史回放兼容；`data` 侧改动另开字段 |
| 指纹是否含 message | **不含** | 消息里的变量值会让同一 bug 指纹漂移 |
| 收敛控制位置 | 中间件（工程化），不放 prompt | prompt 里的"最多重试 2 次"是软约束，模型不遵循即失效；中间件能计数、能强制 |
| 去重键 | error fingerprint 替代 `tool_name` | 同一错误换工具跑就绕过了旧去重 |
| 失败路径成本 | 成功路径零新增开销 | 诊断只在 `success=False` 时触发 |
| 硬刹车后行为 | 汇报而非静默中止 | 沿用项目"不谎报成功"原则；汇报让用户接手优于静默失败 |
| 与 recovery todo 关系 | 共存，不合并 | recovery todo 面向用户可见计划，诊断段面向模型；职责不同 |

---

## 9. 边界与异常

- **无 traceback 可解析**（纯 `exit code 1`、编译期错误）：不注入 `[诊断]` 段，走原有路径，行为与现在完全一致；
- **栈帧全在依赖内部**（无业务帧）：指纹退化为 `{exception}@<no_user_frame>`，仍可去重，提示语改为"错误发生在依赖内部，考虑版本/用法问题"；
- **路径越界**：workspace 外的帧标 `is_user_code=False`，`file` 保留绝对路径但显示时截断；
- **输出超大**：单次最多 10 个 traceback、总回灌 ≤2000 字符，超出标注已截断；
- **畸形 / 半截 traceback**（进程被 kill、输出被截断）：解析返回空列表，不报错；
- **Windows 路径**：`File "C:\..."` 反斜杠归一为 `/` 后再判 workspace 归属；
- **与 `[语法检查警告]` 共存**：两者前缀不同，同一轮可能都出现，顺序为"语法检查在前、诊断在后"；
- **react 模式**：诊断是工具结果后处理，与 `ReActParseMiddleware` 无关，`tool_mode=react` 下同样生效；
- **子 Agent**：子 Agent 走同一 `_execute_tool` 管线，诊断回灌自动生效，无需额外接线。

---

## 10. 分期落地

| 期 | 内容 | 验收 |
| --- | --- | --- |
| **P1** | `diagnostics.py` + `run_tests` trace 字段 + execution 回灌 | 人为制造运行时崩溃（如 `KeyError`），agent 在**不重新全仓 grep** 的前提下直接 `read_file` 到出错行 |
| **P2** | `DebugLoopMiddleware`（指纹计数 + 二次提示 + 三次刹车） | 构造一个无法自解的场景，第 3 次失败后 agent 停止重试并如实汇报；成功路径 token 消耗无变化 |
| **P3** | prompt 调试循环改写 + evals 新增"运行时崩溃"场景 | evals 崩溃类场景 resolved 率提升；`run --fake` 端到端仍 12/12 |
| **P4**（可选） | 前端诊断卡片、复现固化（`pin_repro`）、`_is_recovery_title` 去重键替换 | 用户能在工具卡上看到栈帧并点击跳转 |

**建议顺序**：先做 P1（纯增量、零风险、立刻见效），跑通测试后再上 P2。

---

## 11. 测试要点

- **解析层**：pytest 多失败块、嵌套异常（`During handling of the above exception`）、`ExceptionGroup`、Node `at fn (file:line:col)`、畸形输入、路径归一、业务帧过滤、截断；
- **指纹**：同异常同帧 → 同指纹；同异常不同帧 → 不同指纹；消息变化 → 指纹不变；
- **回灌**：仅失败触发、成功零影响、解析异常不影响工具结果、与语法检查段共存顺序；
- **中间件**：计数正确、跨工具共享计数、三次刹车、`debug_halt` 后不再自动重试；
- **回归**：现有 `test_run_tests.py` / `test_terminal_dev.py` / `test_code_review.py` 全绿；`_LOCK_FREE_TOOLS` 与 `_READ_ONLY_TOOLS` 不因本方案变化；
- **命令**：`pytest --basetemp=/tmp/pt -p no:cacheprovider`（沙箱下默认 tmp 目录会报 `PermissionError: EEXIST`）。

---

## 12. 实施记录（2026-09-19）

### 12.1 落地内容

P1–P3 已实施，P4（前端诊断卡片、`pin_repro`、`_is_recovery_title` 去重键替换）未实施。

| 文件 | 改动 |
| --- | --- |
| `app/tools/diagnostics.py`（新） | `Frame` / `FailureReport` / `parse_python_traceback` / `parse_pytest_short` / `parse_node_stack` / `parse_compile_errors` / `parse_failures` / `compute_fingerprint` / `format_failure_block` / `diagnose_tool_output` / `attach_traces` / `trace_payload` |
| `app/tools/adapters/run_tests.py` | `data.failures[]` 补 `trace`（仅失败时计算） |
| `app/agent/tools/execution.py` | 新增 `_command_failed()`；命令类工具失败时追加 `[诊断]` 段 |
| `app/agent/middleware/debug_loop.py`（新） | `DebugLoopMiddleware`：指纹计数 + 二次提示 + 三次刹车 |
| `app/agent/middleware/__init__.py` | 导出 `DebugLoopMiddleware` |
| `app/agent/tools/tools.py` | `_build_agent` 中间件链插入（`ToolErrorMiddleware` 之前 = 更外层） |
| `app/agent/core/context.py` | `AgentRunContext` 新增 `debug_state` / `debug_halt` |
| `app/agent/core/prompt_sections.py` | `_PROJECT_WORKFLOW` 验证段改写为「验证与调试」四步循环 |
| `tests/test_diagnostics.py`（新） | 35 项 |
| `tests/test_debug_loop.py`（新） | 11 项 |
| `tests/test_command_tools.py` | `test_run_tests_end_to_end` 补 `trace` 断言 |
| `evals/scenarios/s13_runtime_crash_nested/`（新） | 运行时崩溃场景（三层嵌套栈，修复点在调用方帧） |
| `evals/harness.py` | 修 `--rootdir` 未锚定导致的 nodeid 前缀错位（见 §12.3） |

### 12.2 与本文设计的偏差（4 处，均有实测依据）

1. **新增 `parse_pytest_short`**（§2.2 未列）。本文只描述了带 `Traceback (most recent call last):`
   头的完整栈，但 `run_tests` 用的是 `--tb=short`——实测该格式**没有**这行头，
   帧写作 `tests/test_api.py:5: in test_login`，完整栈解析器一条都抓不到。
   不补这条解析器，P1 对 `run_tests` 完全失效。同一条解析器另兼容 `--tb=long`
   （首帧 `file:line: `、末帧 `file:line: KeyError`，均无 `in func`）。
   实测两种 tb 格式对同一次失败产出**相同指纹**，刹车计数不会分裂。
2. **`_command_failed()` 取代 `not output["success"]`**（§3 的判定条件不成立）。
   实测 `terminal` 把「命令跑起来了」记为 `success=True`，非零退出码只在
   `data.exit_code`（`success=True, exit_code=2`）。只认 `success` 的话诊断回灌
   对 terminal 永不触发，而它正是排障主入口。现在两条路径都认。
3. **`is_user_code` 之外增设 `is_business`**（§2.4 只定义了前者）。
   §3 样例把 `<- 业务代码` 标在 `app/api/auth.py:88` 而没标测试帧，
   §2.3 又说指纹取「首个业务帧」——两者要求把测试文件排除出业务帧。
   否则同一个 bug 被两个测试打到会得到两个指纹，去重失效。
   `is_user_code` 仍按 §2.4 原义（测试文件算 user_code），只多一个更窄的判定。
4. **帧截断保留原始顺序**，不做「业务帧提前」（§2.1 的措辞）。
   顺序打乱会丢掉「谁调用了谁」这条最关键的信息；`_MAX_FRAMES` 不够时
   改为优先丢弃外侧的非业务帧。

另有两处小改：`FailureReport` 增 `node` 字段（pytest 段落头里的用例名，
用于把报告回挂到 `data.failures[]`，按名匹配比按序稳）；抽出
`diagnose_tool_output()` 把「解析 → 渲染」收成一个可测函数。

**P2 可选项 `jump_to="end"` 未实施**：本文 §4.2 标为可选，且它与 §8
「硬刹车后行为 = 汇报而非静默中止」冲突——直接收尾会让模型来不及汇报，
用户只看到任务中断。现改为「注入硬指令 + 置 `debug_halt`，此后不再追加提示」。

### 12.3 顺带修复：eval harness 的 rootdir 缺陷（非本方案引入）

`evals/harness.py::run_pytest` 未锚定 rootdir。pytest 的 nodeid 是相对 rootdir 算的，
而工作区落在仓库内（`evals/.runs/`）时，pytest 会向上找到
`divine-server/pytest.ini` 并把 rootdir 定成 `divine-server`，nodeid 于是变成
`evals/.runs/<...>/tests/test_x.py::test_y`，与 `config.yaml` 里写的
`tests/test_x.py::test_y` 永不相等。

后果：`check` 报「全部场景夹具有问题」，`run` 把每个场景标成 `scenario_fixture_broken`。
`pytest.ini` 的 mtime 是 **2026-09-05**，而 `evals/results/` 里最后一份成功报告是
**2026-08-30**——harness 从那时起就静默失效了。修法是给 pytest 传
`--rootdir <workspace>`。修后 `check` 13/13 通过、`run --fake` 13/13 resolved。

### 12.4 验收

- `tests/test_diagnostics.py` 35 项 + `tests/test_debug_loop.py` 11 项全绿；
- `tests/test_command_tools.py` 13 项全绿（含新增 `trace` 断言）；
- `evals.harness check` 13/13；`evals.harness run --fake` **13/13 resolved**；
- 端到端（`tests/test_diagnostics.py::test_execution_appends_diagnosis_on_command_failure`）
  证明真实 `terminal` 失败后模型收到的 content 里带 `[诊断]` + 业务帧 + 指纹。
