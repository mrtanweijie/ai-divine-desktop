# PPT 工具功能增强方案

> 背景：现有 `presentation` 工具生成的 PPT 只有纯文本排版，达不到应用效果。本文档给出诊断与分层增强方案。

## 一、现状诊断

实现链路：`tools/adapters/presentation.py`（工具 schema）→ `tools/scripts/presentation.py`（入口脚本）→ `app/ppt_themes.py`（渲染，python-pptx 1.0.2，在空白版式上程序化绘制矩形 + 文本框）。

核心短板（按感知影响排序）：

1. **零视觉素材**：所有页面 = 纯色矩形背景 + 文本框 + 少量色块。没有图片、图表、表格、图标、渐变。9 个主题（`ppt_themes.py:13-113`）本质上只是一组颜色/字体 token，版式几何完全相同，"换主题"感知差异极弱。
2. **版式只有 4 种**：default（要点）/ cards / timeline / columns。缺少目录、章节过渡页、图文两栏、金句、大数字 KPI、对比、表格页、图表页、结尾页——常规汇报 PPT 中这些版式占比一半以上。
3. **无排版自适应**：正文固定 22/18pt（`ppt_themes.py:252-258`），卡片文字固定 12pt（`:360`），文字多必然溢出或拥挤；timeline 步数 >6 时等分横线挤压变形（`:397-399`）。
4. **能力面窄**：slides schema（`adapters/presentation.py:36-62`）只有 heading/subtitle/body/points/layout，无法表达图片、数据、表格——LLM 有心也传不进来。
5. **封面单调**：纯色背景 + 竖条 + 两行字（`ppt_themes.py:147-204`），没有视觉记忆点。

项目里已有但未被 PPT 用上的能力：

| 设施 | 位置 | 说明 |
|---|---|---|
| AI 生图 | `image_generate`（MiniMax image-01 / GLM-Image） | GLM 明确擅长 PPT/海报等文字密集场景 |
| 网络图下载内嵌 | `_fetch_image_data`（`pdf_theme_manager.py:1749`） | 6s 超时、2MB 上限、base64 内嵌，PDF 旅行手册已在用 |
| 稳定占位图 | `_keyword_to_image_url`（picsum seed） | 无需 API key；缺点是与关键词相关性弱 |
| 图像处理 | Pillow 12.3.0（已安装） | 裁剪/圆角/遮罩 |
| 图表 | `generate_chart`（ECharts SVG）+ `svg_to_png` | 支持 sankey 等复杂图 |
| 原生图表/表格 | python-pptx 自带 `add_chart` / `add_table` | PowerPoint 内可二次编辑 |

## 二、增强方案

### 方案一：版式体系扩展 + 排版自适应【P0，性价比最高】

不引入任何新依赖，把"文本堆"变成"有版式语言的 PPT"。

版式从 4 种扩展到 14 种：

| layout | 用途 | 关键元素 |
|---|---|---|
| cover | 封面（强化） | 渐变背景、大标题、副标题、元信息 |
| toc | 目录 | 序号 + 标题网格 |
| section | 章节过渡页 | 大序号 + 章节标题，深色底 |
| bullets | 要点页（现 default） | 保留 |
| two_col | 图文/双栏 | 左右分栏，可嵌图片（接方案二） |
| cards | 卡片 | 保留，修字号自适应 |
| timeline | 时间轴 | 保留，修 >6 步折行（上下两排或竖向） |
| columns | 分栏 | 保留 |
| compare | 对比页 | 左右两块 vs 布局 |
| kpi | 大数字页 | 2-4 个 value+label 数字卡 |
| quote | 金句页 | 大引号 + 居中金句 |
| table | 表格页 | 原生表格，主题化表头/斑马纹 |
| chart | 图表页 | 接方案三 |
| end | 结尾页 | 感谢/联络信息 |

排版自适应（渲染前新增计算层）：

- 按字符量分档选字号（CJK 按全角估宽），要点 >40 字降档、页面总字数超阈值逐级降；
- cards/timeline 每格文字按长度在 14/12/11pt 间选择，超长加"…"；
- 所有文本框 word_wrap + 估算行数，超高自动缩字号（用估算而非 `fit_text`，后者要求字体文件）。

工作量：3-4 天。风险：低。

### 方案二：图片配图能力【P0，感知提升最大】

schema 扩展：

```json
{
  "heading": "产品架构",
  "layout": "two_col",
  "points": ["..."],
  "image": {
    "source": "https://... 或本地路径",
    "prompt": "极简科技感城市夜景鸟瞰，蓝色调",
    "provider": "glm",
    "position": "right | left | background | full",
    "caption": "图注"
  }
}
```

图片来源三级策略：

1. `source` 有值 → 直接用（URL 走 `_fetch_image_data` 同款下载逻辑；本地路径校验 workspace 内）；
2. 无 source 有 `prompt` 且用户同意配图 → 同进程复用 `image_generate` 的 provider 封装（不走子进程工具调用），GLM-Image 优先（支持指定 16:9 尺寸）；
3. 都没有 → 渐变/几何图形占位（与 PDF 旅行手册的 photo-placeholder 范式一致）。

Pillow 处理：

- 按目标框 cover-crop 到精确宽高比，避免拉伸变形；
- background/full 模式叠加深色半透明渐变遮罩，保证白字可读；
- 可选圆角（two_col 模式）。

交互与时序：沿用 PDF 侧既有范式——首轮快速出"排版完整 + 占位图"版本，随后询问"是否需要配图？"，确认后二次调用带 `images=true`。耗时可控：单张 AI 图 5-15s，单次最多自动生成 4 张（封面 + 关键页），其余保持占位。

注意：adapter `timeout=30`（`adapters/presentation.py:70`）在配图场景必须上调（参考 image_generate 的 150s），或把配图拆成独立二段调用避免单次超时。

工作量：3-4 天。

### 方案三：分层图表能力——简单图原生直绘，复杂图走 ECharts SVG 管线【P0】

图表按复杂度分两档路由：

**第一档：简单图表 → python-pptx 原生 add_chart 直绘（不依赖 generate_chart）**

- 支持类型：柱状/条形（簇状/堆积）、折线、饼图、环形、面积、雷达（python-pptx 1.0.2 内置）；
- schema：`layout: "chart"` + `chart: { engine: "native", type, title, categories[], series[{name, values[]}] }`，脚本端直接构建 CategoryChartData 渲染；
- 路由条件：类型在支持集合内、系列 ≤3 且数据点 ≤12 → native；超出则走第二档；
- 优势：PowerPoint/WPS 内双击可编辑数据（图表内嵌数据表）、矢量渲染无分辨率问题、文件更小、少一次工具调用与中间产物；
- 主题化：series 颜色由脚本直接取预设图表 palette 上色，网格线/字体用主题 token（部分样式需少量 XML 定制，可控）。

**第二档：复杂图表 → generate_chart SVG 管线（图片嵌入）**

- 适用：sankey/treemap/heatmap 等复杂类型、组合图（柱+线双轴）、大数据点图表；
- 链路：`read_file` 读 Excel → LLM 分析 → `generate_chart`（export_svg=true）产出 `charts/xxx.svg` → presentation 的 chart 版式引用该文件 → 脚本端 SVG 转 PNG（resvg）→ `add_picture` 嵌入；
- schema：slide 引用 `image: { path, caption }`（同时接受 .png/.jpg/.jpeg，顺带覆盖"插入用户自有图片"的能力子集）。

两档共用部分：

- chart 版式渲染规则：有 points（takeaway）→ 左图右文（图约 60% 宽）；无 points → 图占满内容区居中；caption 底部小字；
- 数据保真缓解：图表数据经 LLM 转写（native 写进 chart data、SVG 写进 option），大表有转抄误差风险——先读摘要/小表再取数，prompt 明确"数据必须来自 Excel 原文"；native 图表用户可在 PowerPoint 内直接改数兜底；
- 配套改造：① `svg_to_png.py` 的 `_render_with_resvg` 渲染链抽到 `svg_common.py` 三处共用；② `chart_svg.py` 尊重 `option.color`（修复前端预览与 SVG 导出配色不一致）；③ image.path 路径安全（workspace 内 + 扩展名白名单）。

可选增强（二期）：SVG+PNG 双嵌入（svgBlip + PNG fallback）保留矢量；generate_chart 加 source 文件直读聚合（LLM 只声明列映射，彻底消除转抄误差）。

表格：`layout: "table"` + `table: {columns[], rows[[]]}`，原生 `add_table`，主题化：表头 accent 底白字、隔行斑马纹、弱化边框。

工作量：native 图表 2 天 + SVG 管线 1-2 天 + 表格 1 天（native 先行，SVG 兜底可后置）。

### 方案四：现代设计预设模板（主题从"换色"到"换设计"）【P1】

现状 9 主题共享同一套版式几何，仅色板/字体不同。升级为**预设设计模板**：每个预设 = 色板 + 字体 + 装饰语言（封面构图 / 卡片样式 / 装饰元素）+ 配套图表调色板。

技术底座（python-pptx 1.0.2 全部可达成，零新依赖）：

- 线性渐变：`fill.gradient()` + `gradient_stops` + `gradient_angle`（原生支持，双 stop）；
- 半透明填充（玻璃拟态）：向 `a:srgbClr` 注入 `a:alpha` 子元素（约 5 行 XML 辅助函数）；
- 弥散光斑：多层大半径半透明圆形叠加模拟 mesh gradient；
- 硬阴影（新粗野风）：底层偏移色块矩形模拟，无需 XML；
- 点阵/细线装饰：循环绘制小圆/线段，成本低。

预设清单（首批 7 套）：

| 预设 | 封面 | 内容页 | 适用 |
|---|---|---|---|
| aurora 极光 | 深空蓝→紫线性渐变（#1E1B4B→#7C3AED）+ 右下光斑，白色大标题左对齐 | 白底 + 渐变细顶条 + 浅色玻璃卡片 | 产品发布、通用商务 |
| glass 玻璃拟态 | 浅灰蓝底（#F4F6FB）+ 半透明色块构图 | 半透明白卡片 + 细边框，靛蓝 accent | 数据汇报、SaaS |
| brutalist 新粗野 | 米白底 + 高饱和撞色块（黄/橙/蓝）+ 粗黑边框 | 黑边框卡片 + 偏移硬阴影色块，超大黑体标题 | 创意、年轻化品牌 |
| swiss 瑞士国际 | 大留白 + 网格 + 超大序号，单一红色 accent | 细分割线分栏，黑白灰 + 红 | 咨询、学术、极简 |
| mesh 渐变弥散 | 紫→蓝→青多色弥散渐变（Linear/Vercel 风），白字居中 | 极简白底 + 渐变胶囊标签 | 科技、开发者 |
| editorial 杂志 | 米白底 + 衬线大标题 + 细线框 | 分栏排版 + 首字强调，橙红 accent | 深度报告、文化内容 |
| darktech 暗黑科技 | 深色底（#0B0F1A）+ 青→紫霓虹 accent + 细网格线 | 深色卡片 + 霓虹描边，等宽字体点缀 | 技术分享、发布会 |

实现要点：

- 主题 token 结构扩展：在现有 9 色板之外增加 `style`（选择装饰 painter）、`cover_style`、渐变端色、图表 palette 数组；
- 渲染器按方案一重构为 `ppt_renderer/` 包后，每个预设实现 cover/content/cards/timeline 等版式的装饰 painter，版式骨架（坐标、自适应）全部复用；
- **与方案三联动**：每个预设自带图表 palette——原生简单图表由脚本直接按 palette 给 series 上色，SVG 复杂图表由 prompt 规则让 LLM 把 palette 写进 generate_chart 的 `option.color`，保证图表与整套设计同色系；
- 交互沿用现有 ```options 选项卡流程（同 PDF 色卡范式），每个预设给一张主题色卡展示；预设数量增多后 LLM 按场景推荐 2-3 个而非全列。

预制 .pptx 模板资产（方案五）与本方案的关系：预设先用程序化绘制实现（无资产、可随代码迭代）；待 layout 枚举稳定后再做预制模板资产包（设计上限更高、支持用户上传企业 VI），两者共用同一套版式映射。

工作量：3-4 天（与方案一新版式同步实施最划算）。

### 方案五：pptx 模板文件体系【P2，设计上限最高】

程序化绘制的上限有限。终极形态是预制精心设计的 .pptx 模板文件（母版 + 多版式 + 装饰素材），生成时 `Presentation(template.pptx)` 按版式填 placeholder：

- 内置 3-5 套高质量模板（设计工具制作，python-pptx 只负责填内容）；
- 进阶：用户上传企业 VI 模板 → 读取 slide_layouts → LLM 选择版式映射 → 填充生成；
- 这是 Gamma、Kimi PPT、WPS AI 等商业产品的主流做法。

工作量：模板制作 2-3 天/套 + 占位符映射引擎 3-5 天。依赖方案一/二的 layout 枚举稳定后实施。

### 方案六（配套）：LLM 侧生成规范

`prompt_sections.py` DOCUMENT_RULES 同步升级：

- 内容密度规范：每页要点 ≤5 条、每条 ≤2 行、总字数上限（防溢出）；
- 版式选择策略扩展到新版式全集（数据→chart、流程→timeline、对比→compare…）；
- 配图交互规则（先出占位版再询问，同 PDF travel 范式）；
- 封面/章节页/结尾页缺失时工具兜底自动生成。

### 不建议的方向

- **HTML→PPTX 转换管线**：Python 生态无成熟库，收益/成本比远低于以上方案；
- **引入新渲染依赖（matplotlib 等）**：原生 chart 已够用，无需新装包。

## 三、推荐实施路径

| 阶段 | 内容 | 工作量 | 效果 |
|---|---|---|---|
| 一期 | 方案一（版式+自适应）+ 方案三（原生简单图表 + 表格；复杂图 SVG 管线兜底）| ~1.5 周 | 无新依赖，从"文本堆"变"有版式、有图表" |
| 二期 | 方案二 AI 配图 + 方案四现代设计预设模板 + SVG 矢量双嵌入 | ~1.5 周 | 图文表齐备，设计感跃升 |
| 三期 | 方案五 pptx 模板体系 + 用户自定义模板 | 1-2 周 | 对齐商业产品形态 |

> **实施状态**：一期与方案四（现代设计预设）已于 2026-08-30 落地 —— `app/ppt_renderer/` 包
> （themes/textfit/charts/tables/layouts 五模块）承载 14 种版式、排版自适应、原生简单图表
> （add_chart，PowerPoint 内可编辑）、主题化表格、图片插入（png/jpg/svg 自动转 PNG，越界路径降级占位）、
> 结尾页自动补齐，以及 **7 套现代设计预设的装饰语言**（aurora 极光 / glass 玻璃拟态 / brutalist 新粗野 /
> swiss 瑞士 / mesh 弥散 / editorial 杂志 / darktech 暗黑科技，与 docs/PPT模板设计预览.html 对应；
> modern→aurora、roadmap→aurora、academic→editorial 映射）；
> SVG 渲染链下沉 `svg_common.py` 供 svg_to_png / presentation 共用；
> adapter schema（layout 枚举 / chart / table / image / left / right，timeout 60s）与
> DOCUMENT_RULES prompt 规则（含 7 预设风格映射表）同步更新；
> 测试见 `tests/test_presentation_render.py`（全版式 + 7 预设冒烟 + 单元），sidecar 已重新编译并做 frozen 实测。
> 二期剩余项：AI 配图、SVG 矢量双嵌入、pptx 模板文件体系（方案五，待用户模板）。

落地改动点：

- `app/tools/scripts/svg_to_png.py`：渲染链下沉到 `svg_common.py` 供共用；
- `app/chart_svg.py`：render_chart_svg 尊重 option.color；
- `app/tools/adapters/presentation.py`：schema 扩展（image/chart/table、layout 枚举）、timeout 上调；
- `app/tools/scripts/presentation.py`：版式分发、SVG→PNG 转换与兜底逻辑；
- `app/ppt_themes.py`：建议拆为 `app/ppt_renderer/` 包（themes / layouts / textfit / media 四个模块）；
- `app/agent/core/prompt_sections.py`：DOCUMENT_RULES 升级（含 Excel→图表→PPT 多工具链编排规则）。
