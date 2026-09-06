# pdf_form_generate 改造方案：基于 docs/pdf-forms HTML 模板库的模块化表单生成

> 状态：方案待评审 ｜ 日期：2026-09-06
> 前置：pdf_form_generate v1（reportlab 声明式布局）已实施（见 [office-edit 闭环附录](design/017-office-edit-closed-loop-20260906.md)）
> 模板库：[docs/pdf-forms/](../pdf-forms/)（用户手工构建：4 模板 + forms.css + 字段协议 + tagger.js）

## 1. 背景与现状

v1 的 `pdf_form_generate` 用 reportlab 硬编码布局（标签左 + 控件右的单调行式），版式简陋，无法呈现申请表/登记表/报销单等真实表单的观感（分节卡片、网格表格、下划线填空、审批栏、量表矩阵）。

用户已手工构建 HTML 模板库 `docs/pdf-forms/`，具备：

| 资产 | 内容 |
| --- | --- |
| 4 个完整模板 | application（申请）/ registration（登记）/ survey（问卷）/ expense（报销）——形态各异：分节流式+下划线填空+三级审批、紧凑网格+子表、量表矩阵+NPS、可重复明细表+金额合计 |
| 字段协议 | 每个可填写单元用 `data-field`（唯一名）/`data-type`（15 种）/`data-label`/`data-required` 自描述——**HTML 即 schema 源** |
| forms.css | tokens（4 套主题换肤）/12 列栅格/控件标准尺寸/签名栏/print 规则（`break-inside: avoid` 防跨页断裂） |
| tagger.js | 浏览器字段标注器 + `window.__PDF_FORM_SCHEMA__` 检视 |

**核心矛盾**：WeasyPrint 不支持生成 AcroForm 表单字段——HTML 里的控件只能画成静态样子。而 v1 的 reportlab 路径能放真控件却做不出模板观感。

## 2. 目标

**模板的视觉（WeasyPrint）+ 真控件（pymupdf）双阶段合成**：HTML 模板负责"长相"，pymupdf 负责在模板标记的槽位上放置真正的 AcroForm 交互控件。用户/模型可从模板的输入模块**自由组合**出完整表单 PDF，产物直接进入既有闭环（`pdf_form_fields` 读取 → `pdf_form_fill` 填写 → 备份/撤销）。

**非目标**：不做数字签名控件（signature 为视觉占位，打印后手签）；不做扫描件补控件；Office→PDF 转换另议。

## 3. 架构：三阶段管线

```
① HTML 组装            ② WeasyPrint 渲染           ③ pymupdf 控件放置
模板模式: 实例化内置模板   HTML(协议标记+forms.css)     扫描链接注解定位每个槽位 rect
组合模式: 模型按模块库     → PDF（print-color-adjust    → 按字段类型放置 AcroForm 控件
          拼装模块 HTML     exact, @page A4）            （透明填充，CSS 画的下划线/盒子透出）
```

### 3.1 槽位定位：链接注解法（核心机制）

每个可填写槽位在 HTML 里渲染为一个**携带自描述链接的空盒子**：

```html
<a class="fill-box fill-text" href="pdf-form://applicant_name"
   style="width:180px;height:24px"></a>
```

- WeasyPrint 对 `<a href>` 生成**URI 链接注解**，注解 rect 即槽位的精确位置；
- pymupdf `page.get_links()` 读出 `{rect, uri}`，`uri` 前缀 `pdf-form://` 解析出字段名 → 一一对应放置控件；
- 控件用**透明填充、无边框**——CSS 画的下划线/盒子透出，视觉完全由模板决定，交互完全由 AcroForm 提供。

> 备选方案（链接注解实测不可用时）：盒内渲染 0.5pt 同底色 marker 文本，pymupdf `search_for(marker)` 定位。期一第一步先做 WeasyPrint 链接注解的实证（空盒 + 自定义 scheme），通过后锁定方案。

### 3.2 data-type → AcroForm 控件映射

| data-type | AcroForm 控件 | 说明 |
| --- | --- | --- |
| text / date / number / money | TEXT | number/money 右对齐；money 千分位格式提示 |
| textarea | TEXT（多行 field_flags） | 高度由 CSS 决定 |
| select | COMBOBOX | 选项从模块的 option 元素提取 |
| radio | 每选项一个 CHECKBOX（`field::选项` 分组命名） | 互斥由 `pdf_form_fill` 填写逻辑保证（已实现） |
| checkbox | CHECKBOX | 勾选态按 `data-checked` |
| rating / nps | **视觉占位**（v1 无控件，打印后手填） | v2 可升级为逐点 checkbox |
| signature | **视觉占位**（空盒子，打印后手签） | pymupdf 数字签名支持有限，明确不做 |
| table | 递归：单元格内字段各自成槽位 | 明细表 `data-repeatable` 行为模板预画 N 行 |
| group | 递归展开子字段 | — |

`data-required="true"` → AcroForm 字段置 Required 标志位；`data-label` → AcroForm tooltip。

## 4. 两种使用模式

### 4.1 模板模式（内置模板实例化）

```
pdf_form_generate({
  "template_id": "application",          // application/registration/survey/expense
  "theme": "corporate",                  // 可选：minimal/corporate/tech/forest
  "values": { "applicant_name": "李铭", "matter_type": "采购" },   // 可选预填
  "file_name": "采购申请表"
})
```

工具从模板库加载 HTML → 按可选 `values` 预填控件默认值 → 走三阶段管线。模板的静态文字（公司名/表单编号等）由模型通过 `meta`/`content` 覆盖参数替换（v1 先支持 title/org 编号两个高频位）。

### 4.2 组合模式（自由拼装）

模型直接产出遵循协议的完整 HTML（从模块库取片段拼装——分节头/填空行/网格对/单选组/子表格/审批栏/签名区），作为 `html` 参数传入。工具职责收缩为：**协议校验（BeautifulSoup 解析 [data-field]，白名单 data-type、字段名唯一、必填属性齐备）→ 渲染 → 控件放置**。

### 4.3 自定义主题色

模板变量体系统一（`--primary/--primary-light/--accent/--text-*/--bg-*`，控件 158 处 `var(--…)` 全消费），自定义色注入比简历 colorize 简单：

```
用户"黑色 #1A1A1A" → 派生 {--primary:#1A1A1A, --primary-light, --accent, --soft}
                   → HTML 追加 <style>:root{...}</style> → 全表单生效
```

- 输入契约沿用 prompt 已教形态：`theme_colors: {"--color-primary": "#1A1A1A"}` 或 `color_scheme: "黑色"`（色名词表复用 colorize 的 RESUME_COLOR_NAMES，含黑色/石墨墨黑/炭黑等无彩色系）；
- 派生逻辑复用 `colorize.derive_resume_palette`（HSL 四档：main 压亮度保证白字可读；无彩色系派生为灰阶，匹配"纯黑单色"诉求）；
- 注入为 `:root` 覆盖块（`<html data-theme>` 保持不动，覆盖块在后面优先）；
- 简历换色的教训（变量名异构导致静默失效）在此不适用——表单模板变量名统一规范。

### 4.4 兼容

- v1 的 `sections[].fields[]` JSON 声明式模式**保留**：编译为内置模块 HTML（组合模式的语法糖），`layout: "plain"` 时走原 reportlab 路径降级；
- `pdf_form_fields` / `pdf_form_fill` 零改动：AcroForm 字段名 = `data-field`，分组单选的 `field::选项` 语义已实现。

## 5. 资源打包

模板库（4 HTML + forms.css + 字体声明）需进入冻结包：

- `divine-server.spec` 的 `datas` 增加 `docs/pdf-forms` → 运行时从 `sys._MEIPASS` 解析模板路径；
- 或将模板编译为 Python 模块常量（`docgen/pdf/form_templates.py`）——免路径解析、免 docs 目录运行时依赖。**取后者**（与"脚本由包内运行"的现状一致）。

## 6. 分期计划

| 期 | 内容 | 工作量 | 出口标准 |
| --- | --- | --- | --- |
| 〇 | WeasyPrint 链接注解实证（空盒 `<a>` + 自定义 scheme + pymupdf get_links 读 rect） | 0.5 天 | 拿到精确 rect；失败则切换 marker 方案并修订本文档 |
| 一 | 管线核心：HTML 组装 → 渲染 → 控件放置（text/textarea/date/number/select/checkbox/radio 七类）+ application 模板实例化 + values 预填 + 闭环测试 | 2 天 | 用模板生成的表单经 pdf_form_fields/fill 全链路可用 |
| 二 | 模板全量：registration/survey/expense（表格/金额/签名占位/量表）+ data-theme 换肤 + **自定义主题色注入** + 分页 break-inside 验证 | 1–1.5 天 | 4 模板全可生成且视觉与浏览器预览一致；黑色/黑金自定义色生效 |
| 三 | 组合模式：协议校验器 + 模块库文档（模型拼装指引进 prompt_sections）+ v1 JSON 模式编译兼容 | 1 天 | 模型可自由组合新表单 |

## 7. 测试计划

| 测试 | 内容 |
| --- | --- |
| `test_pdf_form_link_anchors.py` | 期〇实证固件：WeasyPrint 对空盒链接的注解生成、rect 精度 |
| `test_pdf_form_html_render.py` | 每种 data-type 的控件放置（类型/rect 命中槽位/默认值/required 标志）；字段名唯一性/协议白名单校验 |
| `test_pdf_form_templates.py` | 4 模板实例化：控件集合 == 模板 data-field 集合；values 预填；分页后跨页字段不丢 |
| 闭环 | 生成 → pdf_form_fields → pdf_form_fill → verify_filled（复用现有断言） |

## 8. 风险与对策

| 风险 | 对策 |
| --- | --- |
| WeasyPrint 对空盒/自定义 scheme 链接的注解行为不确定 | 期〇实证先行；备选 marker 文本方案已设计 |
| 控件透明填充下 CSS 视觉与控件交互错位（rect 偏移） | 期〇的 rect 精度断言（注解 rect vs 槽位 rect 差 ≤1pt） |
| 打印色彩丢失（表头/审批栏背景） | `print-color-adjust: exact`（README 已提示），生成时模板 CSS 已内置 |
| 冻结包模板资源遗漏 | 模板编译为 Python 常量（§5），构建期天然包含 |
| 模型拼装 HTML 不合协议 | 协议校验器逐条报错（字段名重复/类型白名单/缺 data-label），模型可自纠 |
| 简历换色的 colorize 不适用于此管线 | 表单模板自带完整 CSS tokens，不依赖 colorize |

## 9. 与现有批次的关系

- 当前未提交批次（colorize 修复 + 接受按钮移位 + PDF 表单填写/转 Word 工具）建议**先提交**，本方案在其上迭代（同文件 `pdf_form_generate.py` 将被改造）；
- 用户手工资产 `docs/pdf-forms/`（HTML/css/js）为只读参考与打包源，不并入 git 提交边界之外的操作。
