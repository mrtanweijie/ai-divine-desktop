# UX HTML 设计基线

> 编号：014 ｜ 类型：design ｜ 日期：2026-09-03 ｜ 状态：已实施
> 面向**两个** HTML 产出工具：
> - `ux_html` —— UX 交互原型 / 产品界面设计稿（绑定 `ux` 意图，强制询问风格）。
> - `html_generate` —— 其余一切「产出一个 HTML 文件」的场景：分析报告、数据看板、仪表盘、
>   落地页、简历、文档网页版等（**常驻注入**，不按意图裁剪，`style` 可选）。
> 
> 两工具共用同一套 token 基座与静态校验（`ux_html.py` 的 `inject_scaffold` / `lint_html`），
> 视觉基线（token / 排版 / 间距 / 阴影）完全一致，只规范节不同：
> - `_UX_HTML_RULES`（`ux` 意图注入）——多了「必须先询问风格」与交互完整性要求；
> - `_HTML_PAGE_RULES`（`html` 意图注入）——多了图表与数据呈现规范。
> 
> 唯一事实来源是 `divine-server/app/agent/core/prompt_sections.py`；
> 本文是它的可读版本与「为什么这么定」的说明，改规范时两边要同步。


---

## 1. 根因：为什么模型生成的页面不好看

不是模型没有审美，是**约束不可执行**。改动前的视觉规范只有 5 行：

```
- 风格贴合所选风格的真实设计语言，留白充足、排版克制…
- 不使用渐变背景，不使用过重阴影；
- 圆角统一 10px，间距使用 16 的倍数；
```

三个致命问题：

| 问题 | 后果 |
|------|------|
| 全是形容词（"留白充足""排版克制"） | 模型每轮自由解读，输出方差极大，同一需求两次生成可能天差地别 |
| 禁令过严（"不使用渐变""不过重阴影"） | 把建立层次感的手段一刀切掉，成品扁平、平庸、没有焦点 |
| 数值太少（只有圆角 + 间距 2 个维度） | 字号、行高、色阶、组件尺寸、对齐全部放任自流 |

**结论**：模型缺的不是"要好看"这个目标，而是"好看 = 具体哪几个数"的映射表。
所以解法是把形容词翻译成数字。

### 三层防线

```
第 0 层  token 基座        ux_html.py::inject_scaffold  自动前置注入 :root，漏写也兜底
第 1 层  prompt 规范      _UX_HTML_RULES / _HTML_PAGE_RULES【1】-【7】
第 2 层  工具静态校验      ux_html.py::lint_html         保存后回传问题，模型自纠
第 3 层  提交前自检        【7】7 条 yes/no               生成前自己过一遍
```

`html_generate` 通过 `from app.tools.scripts.ux_html import inject_scaffold, lint_html` 复用第 0/2 层，
避免两套规范漂移。

第 0 层是底线：模型偶尔会漏写 `:root` 或把色值散落在组件里，光靠 prompt 只能降低概率。
工具在保存前把所选风格的变量层 + reset **前置**注入到 `<head>` 最前面——CSS 层叠中后定义的
同名规则胜出，所以模型自己写的 `:root` 或组件样式天然覆盖基座，**定制自由完全不受影响**；
模型漏写时基座兜底，页面不会退化成裸 HTML。附带收益是模型不必每次都输出一遍变量，省 token。

第 2 层是关键：**prompt 只能提高概率，校验回路才能保证下限**。
工具保存文件后把问题列表塞进 `message` 与新增的 `warnings` 字段，模型看到后会重写覆盖，
形成生成 → 校验 → 自纠的闭环。文件始终落盘，不阻断流程，避免工具报错打断任务。

两层的协同：lint 跑在**原始** content 上（注入前的模型输出），否则基座的色值会污染
hex 计数；且基座已注入时不再提示"未定义 :root"——基座兜住了还让模型重写属于噪音。

---

## 2. 设计基线全文

以下与 `_UX_HTML_RULES` 视觉规范段一致（prompt 中为节省 token 做了压缩表述）。

### 【1】设计 token

`ux_html` 会按所选风格**自动前置注入** `:root` 变量与基础 reset（含 `--radius-sm/md/lg`），
直接引用 `var()` 即可，无需重复定义；需要定制色值时写自己的 `:root`，后定义的覆盖基座。

变量集：
`--bg` `--surface` `--surface-2` `--border` `--border-strong`
`--text` `--text-2` `--text-3`
`--primary` `--primary-weak` `--primary-ink`
`--ok` `--warn` `--danger` 及其 `-weak` 底

| 风格 | bg / surface / surface-2 / border | text / text-2 / text-3 | primary / primary-weak |
|------|----------------------------------|------------------------|------------------------|
| Notion | `#FFFFFF` `#FFFFFF` `#F7F7F5` `#E9E9E7` | `#37352F` `#787774` `#9B9A97` | `#2383E2` `#E7F3F8` |
| Linear | `#F9F9FB` `#FFFFFF` `#F4F4F6` `#E6E6EB` | `#08090A` `#6E6D77` `#8A8F98` | `#5E6AD2` `#EEF0FD` |
| Apple | `#F5F5F7` `#FFFFFF` `#F5F5F7` `#D2D2D7` | `#1D1D1F` `#6E6E73` `#86868B` | `#0071E3` `#E8F2FD` |
| PlainText | `#FFFFFF` `#FFFFFF` `#FAFAFA` `#DDDDDD` | `#111111` `#555555` `#888888` | `#111111` `#F0F0F0` |
| Obsidian | `#FAF7F1` `#FFFDF8` `#F0EBE0` `#E5DECE` | `#3D3730` `#756D5F` `#A89F8F` | `#0E6E63` `#E1EFEB` |

**Apple 深浅同源**（官方深色语言）：深色层定义在 `_DARK_TOKENS["Apple"]`，取值依据 Apple 官网/系统
深色规范——纯黑底 `#000000`、灰卡分层 `#1D1D1F`/`#2C2C2E`、正文 `#F5F5F7`、次要 `#86868B`、
链接蓝 `#2997FF`（官方深色链接色，黑底上 6.96:1）、语义色用 iOS 系统深色变体
ok `#30D158` / warn `#FF9F0A` / danger `#FF453A`。注意 `--primary-ink` 用深墨 `#04121F`：
`#2997FF` 上白字仅 3.02:1 不达标，深墨 6.27:1。

**Obsidian 深浅同源**（暖棕·冷锚 / 暖白纸张）：浅色为默认层，深色层定义在 `_DARK_TOKENS["Obsidian"]`，
经 `@media(prefers-color-scheme:dark)` 注入并随系统自动切换，模型零额外代码；media query 不影响
specificity，模型后写的 `:root` 仍可整体覆盖（想固定深/浅时自写即可）。深色层：
bg `#262322` surface `#2E2A28` surface-2 `#38332F` border `#3E3833` ｜ text `#CFC7BD` text-2 `#948D83`
text-3 `#7E7669` ｜ primary `#6DB3A3` primary-weak `#28423C` primary-ink `#10312B`（浅青上放深墨而非白字）。
标题色相谱（按需自写、不属基座公共变量）：浅 `#1D345C→#52377A→#0E6E63→#B8445A→#8A5E17`；
深 `#4F74AF→#8567BD→#4E9A8A→#D98A99→#C99B5E`。色相谱仅限标题层级，正文与组件禁止挪用；
H4/H5 字号小，必须用上述修正值保证 ≥4.5:1。

语义色：Notion/Linear/Apple/PlainText 四套通用（前主色后浅底）ok `#0F7B6C`/`#DDF2ED`、
warn `#CB912F`/`#FBF3DB`、danger `#D64545`/`#FBE9E9`；Obsidian 用自己的
ok `#4A704F`/`#E6EFE5`、warn `#8A5E17`/`#F5EBD6`、danger `#B8445A`/`#F9E6E9`（随基座注入）。
`--primary-ink` 浅色层统一 `#FFFFFF`；Obsidian 深色层为深墨。

**可访问性实测（WCAG AA）**：正文深 9.33:1 / 浅 10.99:1（超 AAA）；锚点 6.41 / 5.73。
修正记录：深 text-3 `#6E675E`→`#7E7669`（2.80→3.48，仅限禁用态/装饰用途）；
浅 text-2 `#857D70`→`#756D5F`（3.80→4.78）；浅 warn/danger 与标题四/五级共用修正值
`#8A5E17`（5.32）/`#B8445A`（4.89）；深标题四级 `#C0765E`→`#D98A99`（4.45→5.98，
同时修复浅玫红/深砖红的色相漂移，回到「同色相提亮」原则）。
另：中文禁用合成斜体（汉字无真斜体，强调用颜色+字重替代），已入反模式黑名单。

**主色预算**：只出现在主按钮 / 选中态 / 关键链接 / 图表主序列，全页不超过 3 类用途。
其余层级一律靠灰阶与留白区分。

### 【2】排版阶梯

只允许 6 档，页面内不得出现第 7 种字号。

| 角色 | 字号 / 字重 / 行高 / 字距 |
|------|--------------------------|
| H1 | 32 / 600 / 1.25 / -0.02em |
| H2 | 24 / 600 / 1.3 |
| H3 | 18 / 600 / 1.4 |
| 小标题 | 15 / 600 / 1.5 |
| 正文 | 14 / 400 / **1.7** |
| 辅助 | 12 / 400 / 1.6 |

中文不小于 12px；正文行高 ≥1.7（中文方块字密度高，1.5 会糊成一片）；
数字加 `font-variant-numeric: tabular-nums`；正文列宽 680–760px（单行 ≤40 汉字）。

### 【3】间距与形状

- 间距 4px 基准，只取 `4/8/12/16/24/32/48/64`，禁止 7px、13px 这类手调值
- 圆角：小控件 6、卡片 12、大容器 16（Apple 用 8/16/20），胶囊头像 `999px`/`50%`；全页圆角档位 ≤3 种
- 阴影只两档：
  - `card` = `0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.06)`
  - `float` = `0 4px 12px rgba(16,24,40,.08), 0 12px 32px rgba(16,24,40,.08)`
- 边框统一 `1px var(--border)`，禁止 ≥2px 描边、大面积高饱和渐变、发光与 `text-shadow`

### 【4】布局骨架

- 容器 `max-width: 1200px` 居中，左右 padding 24（窄屏 16）
- 后台/多模块：固定侧栏 240px + 内容区自适应，内容区内部再限宽；顶栏高 56px 且元素垂直居中
- 文档/落地页：单列居中，正文列宽 680–760px
- 多列一律 CSS Grid、gap 16 或 24，禁止 float 与绝对定位堆砌
- 首屏必须有明确视觉焦点，不要一上来就等分三栏
- 窄屏侧栏收为抽屉，禁止横向滚动

### 【5】组件指标

| 组件 | 指标 |
|------|------|
| 按钮 | 高 36（紧凑 32）/ padding `0 14` / 圆角 8 / 14px·500；主按钮实心 `--primary` + `#fff`，次级 `--surface` 底 + 1px 边，危险按钮只做 `--danger` 描边与文字（不做实心红块）；hover 用底色偏移（主色加深约 6% 或填 `--surface-2`），禁止加粗边框或加 outline 造成位移；内嵌图标 16px、gap 6px、整体垂直居中 |
| 输入框 | 高 36 / padding `0 12` / 圆角 8 / 1px 边；focus 边框转 `--primary` 并加 3px 主色 12% 外环；错误态转 `--danger` 并给 12px 行内提示 |
| 卡片 | padding 20–24 / 圆角 12 / 1px 边 + card 阴影；hover `translateY(-1px)`，过渡 150–250ms ease |
| 表格 | 行高 44 / 水平 padding 16；表头 12/500/`--text-2`/底部 1px `--border-strong`；斑马纹 `--surface-2`；数字列右对齐 + tabular-nums；无数据走空状态而非空表 |
| chip | 高 22 / padding `0 8` / 12px / 圆角 6 / 底 `--primary-weak` 字 `--primary`；语义标签换对应 `--*-weak` 底 |
| 空状态 | 48px 内联 SVG(`--text-3`) + 15/600 标题 + 13px `--text-2` 说明 + 一个主按钮，纵向居中 |

### 【6】反模式黑名单

命中任意一条即不合格：

- 整页纯白 + 满屏灰细线表格（Excel 感）
- 主色之外第二种强调色抢戏、全页 4 种以上互不相干的颜色
- 高饱和渐变 / 霓虹色 / 发光 shadow / text-shadow
- 元素贴边（卡片间无 gap、文字顶到边缘、内容挤页脚）
- 全页同字号同灰度、看不出层级
- 中文 <12px 或行高 <1.5
- 图标与文字基线不齐、按钮文字不居中、多列宽窄不一
- **用 emoji 充当 UI 图标**——跨平台渲染不一致、颜色与对齐失控，Tab/导航/按钮图标一律内联 SVG
  （24×24 viewBox、stroke 1.5–2、currentColor）；正文内容里的 emoji 属内容本身，不受此限
- 残留 `lorem ipsum` / "示例文本" / "待补充" / `{{}}` 占位
- hover 只改 outline 或加粗边框，导致周边跳动

### 【7】提交前自检

1. 色值走 token（自有 `:root` 或基座注入）且组件无硬编码 hex？
2. 字号层级一眼可辨？
3. 间距全为 4 的倍数？
4. 圆角 ≤3 种、阴影 ≤2 档？
5. 有明确视觉焦点而非等分堆砌？
6. 可点元素都有 hover / focus-visible / 禁用态？
7. 截图缩到 30% 或黑白化后，主次关系还成立？

### 【8】移动端 App 原型分支（2026-09-04 新增）

桌面基线（6 档字号、4px 间距、1200px 容器）套在手机 App 原型上会产出「桌面感的 App」——
小红书原型实战暴露的系统性错配。需求为手机 App 时切换移动端基线，`ux_html` 传 `canvas="mobile"`：

- **画布**：深色中性背景 + 居中手机画布（390 逻辑分辨率、圆角外壳、状态栏 + Home 指示条），触摸目标 ≥44px
- **图标**：一律内联 SVG（24×24 viewBox、stroke 1.5–2、currentColor），Tab 栏/导航/功能入口
  禁止 emoji 充当图标（emoji 是彩色字形：颜色、描边、对齐全部失控且跨平台不一致）；
  笔记正文等内容里的 emoji 属内容本身，可保留
- **字号**：核心阶梯 28/20/17/15/13/11（行高 1.4–1.6），全页 ≤10 种，禁止 0.5px 值
- **间距**：偶数档 4/6/8/10/12/16/20/24，禁止奇数手调值
- **封面色块**：≤10 个预设渐变轮换
- **品牌原生风**（如小红书）：style=Custom + style_note 记录品牌色 + 自写完整 `:root`

lint 对应放宽（`lint_html(mobile=True)`）：字号上限 10、间距只禁奇数、色值上限 30。
桌面/移动是**显式参数切换**而非自动检测——检测特征（viewport 等）不可靠，宁可让模型多传一个参数。

### 【9】行业感知层（2026-09-04 新增）

完整版见《移动端 App UI 设计规范》手册（`docs/移动端App_UI设计规范.html`）。prompt 层压缩注入 9 行业
mini token：社交内容 / 电商零售 / 金融支付 / 效率工具 / 生活出行 / 健康运动 / 教育学习 / 媒体娱乐 /
企业 B 端，每行业一行（色彩基调 + 排印侧重 + 组件策略 + 反模式）。

- **识别靠模型语义判断**，不做关键词匹配——「记账/钱包/基金」都是金融，关键词表穷举不完
- **作用于内容组件策略与自定义 `:root`**；用户选了具名风格（Apple 等）时风格优先，行业气质叠加
  （金融的金额 tabular 排印在任何风格下都成立）
- 不动 token 基座（基座是风格级，行业是气质层）；lint 不加行业参数

---

## 3. 为什么这么定

| 决策 | 理由 |
|------|------|
| 灰阶分 3 级而不是 2 级 | 2 级（黑/灰）撑不起"标题—正文—辅助"三层结构，模型会退回用颜色区分，导致花 |
| 主色限 3 类用途 | 模型最常见的失控就是到处刷主色。限定预算后，层次被迫用灰阶和留白做，反而高级 |
| 4px 基准而非原规范的 16px | 16 的倍数太粗，按钮 padding、图标 gap 这些小尺度无法表达，模型只能自己编数值 |
| 阴影只 2 档 | 层级靠"面 + 边 + 阴影"三件套表达，档位一多就脏 |
| 圆角 ≤3 种 | 圆角不一致是"手工感"最大来源，比配色错误更伤观感 |
| 正文行高 1.7 | 中文没有西文的下伸部，同样行高视觉更挤；1.5 在中文下会粘连 |
| 校验器宁可漏报不可误报 | 误报会让模型反复重写空耗轮次，比漏掉一个间距破档的代价大得多 |
| 硬伤与美观信号分级 | 白屏类问题必须修，美观信号只是提示；混在一起会让模型抓不住重点 |

---

## 4. 改动位置

| 想改什么 | 改哪里 |
|----------|--------|
| 视觉规范数值 | `app/agent/core/prompt_sections.py` → `_UX_HTML_RULES`（UX 原型）/ `_HTML_PAGE_RULES`（通用页面）的【1】-【7】 |
| 各风格 token 取值 | `app/tools/scripts/ux_html.py` → `_TOKENS`；深浅同源风格的深色层在 `_DARK_TOKENS`（改完记得同步两个 prompt 节里的速查表） |
| 基础 reset | `app/tools/scripts/ux_html.py` → `_RESET` |
| 静态校验规则 | `app/tools/scripts/ux_html.py` → `lint_html()` 与 `_HARD_FAILS` |
| html_generate 工具脚本 | `app/tools/scripts/html_generate.py`（复用 ux_html 的基座与校验） |
| 风格列表 / 工具参数 | `app/tools/adapters/ux_html.py` + `scripts/ux_html.py` 的 `ALLOWED_STYLES`；`adapters/html_generate.py` |
| 意图接线 | `app/agent/intent/intent.py` → `_INTENT_KEYWORDS["html"]` / `CONDITIONAL_SECTIONS["html"]` / `_INTENT_ORDER` / `_TOOL_TO_INTENT` |
| 常驻/裁剪 | `app/agent/tools/tools.py` → `_CONTENT_TOOLS`（html_generate 不在其中 → 常驻；ux_html 在其中 → 按 ux 意图裁剪） |

改 token 时 `tests/test_ux_html.py` 的 `test_prompt_swatch_matches_injected_tokens` 会拦住
prompt 速查表与 `_TOKENS` 的漂移——这种漂移不会报错，只表现为"模型拿到的色值和它以为的不一样"。

**注意**：两个规范节都是**条件注入**——`_UX_HTML_RULES` 只在 `ux` 意图命中时进 system prompt，
`_HTML_PAGE_RULES` 只在 `html` 意图命中时注入（见 `app/agent/intent/intent.py` 的
`CONDITIONAL_SECTIONS`），所以扩充它们的 token 成本只发生在真正生成 HTML 的轮次，不会拖累日常对话。
但 `html_generate` **工具本身常驻**（不在 `_CONTENT_TOOLS`），意图漏判时工具仍在，只是少了详细规范节——
这正是与 ux_html 的关键区别：ux_html 靠「先问风格」锁定路径，html_generate 靠「工具常驻」兜底。

当前长度约 3980 字符（≈2.7k token），改动前约 1500 字符。

---

## 5. 已知边界 / 后续可选

- **html_generate 常驻、规范节条件注入**：工具描述已说清「保存完整 HTML 页面」，模型常驻可见；
  详细规范节只在 `html` 意图命中时注入。若用户消息不含「html/网页/单页/看板/落地页」等信号，
  规范节不注入——但工具仍在，不会退回 write_file 裸写。
- **CDN 策略（2026-09-03 放宽）**：图表默认内联 SVG/canvas（隐私、离线可用）；报告/看板需要
  复杂图表（K 线/雷达/散点/交互）时，模型会询问用户是否启用 ECharts 并列出优点，用户同意后
  用国内可访问的 CDN（BootCDN `cdn.bootcdn.net` / staticfile `cdn.staticfile.org`）。
  lint 对 Google Fonts（被墙）与 jsdelivr/unpkg/cdnjs（国内不稳定）给软提示，
  localStorage/sessionStorage/cookie 仍作硬伤（预览 iframe 无 same-origin，碰了必崩）。
- **CSS 基座（已做，见第 0 层）**：token 层已落地，`_TOKENS` 定义在 `ux_html.py` 内而非外部
  `.css` 文件——本脚本在 PyInstaller frozen 环境下经 `--run-script` 由子进程执行，读外部资源
  路径不可靠。实测：注入点在模型 `<style>` 之前，模型自定义 `:root` 覆盖生效（用例 2 验证）。
  未做的是**组件级基座**（`.btn` / `.card` / `.chip` 等预置类名），那会明显收窄模型的
  结构自由度，收益不确定，暂不引入。
- **PDF / PPT 未复用**：`docgen/` 走的是固定模板，质量由模板决定，不经过模型，
  与本基线无冲突；若要统一语言，可把【1】【2】【3】抽成共享常量。
- **无视觉回归验证**：目前靠人工看预览（`../../templates/002-ux-html-baseline-preview-20260903.html`）。
  若要自动化，可用 headless 截图 + 规则比对，但成本高，收益待评估。
- **测试覆盖**：`tests/test_ux_html.py`（21 个用例）覆盖基座注入与静态校验，
  全部为纯字符串测试、不依赖 `tmp_path`。已做突变验证：改坏主色 / 放开告警上限 /
  挪动注入位置，三种突变分别被 2 / 1 / 3 个用例抓到，确认测试非空转。
  CDN 放宽后覆盖 Google Fonts 被墙提示、国外 CDN 不稳定提示、国内 CDN（BootCDN/staticfile）
  零告警、localStorage 仍为硬伤。
  `tests/test_intent.py` 新增 4 个用例锁住 html 意图路由：html 关键词命中、html_generate 常驻
  （不在 `_CONTENT_TOOLS`）、`_TOOL_TO_INTENT` 回补、`_HTML_PAGE_RULES` 条件注入。
