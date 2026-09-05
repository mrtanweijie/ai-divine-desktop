# PPT 空页修复方案（cards/kpi/quote 内容丢失 + path 目录嵌套）

> 编号：001 ｜ 类型：fix ｜ 日期：2026-09-06 ｜ 状态：已实施
> 取证来源：用户报告的 3 个真实产物 + `tool_runs` 表中模型原始输入（桌面端 DB）
> 关联：[../design/007-ppt-tool-20260830.md](../design/007-ppt-tool-20260830.md)（历史增强方案）、[../design/017-office-edit-closed-loop-20260906.md](../design/017-office-edit-closed-loop-20260906.md)


## 1. 现象

生成的 PPT 大量页面只有标题、正文全空。复现文件（workspace 实测）：

| 文件 | 页数 | 空页分布 |
| --- | --- | --- |
| 霸王茶姬商业模式深度拆解（darktech，09-01） | 16 | kpi 页、cards 页、quote 页正文全空；bullets/compare 页正常 |
| 霸王茶姬商业模式深度拆解（editorial，09-01） | 16 | 同上——与主题无关，p04/p06/p10/p13/p15 空 |
| 智谱_vs_MiniMax_深度对比（darktech，08-30） | 19 | 全篇仅少量文字，多数页正文缺失 |

产物路径还出现目录嵌套异常：`presentations/霸王茶姬商业模式深度拆解_darktech.pptx/霸王茶姬商业模式深度拆解.pptx`——一个以 `.pptx` 结尾的**目录**里套着真正的文件；且 darktech/editorial 两个版本的 `download_url` 与 `file_name` 完全相同（`/files/presentations/霸王茶姬商业模式深度拆解.pptx`），下载/预览指向不明。

## 2. 取证：模型输入 vs 渲染产物逐页对账

`tool_runs`（`started_at=2026-09-01T03:18:24`，darktech 版）里存有模型完整输入。模型给的数据**是完整且高质量的**，例如：

```jsonc
// slide2 —— 渲染后 kpi 页正文全空
{"layout": "kpi", "title": "五年财务跃迁（2021-2024）",
 "items": [{"label": "GMV", "value": "295亿", "desc": "2024年，同比+173%"},
           {"label": "营业收入", "value": "124亿", "desc": "2024年，净利25.15亿"}, …共6项]}

// slide4 —— 渲染后 cards 页正文全空
{"layout": "cards", "title": "品类重构：绕开水果茶红海",
 "items": [{"title": "品类减法", "desc": "舍弃高损耗水果，回归茶叶+鲜奶本质"}, …共4项]}

// slide13 —— 渲染后金句正文丢失
{"layout": "quote", "quote": "健康的增长，比高速的增长更重要。", "subtitle": "霸王茶姬的商业启示", …}
```

产物侧字符数对账（editorial 版，python-pptx 实测）精确吻合"兜底文案"假设：

| 页 | 版式 | 页面总字符 | 构成 | 结论 |
| --- | --- | --- | --- | --- |
| p04 | kpi | 41 | 页码2 + 标题12×2 + `--`(2) + `待补充`(3) + PART 文案 | 渲染了 1 张兜底卡 `--|待补充`，6 项 KPI 数据全部丢失 |
| p06 | cards | 30 | 页码2 + 标题12×2 + `暂无内容`(4) | 渲染了 1 张兜底卡"暂无内容"，4 张卡片全部丢失 |
| p12 | bullets | 101 | 页码 + 标题 + 4 条要点 | 正常——模型恰好发了 `points` 字符串数组 |
| p07/p09 | compare | 68 | 左右两组要点 | 正常——模型发了 `left/right.points` |
| p15 | quote | 13 | 引号 + 页码等 | `quote` 键整句丢失，只渲染了装饰引号 |

## 3. 根因

### 3.1 主因：版式内容键的"窄契约"，模型偏差被静默吞掉

渲染器每个版式各自只读一个窄键（`app/docgen/ppt/renderer/layouts.py`）：

| 版式 | 实际读取 | 代码位置 | 模型实际发送 | 结果 |
| --- | --- | --- | --- | --- |
| cards | `item["points"]`（字符串数组，`"标题\|描述"` 竖线分隔） | `layouts.py:755-757` | `items: [{title, desc}]` | `points` 为空 → 兜底渲染 1 张"暂无内容" |
| kpi | `item["points"]`（`"数值\|标签\|说明"`） | `layouts.py:967-969` | `items: [{label, value, desc}]` | 兜底渲染 1 张 `--\|待补充` |
| quote | `item["heading"] or item["body"]` | `layouts.py:1010` | `quote: "…"` | 金句正文键无人读取，整句丢失 |
| timeline | `item["points"]` | `layouts.py:807+` | 历史 run（08-30）曾发 `events: [...]` | 同样会丢 |

模型为什么发结构化 `items`：

1. adapter 的 JSON Schema（`app/tools/adapters/presentation.py`）**没有定义** `items`/`quote`/`note` 属性，slides 条目也未设 `additionalProperties` 限制——模型自由发挥不受约束；
2. `prompt_sections.py:255-257` 的文字指引教的契约是对的（"卡片条目可用 '标题|描述'、kpi 条目 '数值|标签|同比'"），但 **prose 指引对模型的约束力弱于"layout 名字的语义暗示"**——模型看到 `kpi`/`cards`，按通用先验输出结构化对象数组是最自然的选择；
3. 脚本（`app/tools/scripts/presentation.py`）把 slides **原样透传**给渲染器，无归一化层、无校验；渲染器取不到 `points` 时用"暂无内容"兜底，工具仍返回 `success: true`——**失败被静默掩盖**，16 页里 7 页空也报"PPT 生成完成"。

### 3.2 次因一：`path` 语义歧义 → 目录嵌套

schema 说 `path` 是"保存**目录**"（`adapters/presentation.py`），但模型把它当文件路径传了 `presentations/霸王茶姬商业模式深度拆解_darktech.pptx`。脚本 `_resolve_inside` 解析后直接 `output_dir.mkdir(parents=True)`（`scripts/presentation.py:99-107`）——把 `.pptx` 结尾的字符串当目录建了，真实文件再嵌进去。

### 3.3 次因二：`download_url` 是拼接的理想路径，不反映实际产物

返回的 `download_url: /files/presentations/霸王茶姬商业模式深度拆解.pptx` 与实际嵌套路径不符；两个主题版本的产物 `file_name` 相同导致 URL 冲突，前端下载/预览可能 404 或指向旧文件。

### 3.4 附带：`note`（演讲备注）键无人支持

模型多页发送 `note` 字段，渲染器无 `notes_slide` 支持，schema 也未声明——全部静默丢弃（影响小，一并处理）。

## 4. 修复方案

### 4.1 P0-1：新增 slides 归一化层（治本，单一入口）

新文件 `app/docgen/ppt/normalize.py`，`presentation.py` 脚本在调用渲染器前逐页过 `normalize_slide(item)`。原则：**宽进窄出**——渲染器 14 个版式的窄键逻辑一行不动（已有测试覆盖），归一化层把模型的一切自然表达收敛到窄键：

```python
def normalize_slide(item: dict) -> dict:
    # 1) 标题别名: title → heading（渲染器已兼容 title，保留）
    # 2) 正文别名: body/content 按行拆 → points；bullets → points
    # 3) 结构化 items → points 字符串（按 layout 语境智能展开）:
    #    cards:    {title|heading|name, desc|body|text} → "title|desc"
    #              {label, value}                    → "value|label"
    #    kpi:      {value|label, desc|delta}         → "value|label|desc"
    #    timeline: events/milestones/items {date|time|title, desc|text} → "date|desc"
    #    columns:  items[{title, points}]             → cols 结构
    # 4) quote:  item["quote"] → heading（渲染器读 heading/body）
    # 5) compare: left/right 内兼容 bullets/items 键 → points
    # 6) 返回 (normalized, warnings)——归一化过程中发现的丢弃键/空内容记入 warnings
```

键别名清单以 **tool_runs 历史真实输入**为准（已观测：`items`/`cards`/`events`/`bullets`/`cols`/`desc`/`note`/`quote`/`meta`），后续随观测扩充。

### 4.2 P0-2：path 防御 + download_url 修正（scripts/presentation.py）

- `raw_path` 若以 `.pptx`/`.ppt` 结尾：剥离文件名，取父目录为 output_dir，文件名部分仅在 `title` 缺省时用作标题，并记 warning——schema 文案同步改为"保存**目录**（不要带文件名，文件名自动生成）"；
- `download_url` 从**实际 output_path 相对 workspace** 派生，不再拼接理想路径；`file_name` 撞名时追加主题后缀（`标题_darktech.pptx`），消除多版本 URL 冲突。

### 4.3 P1：生成后 QA 门禁（对齐 PDF 管线的 `docgen/pdf/renderer/qa.py` 先例）

新文件 `app/docgen/ppt/qa.py`，渲染完成后用 python-pptx 重开产物逐页体检：

- 统计每页文本字符量与内容形状数；cover/section/end 之外的单页字符量 < 20 判"空页"；
- 空页清单写入 result `warnings`（"第 4/6/10/13 页内容缺失"），空页率 > 30% 时 `message` 显式降级提示"部分页面内容缺失，建议重新生成"，不再无脑报"PPT 生成完成"；
- 兜底文案（"暂无内容"/"--|待补充"）触发时同步计入 warnings——它应被视为异常信号而非正常输出。

### 4.4 P2：schema 收编 items/quote/note 为一等公民

与其堵（`additionalProperties: false` 会让模型输出被 args_schema 校验拒绝、触发无谓重试），不如疏：

- schema 显式定义 `items`（对象数组，键 `title/desc/label/value`）、`quote`、`note` 属性，描述指向"与 points 二选一"；
- `note` 落地 speaker notes（python-pptx `notes_slide.notes_text_frame`），或从描述中移除避免模型白写；
- 归一化层（4.1）保证双轨输入（points 字符串数组 / items 结构化数组）殊途同归。

## 5. 测试计划

| 测试 | 内容 |
| --- | --- |
| **fixture 回归（最关键）** | 从 tool_runs 提取霸王茶姬 13 页真实输入存 `tests/fixtures/ppt_chagee_input.json`，断言归一化后每页 points 非空、quote 文本保留、kpi 6 项完整——直接复现本次事故的回归测试 |
| `tests/test_ppt_normalize.py` | 各键别名映射（items/events/bullets/quote/left.right）、嵌套结构、非法输入不抛异常 |
| `tests/test_presentation_script.py` | path 以 `.pptx` 结尾剥离；download_url 从实际路径派生；file_name 撞名加后缀 |
| `tests/test_ppt_qa.py` | 构造含空页产物，断言 warnings 命中与 message 降级 |

## 6. 影响面（对现有链路）

- **渲染器零改动**：`layouts.py` 14 个版式的窄键读取不动，现有渲染测试不破；
- **脚本单点改动**：`presentation.py`（206 行）加归一化调用与 path 防御；
- **schema 增量属性**：向后兼容——旧格式（points 竖线串）继续工作，新格式（items 结构化）被正确消费；
- **前端零改动**：warnings 走现有工具结果展示通道。

## 7. 分期与工作量

| 期 | 内容 | 工作量 |
| --- | --- | --- |
| 一（P0） | normalize.py + path/download_url 修复 + fixture 回归测试 | 1.5–2 天 |
| 二（P1） | ppt qa.py 空页检测 + message 降级 | 1 天 |
| 三（P2） | schema 收编 items/quote/note + speaker notes 落地 | 0.5 天 |

## 8. 经验教训（写入约定）

工具输入契约不能只靠 prompt prose 约束模型——**schema 未声明的键 + 渲染器窄键读取 + 静默兜底**三者叠加，等于把模型的合理偏差变成静默内容丢失。新工具（含 office-edit 闭环的三个编辑工具）设计时统一要求：① 归一化层收编别名键；② 结果 JSON 携带 warnings；③ 内容类产物渲染后做体积/完整性自检。
