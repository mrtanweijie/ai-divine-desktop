# 006 · 简单请求也弹 PLAN_CHOICE

> 日期：2026-11-01
> 现象：用户问「人民币兑换美元汇率」，界面先弹「执行任务前是否先出一份方案？」

## 现象与取证

会话 `636016eb…`（16:26）的落库记录：

```
user      人民币兑换美元汇率
assistant (tool_calls) → fx_rates {"symbols":["USD","CNY"],"days":30}
tool      {"success":true,"source":"live","provider":"open.er-api.com",…}
assistant 当前中间价参考：1 美元 ≈ 6.671 人民币…
```

工具只调了一次，就是 `fx_rates`。而 PLAN_CHOICE 只可能由
`agent/tools/execution.py:249` 那个门发出：

```python
not ctx.plan_choice_resolved
and name not in _READ_ONLY_TOOLS
and name not in _NO_PLAN_TOOLS
and _should_ask_plan(state["messages"])
```

逐条核对：

| 条件 | 结果 |
|------|------|
| `ctx.plan_choice_resolved` | False（会话 `plan_mode` 默认 `ask`，只有 `direct`/`plan_first` 才置位；事后 DB 里是 `direct` = 用户点了「直接执行」写的） |
| `name not in _READ_ONLY_TOOLS` | **True —— `fx_rates` 不在白名单**（新工具没登记） |
| `name not in _NO_PLAN_TOOLS` | True |
| `_should_ask_plan` | 见下 |

`_should_ask_plan("人民币兑换美元汇率")` 单独跑是 **False**（无复杂关键词、长度 < 100、无分隔符）。
所以运行时它拿到的一定不是这条文本：

```python
user_messages = [m for m in messages if isinstance(m, HumanMessage)]
if not user_messages:
    return True          # ← fail-open
text = _content_text(...).strip()
if not text:
    return True          # ← fail-open
```

只要 `messages` 里取不到 `HumanMessage`（state 里是 dict、或打包后存在两份
langchain_core 导致 isinstance 失配、或内容为空），就直接判成「需要方案」。

## 根因

两个缺陷叠加，任一个单独都不会弹窗：

1. **白名单是 opt-in 的**：`_READ_ONLY_TOOLS` 没收录，工具就被当成「会写文件」，
   于是走到「先问方案」的分支。新加的纯展示/只读工具（`fx_rates`、`flight_board`、
   `render_graph`）全部中招。
2. **判据 fail-open**：`_should_ask_plan` 在「判不出来」时返回 True，
   与「宁可少打扰」的产品预期相反。

## 修法

- `core/constants.py`：`_READ_ONLY_TOOLS` 补 `fx_rates`、`flight_board`、`render_graph`。
- `core/prompts.py`：新增 `_user_texts()`，兼容 LangChain 对象 / dict / 鸭子类型
  （`.type == "human"`，覆盖跨模块副本）；`_should_ask_plan` 取不到可判读文本时
  返回 **False**（fail-closed），显式关键词（"先出方案" / "不要方案"）与复杂度打分逻辑不变。

## 验证

- `tests/test_plan_gate.py` 8 条：无消息不弹、dict 形态、鸭子类型、显式要方案/不要方案、
  复杂请求仍会弹、四个只读工具都在白名单。
- 全量后端：**1685 passed**；5 个失败均为环境性（`Missing credentials` 与
  「临时目录在 git 仓库内导致 `git` 不报错」），与本次改动无关。

## 教训

`_READ_ONLY_TOOLS` 这种**默认为"有副作用"的开关集合**，新增工具时极容易漏。
以后加工具时先问一句：它会不会写工作区 / 改会话状态？不会就必须进白名单，
并在工具的测试里断言 `name in _READ_ONLY_TOOLS`。
