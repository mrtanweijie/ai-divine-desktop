# 会话历史"不见了"：尾部窗口被裁成 1 条（分页对齐塌陷）

> 编号：004 ｜ 类型：fix ｜ 日期：2026-09-14 ｜ 状态：已实施（待重建 sidecar 后在 app 内确认）
> 取证：用户报告「项目列表 ai-divine-desktop 对话内容不见了」+ 生产库只读查询 + 分页接口实测
> 关联：[../design/](../design/)（分页特性源自 `82fb43c feat: add message pagination…`）


## 1. 现象

项目 `ai-divine-desktop` 下的会话「分析项目功能」（`02a7538df3ab4a8492d6ac8641bd62f5`）打开后几乎空白，用户判断为「对话内容不见了」。

## 2. 取证：数据没丢，是接口只给 1 条

| 检查 | 结果 |
| --- | --- |
| 生产库（`~/Library/Application Support/com.ai-divine.desktop/ai_workspace.db`）该会话消息数 | **659 条**（assistant 268 / tool 362 / user 29） |
| `GET /api/sessions/{id}`（无 limit，全量） | 659 条 ✅ |
| `GET /api/sessions/{id}?limit=80`（**前端首屏用的值**） | **1 条** ❌ `has_more=true` |
| `?limit=30` | 1 条 ❌ |
| `?limit=100` | 90 条（侥幸正常） |

前端 `useSessionLoader.ts` 首屏与「加载更早」都用 `limit: 80`，所以打开会话只看到 1 条消息。

## 3. 根因：裁剪式对齐在 tool 密集会话里把整页裁掉

`app/db/history.py::load_session_page` 原逻辑：

```python
rows = ... ORDER BY m.rowid DESC LIMIT 30     # 取最新 limit 条
page = list(rows)[::-1]                       # 转升序
while page and page[0]["role"] != "user":     # 页首不是 user 就从头砍
    page.pop(0)
```

- 目的是让页面起点落在 turn 边界（顶部不留半截 turn）；
- 但**工具调用是逐条落库的独立消息**（`role='tool'`），实测该会话 362 条 tool 对 29 个 user turn —— 最新 80 条窗口里只有**末尾一条** user（rowid 12658），裁剪循环把前 79 条全砍掉，只剩 1 条；
- 上一轮 user 在 rowid 12570，距窗口起点 59 条——**只需扩窗就能覆盖**，原实现却选择"砍"。

触发条件：单个 user turn 跨度 > 前端 limit（工具密集的 agent 会话必然如此）。

## 4. 修法：向前对齐（扩窗），而不是向后裁剪

```python
page = _page_rows(...limit=limit)[::-1]
if page and page[0]["role"] != "user":
    boundary = 最近的更老 user 消息 rowid
    if boundary and page[0]["rowid"] - boundary <= MAX_PAGE_LOOKBACK:
        page = 该 user 到窗口起点之间的行 + page     # 起点对齐到 turn 边界
    # 超出回看上限（或压根没有更老 user）→ 保留未裁剪窗口：
    # 顶部半截 turn 只是观感问题，裁成 1 条等于"历史不见了"
```

- 新增 `MAX_PAGE_LOOKBACK = 200`（回看上限）与 `_page_rows()`（抽出重复的长 SELECT，支持 WHERE + 排序 + 可选 LIMIT）；
- `has_more` 仍按新的页首 rowid 计算，游标语义不变（前端用 `messages[0].id` 做 `before_id`）。

## 5. 验证

**生产库实测**（只读，`DB_PATH` 指向 app 真实库）：

| limit | 修前 | 修后 | 页首角色 |
| --- | --- | --- | --- |
| 30 | 1 条 | **89 条** | user ✅ |
| 80（前端值） | 1 条 | **89 条** | user ✅ |
| 100 | 90 条 | **189 条** | user ✅ |
| 第二页（before=首页页首，limit 80） | — | 100 条 | user ✅ |

**回归测试**（`tests/test_history_window.py` 新增 4 例）：`test_session_page_keeps_tool_heavy_tail` / `covers_requested_window` / `second_page_starts_at_boundary` / `gives_up_alignment_beyond_lookback`。
用 `git stash` 临时还原旧实现后**这 4 例全红**，恢复修复后 14 passed —— 确认是有效护栏，不是"跟着实现写的测试"。

## 6. 部署注意（重要）

运行中的后端是 **PyInstaller 二进制**（`divine-server/bin/darwin-arm64/divine-server`，2026-09-14 10:32 构建），不是源码进程。**Python 侧改动必须重建 sidecar 才会生效**：

```bash
cd divine-server && ./build-sidecar.sh        # 产出 bin/<target>/divine-server
# 再同步到 divine-app/src-tauri/binaries/（脚本已内建），重启 app
```

在重建之前，app 内仍是旧分页逻辑（打开该会话只显示 1 条）。

## 7. 遗留

1. 对齐后单页条数可能超过 `limit`（最多 +MAX_PAGE_LOOKBACK）。当前前端不假设上限，但若要严格控制单页体积，可让前端把 `limit` 调小（例如 50）或把回看上限调低。
2. `has_more` 只判断"还有更老的行"，不判断"还有更老的 **turn**"——极端情况下最后一页可能只有零星几条。未做改动。
3. 生产库里存在**两个同名「数据分析」项目**（id 不同，8-22 与 8-29 各建了一个），属于数据卫生问题，与本次无关，未处理。
