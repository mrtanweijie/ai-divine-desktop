# 023 · PDF 论文/报告四套页式模板接入（2026-09-13）

> 编号：023 ｜ 类型：design ｜ 日期：2026-09-13 ｜ 状态：已实施
> 前置：008 review-pdf-template-ui-audit（四套模板的 UI 审计与优化）

---

## 1. 背景与目标

`docs/templates/011–014` 提供了四套新的 PDF 版式样张：学术报告（学院蓝）、论文投稿（期刊黑白）、数据分析报告（券商研报风）、研究报告（咨询白皮书风）。此前它们只是**设计样张**——docgen 管线不消费，用户无法通过工具生成。

本方案把四套模板接入 PDF 工具，使其成为可选的文档样式。

**目标**

1. 四套模板成为 `pdf_generate` 可选配方，用户按文档类型即可生成对应版式；
2. 生成的内容与模板的页面结构、CSS 类名严格对齐（不漏页、不自创类名、图表编号与刻度等排版契约成立）；
3. 不破坏既有配方（report / business / travel / resume 等）的行为。

**非目标**：不引入新的渲染引擎；不改变 markdown 类配方的生成方式；不为四套模板做可视化编辑器。

---

## 2. 为什么复用 travel 管线而不是新建

四套模板与旅行手册模板**同构**：都是一个 HTML 文件，内含 `<style>` 与一串 `<div class="page">` 页片段，靠占位符标注待填内容。travel 管线已经解决了这条链路的全部问题：

| 环节 | travel 已有能力 | 四套模板复用情况 |
| --- | --- | --- |
| CSS 获取 | 从模板 `<style>` 提取 | 直接复用（把 `_travel_css` 泛化为 `_html_template_css`） |
| 结构骨架 | `travel_template_skeleton` 抽取页面结构喂给 LLM | 新增 `html_template_skeleton` 分派：travel 用原筛选逻辑，四套用「保留全部页」 |
| 内容生成 | `content_format="html"` + 骨架提示词 | 新增 `PageTemplateRecipe` 基类承载提示词模板 |
| 文档组装 | `build_travel_html_document` 拼 CSS + body | 泛化为 `build_html_template_document` |
| 渲染 | `render_html_to_pdf`（WeasyPrint） | 直接复用 |

因此改动集中在「注册 + 分派 + 提示词」，没有新增渲染路径。

---

## 3. 与 travel 的三点关键差异

### 3.1 模板自带封面（`own_cover`）

travel 主题的封面由系统按 `cover_data` 另造（`build_cover_html`）。四套模板的封面是模板的一部分——里面有机构名、作者信息表、KPI 指标带、目录等模板专属结构，系统造不出来。

处理：`THEMES` 增加 `own_cover: True` 标记；`build_html_template_document` 据此**不再另造封面**，同时**不注入 `<div class="header">`**（模板自带页眉页脚，多注入一个标题条会顶掉封面后的版式）。

> 这里有个容易漏的点：`.header` 是 travel 管线注入的 running 元素，travel 模板自己定义了 `.header` 样式来决定显示/隐藏。四套模板没有这个类，若不跳过注入，标题会以普通 div 的形式出现在正文流里。

### 3.2 一个配方对一个模板

travel 是「一个配方 + 四套风格」（同一页结构换皮），四套模板是「一个配方对一个模板」（页结构各不相同：学术报告 4 页、论文 3 页、数据分析 4 页、研究报告 4 页）。

处理：
- `PAGE_TEMPLATE_RECIPES` 与主题一一对应；
- `resolve_family_theme` 对论文/报告配方**只接受配方自身的主题**，显式传别家主题一律回退（防止把论文的 CSS 套到研报的页结构上）；
- 但为了让 `theme` 参数仍可用，engine 里加了一条等价转换：`theme` 命中四套之一时，**等价于传同名 `kind`**。

### 3.3 不能走 markdown 路径

四套模板的 CSS 大量依赖模板专属类名（`.sec-h1`、`.three-line-table`、`.fin-table`、`.insight-item`、`.matrix`、`.badge`…）。这些类在 markdown 渲染路径上不存在，套上去只会得到一页错乱的排版。

处理：`design_rules` 增加 `PAGE_TEMPLATE_THEMES` 拦截——在 markdown 路径上解析出这四个主题时，回退到配方默认主题；同时把它们加入 `_SPEC_THEME_BLOCKLIST`，禁止 LLM 设计师跨体系选择。`pdf_render` 工具（只渲染 markdown）的 theme 枚举**刻意不包含**这四套，并在描述里指向 `pdf_generate`。

---

## 4. 实现结构

### 4.1 新增文件

```
app/docgen/pdf/pdf_themes/
├── academic_report.html     (011 学术报告 · 4 页)
├── thesis_paper.html        (012 论文投稿 · 3 页)
├── data_report.html         (013 数据分析报告 · 4 页)
└── research_report.html     (014 研究报告 · 4 页)
```

来源为 `docs/templates/011–014`，复制时清除了外部页面编辑器注入的 `data-page-node-id` 属性（共 550 处）。打包配置 `divine-server.spec` 已把整个 `pdf_themes/` 目录作为 data 打入，无需改动。

### 4.2 改动文件

| 文件 | 改动 |
| --- | --- |
| `theme_registry.py` | 新增 4 个 `THEMES` 条目（含 `html_template` / `own_cover` 标记）；`_travel_css` → `_html_template_css`（保留旧名别名）；新增 `is_html_template_theme` / `theme_owns_cover` / `html_template_skeleton` / `html_template_pages`；`load_theme_css` 改为按「是否页式模板」决定是否叠加 `modules.css` |
| `recipes.py` | 新增 `PageTemplateRecipe` 基类与 4 个配方；注册进 `RECIPE_REGISTRY`；`detect_recipe` 增加四类文档的分流（放在 business/report 之前，避免被宽泛词吸走） |
| `design_rules.py` | `KNOWN_THEMES` 补 4 项；新增 `INDEPENDENT_THEME_RECIPES` / `PAGE_TEMPLATE_THEMES` / `resolve_family_theme`；`resolve_design` 的独立主题分支由 `recipe_name == "travel"` 泛化为集合判断；markdown 路径加主题拦截 |
| `design_enforcer.py` | 无需改动（`KNOWN_THEMES` 已含新主题） |
| `cover_builder.py` | `build_travel_html_document` → `build_html_template_document`（保留旧名别名），按 `own_cover` 跳过系统封面与 `.header` 注入 |
| `renderer/renderer.py` | 改用新函数名 |
| `engine.py` | `theme` → `kind` 等价转换；HTML 配方分支由 `recipe_name == "travel"` 泛化为 `recipe.content_format == "html"`；四套走 `universal_color_overrides`，travel 仍走 `travel_color_overrides` |
| `api/pdf_themes.py` | `render-preview` 对自带封面的模板直接渲染模板页片段（markdown + 通用封面会散架） |
| `tools/adapters/pdf_generate.py` | `kind` 与 `theme` 枚举补 4 项，描述说明四套是页式模板 |
| `tools/adapters/pdf_render.py` | theme 枚举**不加**，描述指向 `pdf_generate` |
| `agent/core/prompt_sections.py` | 增加四类文档的场景分流规则，并说明「四套是页式模板而非视觉风格」 |

### 4.3 主色覆盖的接线

四套模板原本把主色写死在各自的语义变量里（`--navy` / `--ink` / `--blue` / `--green`），`theme_colors` 与 `color_scheme` 传进来会静默失效。处理：

```css
:root {
  --primary: #1F3A5F;        /* 由管线注入同名变量覆盖 */
  --navy: var(--primary);    /* 语义别名挂到主色上 */
  --blue: var(--accent);
  ...
}
```

管线注入的 `:root` 块在模板 CSS **之后**，同名声明按层叠规则胜出；`var()` 在计算值阶段解析，因此改 `--primary` 即整套联动。正文墨色（`--ink`）**不挂**主色，避免用户换个主色把正文染成彩色；论文模板是单色主题，主色只作用于标题与表格线。

---

## 5. 提示词里编码的排版契约

四套模板的版式有若干**踩过坑才总结出来**的硬约束，全部写进配方提示词，避免生成时复现：

| 模板 | 契约 | 不遵守的后果 |
| --- | --- | --- |
| data_report | `.chart-axis` 4 格必须 `table-layout: fixed` 等分，且第 1/2/3 格 `text-align: left`、第 4 格 `right` | 用 `center` 会让 25%/50% 刻度右偏到 37.5%/62.5%，与条长不符 |
| data_report | 「优先级 / 时限」列不加 `class="num"` | 表头左对齐、单元格右对齐，视觉错位 |
| data_report | 洞察编号固定「洞察 1..4」 | 编号列宽度不足会折行，编号与正文错位 |
| thesis_paper | 表注必须写成 `<div class="tbl-note">` 放在 `</table>` 之后 | 作为 `<tr>` 放进表内会让三线表收尾粗线落到注释下方 |
| thesis_paper | P2 必须出现 `3.1`，P3 才接 `3.2` | 编号跳号，P3 以孤立子标题开头 |
| academic_report | 图题在图下方（`.fig-caption`）、表题在表上方（`.tb-caption`） | 违反学术图表规范 |
| research_report | 每页（P2–P4）第一行必须是 `.page-head` 页眉条 | 页眉缺失，版面层级断裂 |

此外所有配方共用一条**扁平占位符**约定：`{{甲}} 与 {{乙}}`，禁止 `{{外层 {{内层}} 外层}}`（嵌套写法是 008 审计里 10 处括号缺陷的根因）。

---

## 6. 验证

### 6.1 端到端页数

用 `StructuredLLM`（模拟「按骨架正确产出」的模型，零 API 成本）跑完整 `PDFTool.run`：

| 配方 | 期望页数 | 实测 |
| --- | --- | --- |
| academic_report | 4 | 4 ✓ |
| thesis_paper | 3 | 3 ✓ |
| data_report | 4 | 4 ✓ |
| research_report | 4 | 4 ✓ |

四套输出与 `docs/templates/` 下的独立渲染逐页一致（封面色带贴顶、KPI 带满宽等分、页眉页脚就位）。

### 6.2 分流正确性

`detect_recipe` 对四类文档正确分流，且未被更宽泛的词吸走：

```
写一篇深度学习方向的论文        -> thesis_paper
做一份课程学术报告              -> academic_report
帮我写一份经营数据分析报告      -> data_report
出一份行业研究报告              -> research_report
帮我写份周报                    -> report      （未被 research_report 吸走）
做一份商业分析报告              -> business    （未被 data_report 吸走）
```

### 6.3 回归

- 新增测试 `tests/test_pdf_page_templates.py`：43 项全通过（主题注册、CSS 提取、别名接线、骨架页数、`.page-head` 不误判、降级内容不含注释文本、配方分流、族内主题守卫、markdown 路径拦截、`theme`≡`kind`、文档组装不注入 header、travel 仍注入 header 的回归保护、端到端页数）；
- 既有 PDF/主题/模块测试：52 项全通过；
- 全量测试：见 §6.4。

> 测试环境提示：本机沙箱下 pytest 默认 tmp 目录会报 `PermissionError: EEXIST`，需加 `--basetemp=/tmp/pt` 指定可写目录，与代码改动无关。

---

## 7. 已知限制

1. ~~**`data_report` 条形图的第 2–4 条不跟随主色**~~ —— 已修复，见 §10。
2. ~~**`research_report` 的 `--green-faint` 与 `--green-soft` 合并**~~ —— 已修复并还原原设计的两个层次，见 §10。
3. **`pdf_render` 不支持四套模板**（只渲染 markdown）。这是刻意设计：模板 CSS 与页结构强耦合。
4. **`cover` / `toc` 参数对四套无效**。模板页数与封面固定，传了不生效（工具描述已说明）。
5. ~~**MockLLM 下四套只会得到 1 页**~~ —— 已修复，见 §8。

> 至此「已知限制」里只剩 3、4 两条——它们都不是缺陷，而是页式模板的固有约束。

---

## 8. 补做：页结构兜底与 `content` 传参（2026-09-13 追加）

首版完成后发现两个真实会踩到的缺口，已一并修掉：

1. **模型输出不是页式 HTML 时会渲染成散架单页。** `generate_content` 对 `content_format == "html"` 的配方增加结构校验：输出不含任何 `<div class="page">` 片段时兜底为 `recipe.fallback_content(intent)`。
   典型触发场景是 **MockLLM（无 API Key 的演示模式）**——它返回通用演示文本，修复前四套都只出 1 页；修复后演示模式也能得到页数正确的模板样张。同时在 `intent.meta["content_qa"]` 记录 `page_fragments` 与 `expected_page_fragments`（后者来自新增的 `PageTemplateRecipe.expected_pages`，直接读模板页片段数）。
   注意**只对「完全没有页片段」兜底**，页数不足时不覆盖——那属于需要补页修复的场景，静默兜底会丢掉已生成的好内容。

2. **`content` 传参路径把 Markdown 当成 HTML 原样渲染。** `engine.py` 里只有 travel 会把传入内容交给 LLM 按骨架重组；已泛化为 `recipe.content_format == "html"`，四套模板同样先重组再渲染。

3. **页数不足时补页修复**（`ensure_page_template_pages`）。单次生成被 `max_tokens` 截断会让末尾整页丢失，
   这是页式模板最容易翻车的场景。与第 1 条的「完全无页片段」兜底分工不同——那里是整份跑偏，
   这里是跑对了但没跑完，需要**接着已有页往下续写**。
   流程：丢掉未闭合残页 → 数已有页片段 → 让模型**只补缺失的后 N 页**（提示词带上 `page_plan` 便于定位）→
   校验补出来的页片段数正好等于缺失数且不含封面页，否则**放弃拼接、保留已完成的页**（宁缺勿错）。
   travel 没有 `expected_pages`（页数与天数相关），此函数为 no-op。

验证：MockLLM 下四套页数 4/3/4/4 ✓；传 `content` 时同样 4/3/4/4 ✓；补页路径 6 项测试（正常续写、
拒接错误页数、拒接含封面的补页、页数已足不请求、残页丢弃、travel no-op）全部通过。合计新增 18 项测试。

## 9. 补做：提示词公共片段收敛（2026-09-13 追加）

`PageTemplateRecipe` 与 `TravelRecipe` 的提示词开头（角色句 + 骨架块 + 输出规则分隔线）原本各写各的，
且骨架读取的样板代码重复三处。已抽出两个模块级函数：

- `_load_skeleton(theme, fallback_name)` → `(skeleton, skeleton_name)`
- `_skeleton_prompt(role, desc, skeleton, skeleton_name)` → 角色句 + 骨架块 + 分隔线

**收敛原则：只收「逐字相同」的部分，各配方的「输出规则」正文保持独立。** travel 的提示词是长期调过的
（项目里有专门的 preprocess/fix 文档），为省几行重复去改它的措辞不划算。

### 用前后快照比对把风险变成可验证的

改动前先把 travel 两条分支的提示词存为快照（travel 8645 字符、travel_swiss 11504 字符），改完逐字比对。
**第一轮比对就抓到一个真实回归**：`desc` 参数带了尾部空格，拼出「PDF 的 完整旅行攻略」这种多余空格。
修正（`spacer` 只在修饰语与 `HTML` 之间留一个空格，`desc` 为空时退化为一个空格）后，两分支均逐字一致。

这条不变量已固化进测试（`test_travel_prompt_keeps_original_wording`）：既断言正确措辞存在，
也断言错误形式（`PDF 的 {desc}`）不存在。以后动 `_skeleton_prompt` 会立刻暴露对 travel 的影响。

## 10. 补做：data_report 条形图色阶跟随主色（2026-09-13 追加）

`data_report` 的条形图是 4 级色阶（`.chart-bar` / `.c2` / `.c3` / `.c4`）。首条挂了 `var(--primary)`，
后三条原本写死蓝色（`#3D74A8` / `#6D9CC7` / `#A8C3DC`），**换主色会出现「红首条 + 蓝后三条」的撞色**。

之前以「CSS 无法从 `--primary` 派生同色阶、`color-mix()` 在 WeasyPrint 66 支持不确定」为由搁置。
但这个理由只在 CSS 侧成立——管线里本来就有 HSL 派生机器（`_shift_lightness`、`derive_teal_scale` 等先例），
**可以在 Python 侧算好再注入**：

- `theme_colors.derive_bar_ramp(primary)` → `{"--bar-1"…"--bar-4"}`，按 HLS 亮度阶梯 `(0, .17, .32, .48)` 派生；
  增量取自原设计色板的亮度差。
- 模板 `:root` 补 `--bar-1…--bar-4`，`.chart-bar.cN { background: var(--bar-N) }`。
- `engine.py` 在 data_report 分支把色阶并入 overrides（显式 `--bar-N` 优先）。

**关键取舍：只在主色被覆盖时才派生。** 派生色与原写死色有 18–30 的通道差（原色板还调了饱和度，亮度增量还原不了），
无条件派生会改动默认观感。无覆盖时保留模板字面量，默认渲染与改动前完全一致。

验证（端到端抽取 PDF 里的条形填充色）：

| 场景 | 条形色 | 结果 |
| --- | --- | --- |
| 无覆盖 | 4 种 = `#14497B`/`#3D74A8`/`#6D9CC7`/`#A8C3DC` | ✓ 原色板不变 |
| `--primary: #B03A2E` | 4 种 = 派生色阶，**无残留蓝色** | ✓ 整体跟随 |

新增 3 项测试（派生规则、默认色板不变、换色后无残留蓝）。

### 顺带修掉：research_report 二级浅色

同一招再用一次。`research_report` 原设计有两个层次的浅色底：`--green-soft`（`#EAF1EE`，L≈0.93，徽章/数据胶囊）
与 `--green-faint`（`#F4F8F6`，L≈0.97，引用块底色）。上一版为避免撞色把两者都压到了 `var(--primary-light)`，
**顺带把原设计的层次也压平了**。现补 `derive_faint_tint(primary)`（L=0.965，饱和度沿用同套钳制规则），
模板加 `--primary-faint` 字面量兜底，`--green-faint: var(--primary-faint)`。

效果：默认渲染**还原**为原设计的两个层次（`#EAF1EE` / `#F4F8F6`），换主色时两者一起跟随。
新增 3 项测试（派生规则、默认还原原 faint 色、换色后不残留绿底）。

## 11. 后续建议

1. **输出规则正文的收敛（已核查，建议不动）**。逐条比对过两者的规则正文，**重叠只有 2 条**：

   | 规则 | travel | 论文/报告四套 | 差异 |
   | --- | --- | --- | --- |
   | 只输出 HTML body | 含 `<div class="page-footer">` 排除项 | 无该排除项 | travel 模板有页脚块，四套没有 |
   | 措辞 | 「也不要输出解释文字」 | 「也不要输出任何解释文字」 | 多一个「任何」 |
   | 类名约束 | 规则 7「只使用骨架中出现过的 CSS 类名」 | 规则 4 同义 | 实质相同、编号不同 |
   | 其余 6–8 条 | 路线总览/每日行程/预算页/水印/配图等 | 页序固定/占位符替换/数据自洽/不得编造 | **按文档类型各不相同，不是重复** |

   也就是说：规则正文的绝大部分是**各文档类型固有的内容**，不是重复代码。为了收敛那 2 条去改动 travel
   长期调过的措辞，收益接近零、风险不为零。建议维持现状；若日后确有需要统一，必须先做前后快照比对再改
   （见 §9 的方法，快照脚本思路：`content_system_prompt` 的返回值存盘 → 改完逐字 diff）。

> **关于 015 / 016（2026-09-13 核查）**：经确认，`keynote` 与 `devconf` **早已实现**在
> `app/docgen/ppt/renderer/themes.py::PPT_THEMES` 中，015/016 只是这两套主题的**视觉样张**（不参与运行时渲染）。
> 所以不存在「接入」工作，本轮做的是样张本身的缺陷修复与约定固化：
> - 修复 4 处占位符缺陷：015 一处漏闭合；016 一处四重括号（`{{{{官网地址}}`）+ 两处漏闭合。
> - 新增占位符卫生测试覆盖 011–016：`test_sample_placeholders_balanced`（括号平衡 + 无四重括号）
>   与 `test_pdf_sample_placeholders_are_flat`（011–014 禁止嵌套）。已验证注入缺陷会被拦截。
> - 015/016 使用「整句包裹 + 内层插槽」的嵌套写法，与 011–014 的扁平约定不同。当前括号平衡、
>   无运行时消费者，故**未**做 23 处机械扁平化——改动面大而收益为零；差异已写入 `docs/README.md`。
>   若日后要把它们接入会做占位符替换的管线，必须先扁平化。
