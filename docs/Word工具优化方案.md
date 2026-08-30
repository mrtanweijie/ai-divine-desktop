# Word 工具优化方案

> 背景：`word_document` 是文档三件套（PDF / PPT / Word）中最薄弱的一个——元素只有标题、无序列表、纯段落三种，不支持表格、图片、行内格式；而它的定位场景（周报、合同、会议纪要）恰恰是表格与条款格式要求最重的场景。本文档给出诊断与分层优化方案。

## 一、现状与链路

```
adapters/word_document.py（工具 schema：4 个参数 title/theme/path/sections）
  → scripts/word_document.py（131 行入口：路径校验、重试保存）
    → app/word_themes.py（187 行：9 套主题 token + 样式/封面应用，python-docx 1.2.0）
```

读侧配套：`read_file` → `document_reader.read_file_text`（anydoc 优先转 GFM Markdown，legacy `_read_docx` 兜底），**读写能力严重不对称**：读进来是完整结构的 Markdown，写出去只有纯文本。

参数面：title、theme（9 枚举）、path、sections[{heading, body}]。脚本实际还支持 `type`（heading/bullet_list）、`content`、`text` 等字段（`scripts/word_document.py:36-47`），但 schema 未声明，LLM 无入口可用。

## 二、核心诊断：为什么"Word 生成 = 纯文本堆"

按感知影响排序：

1. **元素能力面极窄，与定位场景错位**。工具描述写着"周报、合同、会议纪要"，三类场景都离不开表格 / 编号条款 / 数据指标，但 `add_sections`（`scripts/word_document.py:34-65`）只支持标题（h1/h2/h3）、List Bullet、普通段落三种元素：没有表格、没有有序列表、没有图片、没有代码块、没有引用。讽刺的是表头着色 `shade_table_header`（`word_themes.py:172-187`）早已写好，却是全仓无调用的死代码——表格能力"差最后一步"但从未接上。

2. **零行内格式，markdown 语法原样漏出**。正文按行 `document.add_paragraph(line)` 直插（`scripts/word_document.py:64-65`）：`**加粗**`、`` `代码` ``、`[链接](url)` 会带着星号反引号原样出现在文档里；`- item` 不被识别为列表；空行产生空段落；`1. 条款` 保持字面。LLM 天然倾向输出 markdown，输出端不做任何解析，格式损耗 100%。

3. **版式结构缺失**：
   - 封面不是页：`add_title_page`（`word_themes.py:154-169`）只是 26pt 标题 + 12pt 副标题两个段落，无分页符，正文紧贴同页开始；
   - "页脚"是正文末段：生成完成后 `document.add_paragraph("AI Divine · Word Document")`（`scripts/word_document.py:103-106`），不是节页脚，不会出现在每页底部，也没有页码；
   - 无目录（Word TOC 域）、无分页符控制、无页眉。

4. **schema 与实现脱节**。adapter schema 只声明 heading/body（`adapters/word_document.py:39-46`），脚本支持的 `type`/`content`/`text` 无 schema 入口；`_DOCUMENT_RULES` 提示词（`agent/core/prompt_sections.py:216-222`）也只教 LLM"问风格 → 映射 theme"，没有结构化内容的表达指引——能力有实现、无入口，LLM 想传也传不进来。

5. **主题同质化**。9 套主题只差字体/字号/行距/页边距/标题色五个 token；"modern"（`word_themes.py:53-62`）与"universal"（`13-22`）的 7 个值完全相同，是重复主题。字体不分西文/中文双通道（ascii/hAnsi/eastAsia 全设 PingFang SC，`word_themes.py:114-120`），Windows 环境无回退链。对比：PDF 有 11 套 CSS 主题 + 模块化布局，PPT 有 9 套主题 × 5 种版式自动判断。

6. **无质检闭环**。保存即返回；对比 PDF 侧正在建设的"设计校验/自检"层，Word 侧连"生成的表格行数是否等于入参"这类最便宜的结构校验都没有。项目里 anydoc 已能 docx→GFM，读回校验成本极低但未使用。

## 三、项目内已具备、未被 Word 用上的能力

| 设施 | 位置 | 说明 |
|---|---|---|
| 表头着色 | `word_themes.shade_table_header`（死代码） | 接上即可用 |
| 表格样式范式 | `spreadsheet.py:246-317`（表头/斑马纹/列宽自适应/汇总行） | 直接移植到 docx 表格 |
| 网络图下载内嵌 | `pdf_theme_manager._fetch_image_data`（`:1855`） | 6s 超时、2MB 上限，PDF 旅行手册在用 |
| AI 生图 | `image_generate` 适配器 | 封面/配图场景 |
| Markdown 解析 | `markdown` 3.10.3（已安装，tables/fenced_code 扩展） | md→HTML→遍历映射 docx 元素，零新依赖 |
| docx 结构读回 | anydoc / `document_reader._read_docx` | 生成后自检闭环 |
| 页脚/页码域 | python-docx 1.2.0 原生 `section.footer` + OXML fldSimple | 无新依赖，已验证 |

## 四、优化方案

### 方案一：元素体系扩展 + 行内格式解析【P0，性价比最高】

不引入新依赖，把"纯文本堆"变成"有文档语言的 Word"。

1. **行内格式解析（地基）**：新增 `_add_rich_text(paragraph, text)`，把 `**bold**` / `*italic*` / `` `code` `` / `[text](url)` 解析为多 run（code 用 Consolas + 浅灰底纹），所有元素入口统一走它。
2. **section 类型从 3 种扩到 10 种**：
   - `table`：`{type:"table", headers:[], rows:[[]]}` → `add_table` + `shade_table_header`（现成）+ 斑马纹/列宽自适应（移植 spreadsheet 范式）；
   - `numbered_list` → style="List Number"（默认模板已含该样式，已验证）；
   - `quote`（左缩进 + 左侧竖线边框 + 强调色）；
   - `code_block`（等宽字体 + 浅灰段落底纹）；
   - `image`：`{type:"image", src, caption}`，本地路径/URL → `add_picture`，宽度自适应版心（网络图复用 `_fetch_image_data`）；
   - `page_break`、`toc`（Word TOC 域，dirty 置位提示打开时更新）。
3. **正文宽容解析**：`add_sections` 内做逐行预处理——`- ` 开头自动转 List Bullet、`1. ` 开头转 List Number、空行跳过、markdown 表格块自动转 table 元素；LLM 不传 type 也能得到正确版式，兜住存量调用。

工作量：3-4 天。风险：低。

### 方案二：真实页面结构【P0】

1. **真封面页**：`cover=true` 时标题页独占（标题/副标题/日期/品牌脚注）+ `add_page_break`；默认（周报类）保持现有紧凑头部不变，兼容存量调用。
2. **真页脚**：品牌文字移入 `section.footer` 居中，追加「第 X 页 / 共 Y 页」PAGE/NUMPAGES 域；可选页眉放文档标题（细线分隔）。
3. **目录**：`toc=true` 时封面后插入 TOC 域 + 分页；打开时需一次"更新域"，结果文案里提示用户即可。

工作量：1-2 天。风险：低。

### 方案三：Markdown 直转入口【P1，补读写对称】

对齐 `pdf_render`"现成内容转换"入口：word_document 新增 `markdown` 参数（与 sections 二选一）。用已装的 markdown 库（tables/fenced_code 扩展）转 HTML 后遍历映射：h1-h3→Heading、p→正文、ul/ol→列表、table→表格、blockquote→引用、pre/code→代码块、img→图片（下载内嵌）、strong/em/code/a→行内 run。

对话中的正文、仓库 README、已生成的报告 md 可一键转 Word——"先出 md 再出正式版"是会议纪要/合同评审场景的高频路径。

工作量：2-3 天。风险：中低（子集覆盖不全时按段落兜底，不失败）。

### 方案四：主题治理 + Schema/Prompt 对齐 + 自检【P1】

1. **主题治理**：删除 modern（与 universal 全同）或在映射层做别名；字体拆西文/中文双通道（ascii=西文字体、eastAsia=PingFang SC），避免 Windows 裸奔；主题增加一个版式级 token（标题装饰：底色块/侧条/下划线三选），让"换主题"有结构感知而非只换色。
2. **Schema 对齐**：adapter schema 扩成完整元素定义（type 枚举 + table/headers/rows/src 等字段），与脚本能力一致；`_DOCUMENT_RULES` 增补表达指引与场景引导：会议纪要→决议表格、周报→数据指标表、合同→编号条款。
3. **生成后自检**：保存前用 python-docx 读回校验（章节/表格行数/图片数与入参一致、空标题清理）；失败降级返回并附警告，复用现有 retry 循环。

工作量：2 天。风险：低。

## 五、实施顺序与预期

| 顺序 | 方案 | 优先级 | 工作量 | 感知收益 |
|---|---|---|---|---|
| 1 | 方案一 元素 + 行内格式 | P0 | 3-4 天 | 最高：表格/加粗/列表直接决定文档可用性 |
| 2 | 方案二 页面结构 | P0 | 1-2 天 | 高：真封面/页码是"正式文档"的最低门槛 |
| 3 | 方案四 主题治理 + schema 对齐 | P1 | 2 天 | 中：让 LLM 真正用上新能力 |
| 4 | 方案三 markdown 直转 | P1 | 2-3 天 | 中：补齐读写对称的高频路径 |

四案合计约 9-11 天；无新增依赖（python-docx 1.2.0 + markdown 3.10.3 均已安装）。方案一 + 二落地后，Word 从"三件套垫底"追平 spreadsheet 优化后的水准；方案三补上内容转换入口后与 pdf_render 能力对齐。
