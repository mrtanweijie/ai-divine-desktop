# 007 · fx_rates 面板「执行完成但没有图」

> 日期：2026-11-01
> 现象：问「人民币兑换美元汇率」，工具卡显示 `FX_RATES 执行完成`，正文还写着「上方面板已展开近 30 天走势」，但界面上没有图。

## 取证

工具结果里确实带了 `a2uiMessages`（三条，`surfaceId=fx-board`），
但 `execution.py` 的发事件分支写死：

```python
if name == "render_ui" and output.get("success"):
    a2ui_payload = _take_a2ui_payload(...)
    writer(a2ui_payload)
```

`fx_rates` 命不中，消息被**静默丢弃**：面板从未下发，模型却以为已经画了。

同名的硬编码还有两处，一并露出来：

| 位置 | 原写法 | 后果 |
|------|--------|------|
| `tools/execution.py:1131` | `name == "render_ui"` | 不发 `event: a2ui` |
| `tools/tools.py:168` | `name == "render_ui"` | 总开关关闭时只下线 render_ui，其余面板工具仍可见 |
| `state/persistence.py:51` | `name != "render_ui"` | 回合收尾不重建面板 → 重放/刷新后也没有 |

## 修法

新增唯一判据 `core.constants.A2UI_TOOL_NAMES = ("render_ui", "fx_rates", "flight_board")`，
三处共用（与 `A2UI_INTENTS` 的「单一真源」做法一致）。

落库重建按工具分别处理，因为**入参语义不同**：

- `render_ui`：参数本身就是 IR → 重跑 `validate_ui_surface(extract_surface(args))`；
- `flight_board`：参数是「条件 + 报价行」，面板由 `prepare()` 纯函数重建
  （为此把 `run` 里的构建逻辑抽成 `prepare()` / `surface_from_args()`，实时与回放共用一份）；
- `fx_rates`：**不落库**。折线依赖联网拿到的日线序列，离线重建只能出空图，
  宁可不显示，也不落一块骗人的空面板（文件内已注明）。

## 验证

- `A2UI_TOOL_NAMES` 断言三件套齐全；
- `_collect_ui_surfaces` 能从 `flight_board` 的 args 重建出 18 组件的面板并通过校验；
- `fx_rates` 明确返回空（已知限制，有测试钉住，避免以后被误判成 bug 又改坏）；
- 相关测试 **135 passed**。

## 教训

面板能力有三段链路：**产消息 → 发事件 → 落库**。三段各自写死工具名，
新增面板工具时必然漏一段，而且**漏了是静默的**（模型还照常宣称"面板已呈现"）。
凡是「按工具名分流」的地方，都应该收敛成一个常量，并在测试里断言集合内容。

---

## 第二轮：SSE 里有图，回合结束就消失

修完发事件后现象变了：流式过程中能看到图，`done` 一到就没了。

查会话 `636016eb…` 的落库：20 条消息、6 次 `tool_calls`，
`message_parts` 里 **`ui_surface` 一条都没有**（只有 think / tool_calls / tool_result）。

机制很直接：流式阶段的面板活在前端内存里（`event: a2ui` 建立 live surface），
`done` 会**用服务端返回的消息整段覆盖本地状态**；服务端消息里没有 `ui_surface` part，
面板就被抹掉了。所以问题不在渲染，而在**没落库**。

### 为什么 `fx_rates` 落不了库

`render_ui` 的面板能从 `tool_calls.args` 重跑校验还原；`flight_board` 的入参是
「条件 + 报价行」，也能用纯函数重建。但 `fx_rates` 的入参只有 `symbols` / `days`，
**折线数据来自联网**——收尾时再拉一次既慢又可能失败。

### 修法

新增 `app/agent/state/surface_cache.py`：发事件的同时把 `data.uiSurface` 按 `call_id`
存进进程内 LRU（上限 128）；回合收尾 `_collect_ui_surfaces` 按 `call_id` 取回、重跑校验后落库。

两个细节：

* `runtime.tool_call_id` 在个别打包/子图场景可能与 AIMessage 里的 id 对不上，
  因此额外记录「每个工具最后一次的面板」，精确匹配落空时兜底——宁可复用最近一块，
  也不要出现「看到图、结束后没了」；
* sidecar 重启后快照丢失 → 那一轮的面板不再补进历史。这是可接受的降级，
  因为面板的价值主要在「本轮可见 + 可交互」。

