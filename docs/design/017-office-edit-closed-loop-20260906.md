# Office 编辑闭环设计方案（fill_template / edit_docx / edit_xlsx）

> 编号：017 ｜ 类型：design ｜ 日期：2026-09-06 ｜ 状态：已实施（期一/二/三）
> 实施结果：新增 fill_template / edit_docx / edit_xlsx / edit_pptx / document_outline 五个工具，
> 测试 936 → 1001 全绿（tests/test_word_editor.py、test_office_edit.py、test_office_registration.py、
> test_xlsx_editor.py、test_pptx_editor.py）。实现与设计的差异见文末附录。
> 关联：[../review/006-capabilities-recheck-20260905.md](../review/006-capabilities-recheck-20260905.md)（"办公能力只生成不编辑"结论）
> 本文初始版本只做设计，代码已按本文实施。


## 1. 背景与问题

现有 Office 工具链是"单向生成"：能从零产出 docx/xlsx/pptx，不能修改已有文件。办公场景里"改"比"生成"更高频——更新周报数据、按模板填合同、往现有表格追加数据，目前全部无法完成，只能"读出来 → 整份重新生成"，样式和用户后续的手工调整全部丢失。

现状证据（均为已核实代码事实）：

| 现状 | 位置 |
| --- | --- |
| `word_document` 固定 `Document()` 新建，无打开已有文件的分支 | `app/tools/scripts/word_document.py`（import 处即 `from docx import Document`，全脚本无 `load` 路径） |
| `spreadsheet` 工具自述"本工具不能读取已有 Excel" | `app/tools/adapters/spreadsheet.py` 工具描述 |
| `read_file` 经 anydoc 可读 Office（转 GFM Markdown），但内容硬截 12000 字符，且**不输出段落序号/表格序号**——Agent 看得到内容、指不出坐标 | `app/document_reader.py:19-27`、`app/tools/scripts/read_file.py`（`capped = selected[:12000]`） |
| 撤销快照单文件上限 512KB，带图 docx/xlsx 轻松超限 → `undo_last_turn` 保护不了 Office 编辑 | `app/tools/checkpoint.py` `_MAX_FILE_BYTES = 512 * 1024` |
| 外部路径（用户桌面真实文件）的解析与确认机制已存在，可复用 | `app/tools/base.py:67 resolve_external_path`、`app/agent/tools/execution.py:561-600`（`ctx.approved_paths` 免重复确认） |
| openpyxl 3.1.5 往返保存**保留图表与公式**（旧版"编辑丢图表"限制已不存在，实测验证，见 §10） | `.venv` 内实测：带 BarChart + `=SUM()` 的 xlsx 经 load→改→save 后 chart XML 与公式完整幸存 |

结论：缺口不在依赖库，在没写工具 + Agent 无定位坐标 + 撤销保护盖不住二进制文件。

## 2. 目标与非目标

**目标**：用户给出一份已有文档 + 一句修改意图，Agent 能"读取定位 → 改前确认 → 执行 → 验证 → 交付"，全程样式不丢、原文件可控、误操作可撤销。

**非目标（明确不做）**：

- 版式级编辑（改字体/字号/颜色/页边距）——参数空间大，语言模型干这个不可靠；
- `.doc` 老格式直接编辑——python-docx 不支持，明确报错并引导另存 `.docx`（读取侧 anydoc 可读 `.doc`，可走"读出内容 → 重新生成"兜底）；
- 修订模式（track changes）/ 实时协作——python-docx 支持有限，非单人桌面助手核心场景；
- `edit_pptx` 只做文本替换，不动母版、不动版式（三期再议）。

## 3. 闭环架构

```
① 读取定位            ② 改前确认              ③ 执行                ④ 交付
document_outline  →  _EDIT_TOOLS 确认卡    →  子进程脚本执行    →  输出路径 + .bak
read_file(全文)      diff 呈现改动           run 级/单元格级      + 验证结果 JSON
                     (复用 edit_files 流)    操作,样式保留         hits/missed 反馈
```

四个环节各自的现状与新增：

| 环节 | 现状 | 本方案新增 |
| --- | --- | --- |
| 读取定位 | `read_file` 给全文（截断），无坐标 | `document_outline` 工具（对偶于代码侧 `list_definitions`），输出可编辑坐标 |
| 改前确认 | `edit_files` 的 SEARCH/REPLACE 确认流 | 三个新工具加入 `_EDIT_TOOLS`，diff 换 Office 内容形态 |
| 执行 | 无 | `docgen/word/editor.py`（run 级替换引擎）+ `docgen/xlsx_editor.py` + 子进程脚本 |
| 交付 | 生成工具返回产物路径 | 编辑工具额外返回 `.bak` 备份路径 + 命中数验证结果；`undo_last_turn` 补 `.bak` 恢复分支 |

## 4. 工具规格

三个写工具统一约束：

- 执行路径：`_run_subprocess_tool` 子进程（与 `word_document` 一致），损坏/加密文件崩在子进程内，不伤 sidecar；
- `path` 参数同时接受 workspace 相对路径与外部绝对路径；外部路径走 `allow_external_paths` 确认流；
- 结果 JSON 统一契约见 §5.5。

### 4.1 `fill_template`（期一，最先做）

识别并填充 docx/xlsx 中的 `{{占位符}}`。合同、offer、通知函、介绍信等最高频场景，实现最简单，用于打通整条链路。

```jsonc
// 参数
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "模板文件路径（docx/xlsx），workspace 相对路径或用户提供的绝对路径"
    },
    "values": {
      "type": "object",
      "additionalProperties": { "type": "string" },
      "description": "占位符→值映射，如 {\"company\": \"某某科技\", \"sign_date\": \"2026年9月6日\"}；键不带花括号"
    },
    "list_values": {
      "type": "object",
      "description": "表格行填充（xlsx 或 docx 表格）：键为占位符名，值为对象数组，逐行展开整行；如 {\"items\": [{\"name\": \"..\", \"qty\": \"2\"}]}",
      "additionalProperties": {
        "type": "array",
        "items": { "type": "object" }
      }
    },
    "save_as": {
      "type": "string",
      "description": "另存文件名（不含目录）；默认 <原名>_filled.<ext>"
    }
  },
  "required": ["path", "values"]
}
```

行为要点：

- docx：正文段落、表格单元格、页眉页脚内的 `{{key}}` 全部替换；`list_values` 命中表格时，以占位符所在行为模板行，向下复制 N-1 行再逐行填充（沿用该行样式）；
- xlsx：所有 sheet 的字符串单元格替换；不触碰公式单元格；
- 未命中的 key 不算失败，列入 `missing_keys` 返回，由 Agent 决定向用户澄清或忽略；
- 值一律按字符串写入，`number_format` 由调用方可选指定（期二）。

### 4.2 `edit_docx`（期一）

```jsonc
// 参数
{
  "type": "object",
  "properties": {
    "path": { "type": "string", "description": "docx 文件路径" },
    "ops": {
      "type": "array",
      "description": "操作序列，按顺序执行；任一操作定位失败则整个事务中止且不写盘",
      "items": {
        "type": "object",
        "properties": {
          "op": {
            "type": "string",
            "enum": ["replace_text", "set_paragraph", "set_table_cell", "append_section", "delete_paragraph"]
          },
          "find":       { "type": "string", "description": "(replace_text/delete_paragraph) 要查找的文本，需完整落在同一段落内" },
          "replace":    { "type": "string", "description": "(replace_text) 替换文本" },
          "all":        { "type": "boolean", "description": "(replace_text) 替换全部命中，默认只替换第一处" },
          "match":      { "type": "string", "description": "(set_paragraph/delete_paragraph) 段落定位文本（段落内包含即命中）" },
          "text":       { "type": "string", "description": "(set_paragraph) 新段落文本" },
          "table":      { "type": "integer", "description": "(set_table_cell) 表格序号，从 1 开始，与 document_outline 的表格清单对应" },
          "header":     { "type": "string", "description": "(set_table_cell) 列定位：目标列的表头文字" },
          "row_key":    { "type": "string", "description": "(set_table_cell) 行定位：该行第一列的值" },
          "row":        { "type": "integer", "description": "(set_table_cell) 行序号兜底（与 row_key 二选一，row_key 优先）" },
          "col":        { "type": "integer", "description": "(set_table_cell) 列序号兜底（与 header 二选一，header 优先）" },
          "heading":    { "type": "string", "description": "(append_section) 新章节标题" },
          "level":      { "type": "integer", "description": "(append_section) 标题级别 1-3，默认 2" },
          "body":       { "type": "string", "description": "(append_section) 章节正文，支持 **粗**/`码`/[链](接) 行内语法（复用 word elements）" },
          "items":      { "type": "array", "items": { "type": "string" }, "description": "(append_section) 列表条目" }
        },
        "required": ["op"]
      }
    }
  },
  "required": ["path", "ops"]
}
```

操作语义：

| op | 语义 | 定位方式 |
| --- | --- | --- |
| `replace_text` | 段落内文本替换，run 级保样式（§5.1） | 内容匹配；`all` 控制全部/首处 |
| `set_paragraph` | 整段文字替换（样式取段首 run） | `match` 内容匹配 |
| `set_table_cell` | 更新表格单元格 | `header`+`row_key` 优先，`row`/`col` 序号兜底 |
| `append_section` | 文档末尾追加章节（标题+正文/列表/表格） | 无需定位，复用 `docgen/word/elements.py` 元素渲染 |
| `delete_paragraph` | 删除段落 | `find`/`match` 内容匹配 |

事务性：ops 按顺序在内存中执行，**任一步定位失败则整体中止不写盘**，返回已成功模拟的步骤清单与首个失败原因——避免"改了一半"的文件。

### 4.3 `document_outline`（期一，配套读取工具）

返回可编辑坐标，供 Agent 在 `edit_docx`/`edit_xlsx` 前调用。与 `list_definitions`（代码结构大纲）完全对偶。

```jsonc
// 参数
{
  "type": "object",
  "properties": {
    "path": { "type": "string", "description": "docx/xlsx 文件路径" }
  },
  "required": ["path"]
}

// docx 返回
{
  "kind": "docx",
  "paragraphs": [
    { "index": 1, "style": "Heading 1", "preview": "2026年9月工作月报" },
    { "index": 2, "style": "Normal",    "preview": "本月共完成客户交付项目 12 个，环比…" }
  ],
  "tables": [
    { "index": 1, "rows": 9, "cols": 4, "headers": ["项目", "负责人", "状态", "交付日期"] }
  ]
}

// xlsx 返回
{
  "kind": "xlsx",
  "sheets": [
    {
      "name": "9月",
      "dims": "A1:F42",
      "headers": ["日期", "客户", "金额", "备注"],
      "has_formulas": 3,
      "has_chart": true
    }
  ]
}
```

- `preview` 截前 50 字，全量内容仍走 `read_file`；
- docx 段落 `index` 同时是 `set_paragraph` 等的兜底坐标（本期 ops 以内容匹配为主，index 兜底在期二放开）。

### 4.4 `edit_xlsx`（期二）

```jsonc
// 参数
{
  "type": "object",
  "properties": {
    "path": { "type": "string", "description": "xlsx 文件路径" },
    "ops": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "op": {
            "type": "string",
            "enum": ["set_cells", "append_rows", "add_sheet", "set_formula"]
          },
          "sheet":  { "type": "string", "description": "sheet 名；set_cells 的 items 内可逐项覆盖" },
          "cells": {
            "type": "array",
            "description": "(set_cells) 单元格更新列表",
            "items": {
              "type": "object",
              "properties": {
                "cell":  { "type": "string", "description": "A1 坐标，如 B3" },
                "value": { "description": "新值；字符串/数字/布尔" },
                "header": { "type": "string", "description": "列定位辅助：按表头文字解析出列号，与 cell 的列字母二选一" },
                "number_format": { "type": "string", "description": "可选，如 '#,##0.00'、'0.0%'" }
              },
              "required": ["cell", "value"]
            }
          },
          "rows":   { "type": "array", "items": { "type": "array" }, "description": "(append_rows) 追加的数据行，从现有数据区末尾之后开始写" },
          "name":   { "type": "string", "description": "(add_sheet) 新 sheet 名" },
          "headers":{ "type": "array", "items": { "type": "string" }, "description": "(add_sheet) 表头行，套用 spreadsheet 生成器的主题样式" },
          "cell":   { "type": "string", "description": "(set_formula) 公式目标单元格" },
          "formula":{ "type": "string", "description": "(set_formula) 公式，如 '=SUM(B2:B13)'，以 = 开头" }
        },
        "required": ["op"]
      }
    }
  },
  "required": ["path", "ops"]
}
```

行为要点：

- `load_workbook` 不传 `data_only`（默认保留公式），已实测公式与图表往返无损；
- 合并单元格只允许写左上角锚点，写非锚点坐标报 warning 并改写锚点；
- `append_rows` 自动探测现有数据区末行（含公式区），不覆盖已有数据；
- `add_sheet` 复用 `spreadsheet.py` 的表头样式（主题色/冻结/筛选），保证与生成链路观感一致；
- 编辑后的文件由 openpyxl 全量重写：期二补一条**嵌入图片存活**的冒烟断言（图表已实测，图片未测）。

## 5. 关键技术设计

### 5.1 run 级替换引擎（docx 样式不丢的核心）

docx 段落由多个 run 组成（不同字体/加粗/颜色各占一个 run）。引擎规则（落 `docgen/word/editor.py`，纯函数）：

1. 在段落全文上做查找，得到命中区间 `[start, end)`；
2. 计算命中所覆盖的 run 集合；
3. **单 run 命中**（最常见）：只改 `run.text`，样式天然保留；
4. **跨 run 命中**：若被覆盖 run 的格式属性（font.name/size/bold/italic/color）全部一致 → 合并替换；不一致 → 用首个 run 的格式承载新文本、清空 span 内其余 run（与 Word 自身查找替换行为一致）；
5. 结果报告 `cross_run` 计数，供 Agent/用户知晓该处格式可能简化。

禁止整段重建（`paragraph.text = ...` 会把全段压成单 run，丢失段内混合格式）。

### 5.2 定位双轨

- **内容匹配优先**：模型给的 `find/match/header/row_key` 做精确匹配（`strip` + 全角/半角归一 + 大小写不敏感可选）；未命中时报出最相近的 3 个候选段落/表头（编辑距离），Agent 可自行修正重试；
- **坐标兜底**：`document_outline` 的 `index`/A1 坐标作为第二选择；文档结构变化导致坐标漂移的风险由"改前 diff 确认"兜底（§5.4）。

### 5.3 输出与安全策略

两个绕不开的既有约束：快照 512KB 上限（checkpoint.py）使 `undo_last_turn` 对 Office 文件失效；外部路径确认流已存在（base.py + execution.py）。策略：

| 文件来源 | 策略 |
| --- | --- |
| workspace 内文件 | 原地编辑；写盘前先把原文件字节级备份到 `data_dir/backups/<session_id>/<文件名>.<ts>.bak`。**不放 workspace 内**：Rust 侧文件树（`src-tauri/src/commands/workspace.rs`）无点前缀过滤，workspace 内任何备份文件都会漏进前端文件面板并触发 watch 事件；放 `data_dir` 与 checkpoints 同级有先例，且天然不进快照枚举 |
| 外部文件（用户桌面等） | **不原地改**。先复制进 `workspace/documents/edited/<原文件名>_<时间戳>.<ext>`，在副本上编辑；原文件零风险，结果里给副本路径与下载入口 |
| `.doc` 输入 | 直接拒绝，报错文案引导"另存为 .docx 后重试，或让我读取内容重新生成" |

`undo_last_turn`（`app/tools/adapters/undo_turn.py` 一族）补一条分支：本会话若存在 Office 编辑记录，恢复 = 从 `data_dir/backups/` 拷回覆盖原文件；每会话保留最近 3 份。

### 5.4 改前确认与改后验证

- 三个写工具**不加入** `execution.py:30` 的 `_EDIT_TOOLS`——该集合唯一消费点是执行成功后的代码语法检查（`execution.py:1014` → `syntax_check_paths`，只认 `edit_files/write_file/edit_lines/apply_patch` 四种参数形态，见 `tools/syntax_check.py:28-48`），混入 Office 工具属语义错位。新建独立 `_OFFICE_EDIT_TOOLS` 集合，挂独立的"重开验证"分支；plan-first 门控不需要任何动作——它来自"不在 `_READ_ONLY_TOOLS`/`_NO_PLAN_TOOLS` 白名单"（`constants.py:56/82`），对新写工具自动生效；
- diff 形态：docx 按 op 逐条给"段落原文 → 新文本"文本对照（前端复用现有 DiffView）；xlsx 给"`Sheet1!B3: 100 → 250`"行级列表；fill_template 给"key → 值"清单 + 命中位置数；
- 改后自验证（对应代码工具的 syntax check 环节）：子进程内重新用 python-docx/openpyxl 打开产物文件，断言——ops 全部生效、`missed` 为空或已声明、公式单元格 `data_type == 'f'` 保持、sheet 数量符合预期；验证失败则回滚（覆盖回 `.bak`）并报错，绝不交付半成品。

### 5.5 结果 JSON 统一契约

```jsonc
{
  "success": true,
  "message": "已更新 3 处，生成副本 documents/edited/周报_20260906_1530.docx",
  "output_path": "documents/edited/周报_20260906_1530.docx",
  "backup_path": null,            // workspace 内原地编辑时才有
  "source_path": "/Users/x/Desktop/周报.docx",   // 外部文件时返回原路径
  "ops_applied": ["replace_text", "set_table_cell"],
  "hits": 3,
  "missed": [],                   // 未命中的定位目标
  "cross_run": 1,                 // 跨 run 替换次数（格式可能简化）
  "warnings": ["B7 为合并单元格，已写入左上角锚点 B7"],
  "verified": true                // 改后重开验证是否通过
}
```

`missed` 非空且 `success: true` 不可同时出现——有未命中即视为失败（事务中止），Agent 据此决定澄清或修正。

### 5.6 意图门控决策：编辑工具常驻，不进 `_CONTENT_TOOLS`

`tools.py:53` 的 `_CONTENT_TOOLS` 把 `word_document/presentation/spreadsheet` 门控在 `"document"` 意图（命中才注入，省 input token：全量 ≈13.3k、裁后 ≈7k）。新工具**不跟随**这个门控：

- 编辑请求多以口语出现（"帮我改下这份周报"），意图漏判时工具被裁掉，模型只能退回"整份重新生成"——恰好复刻本方案要消灭的旧模式；
- `tools.py` 注释的既有保守原则（"干活主力工具一律常驻，避免意图漏判导致工具缺失"）同样适用于编辑工具；
- 代价是每次云端调用多 4 个 schema 的 token（四个工具 schema 都小，远低于 pdf_generate 的 889 token），可接受。

既有影响：word_document 等生成工具的门控与行为不变，但 prompt 指引（§6）会把"修改已有文档"的流量从"重新生成"分流到编辑工具——这是预期变化。

## 6. 代码落点清单

| 层 | 文件 | 动作 |
| --- | --- | --- |
| docgen | `app/docgen/word/editor.py` | 新增：run 级替换引擎 + op 执行器（纯函数） |
| docgen | `app/docgen/xlsx_editor.py` | 新增：openpyxl op 执行器 |
| docgen | `app/docgen/outline.py` | 新增：document_outline 读取逻辑（python-docx / openpyxl 双实现） |
| tools/scripts | `edit_docx.py`、`edit_xlsx.py`、`fill_template.py`、`document_outline.py` | 新增：子进程脚本，JSON in/out（对齐 word_document.py 模式） |
| tools/adapters | `edit_docx.py`、`edit_xlsx.py`、`fill_template.py`、`document_outline.py` | 新增：参数 schema 与工具描述；前三个设 `allow_external_paths = True` |
| agent | `app/agent/tools/execution.py` | 新增 `_OFFICE_EDIT_TOOLS` 集合与独立"重开验证"分支；**不改** `_EDIT_TOOLS` 及现有语法检查路径 |
| agent | `app/agent/core/constants.py` | `document_outline` 进 `_READ_ONLY_TOOLS`（免 plan-first）与 `_NO_PLAN_TOOLS`；三个写工具不进任何白名单（自动获得 plan-first） |
| agent | `app/agent/tools/tools.py` | `document_outline` 进 `_LOCK_FREE_TOOLS`（可并行）；三个写工具**不进** `_CONTENT_TOOLS` 意图门控（见下） |
| agent | `app/agent/tools/execution.py` | `_OFFICE_EDIT_TOOLS` 改后检查分支对 Office 工具走"重开验证" |
| tools | `app/tools/adapters/undo_turn.py` 及快照记录 | 补 `data_dir/backups/` 恢复分支 |
| agent | `app/agent/core/prompt_sections.py` | 补工具选择指引（§7） |
| 前端 | 无新组件 | 确认卡/文件列表复用 `ToolConfirmSection` / `ToolFileList`；diff 复用 DiffView |

`prompt_sections.py` 指引草案：

> 修改用户已有文档时优先使用编辑工具而非重新生成：填空（合同/通知函）用 fill_template；改 Word 内容用 edit_docx（先 document_outline 查看结构，再给 ops）；改 Excel 数据用 edit_xlsx。整份文档的结构/样式需要重做时才用 word_document/spreadsheet 重新生成。外部路径文件会生成编辑副本，不会动用户原文件。

## 7. 分期计划

| 期 | 内容 | 工作量 | 出口标准 |
| --- | --- | --- | --- |
| 一 | `editor.py` 替换引擎 + `fill_template` + `edit_docx`（5 个 op）+ `document_outline`(docx) + `.bak`/undo 分支 | 3–4 天 | 用真实周报/合同 docx 走通"outline → edit → 确认 → 验证 → undo"全链路；单测全绿 |
| 二 | `edit_xlsx`（4 个 op）+ `document_outline`(xlsx) + `replace_text` 的 `all`/regex 收尾 + 图片往返冒烟 | 2–3 天 | 真实多 sheet 财务表追加数据 + 合计公式，图表无损 |
| 三 | `edit_pptx` 文本替换、`.doc` 拒绝引导文案、前端确认卡 Office diff 文案打磨 | 2–3 天 | PPT 改标题/数字场景可用 |

## 8. 测试计划

| 文件 | 必测点 |
| --- | --- |
| `tests/test_word_editor.py` | 单 run 替换样式保留（断言 run.font.bold 不变）；跨 run 替换合并策略；全角/半角归一；`all` 参数；表格 header+row_key 定位；事务中止不写盘 |
| `tests/test_fill_template.py` | 正文/表格/页眉命中；`list_values` 模板行展开；`missing_keys` 报告 |
| `tests/test_xlsx_editor.py` | 公式保留断言（`data_type == 'f'`）；图表往返冒烟；合并单元格锚点改写；`append_rows` 末行探测 |
| `tests/test_document_outline.py` | docx 段落/表格清单与 python-docx 实际结构一致；xlsx dims/headers 解析 |
| `tests/test_office_undo.py` | 备份落 `data_dir/backups/` 的创建/恢复/保留 3 份；外部文件副本路径不污染原文件；既有 `undo_last_turn` 文本文件恢复路径回归 |
| `tests/test_tool_registration.py`（或就近注册测试） | 三个写工具不在 `_READ_ONLY_TOOLS`/`_CONTENT_TOOLS`；`document_outline` 在 `_READ_ONLY_TOOLS`/`_LOCK_FREE_TOOLS`/`_NO_PLAN_TOOLS` |

## 9. 风险与对策

| 风险 | 等级 | 对策 |
| --- | --- | --- |
| 模型定位错段落/单元格 | 中 | 内容匹配优先 + 最相近候选提示 + 改前 diff 确认 + 事务性（任一步失败整体不写盘） |
| 加密/损坏文件 | 低 | 子进程隔离；报错文案区分"已加密"与"已损坏"，不静默失败 |
| xlsx 嵌入图片往返丢失 | 低（未实测） | 期二补冒烟断言；若确有丢失，警告用户"编辑后请检查图片" |
| 跨 run 替换导致局部格式简化 | 中 | `cross_run` 如实上报；文档里向用户说明 |
| 表格模板行展开样式错乱（fill_template） | 中 | 复制模板行的 `trPr`/run 样式；测试用例覆盖三行以上展开 |
| 大文件性能 | 低 | python-docx/openpyxl 对 50MB 内文件可接受；子进程 + 60s 超时兜底 |

## 10. 已验证的技术事实（2026-09-06，本机 .venv 实测）

1. openpyxl 3.1.5：带 BarChart 与 `=SUM()` 公式的 xlsx，经 load → 改单元格 → save 往返后，chart XML 部件完整幸存、公式原样保留——"openpyxl 编辑丢图表"的旧结论在当前依赖版本下**不成立**，`edit_xlsx` 无硬阻碍；
2. python-pptx / python-docx 基于未知 XML 保留机制，未触碰的部分往返无损（库设计保证，实施时以单测固化）；
3. `_EDIT_TOOLS`（`execution.py:30`）全后端仅一个消费点：`execution.py:1014` 的执行后语法检查；`edited_paths()`（`tools/syntax_check.py:28-48`）对未知工具名返回空列表。Office 工具走独立 `_OFFICE_EDIT_TOOLS`，现有四个编辑工具的语法检查路径零改动；
4. plan-first 门控与 `_EDIT_TOOLS` 无关，来自"不在 `_READ_ONLY_TOOLS`/`_NO_PLAN_TOOLS`"（`constants.py:56/82`），新写工具自动获得；
5. Rust 侧工作区文件树（`src-tauri/src/commands/workspace.rs`）**无点前缀/隐藏文件过滤**——workspace 内的备份文件会漏进前端文件面板并触发 watch 事件，故备份定址 `data_dir/backups/`（§5.3）；
6. 意图裁剪白名单 `_CONTENT_TOOLS`（`tools.py:53`）现状：word_document/presentation/spreadsheet 挂 `"document"` 意图；全量工具 ≈13.3k token、裁后 ≈7k。编辑工具常驻的 token 代价见 §5.6。


## 附录：实施记录（2026-09-06）

与本文设计的差异与最终落点：

1. **`_OFFICE_EDIT_TOOLS` = {fill_template, edit_docx, edit_xlsx, edit_pptx}**（execution.py），
   独立于 `_EDIT_TOOLS`，不接代码语法检查；产物"重开验证"在脚本内完成（office_files.verify_output）。
2. **备份位置** `data_dir/backups/<session_id>/`（office_backup.py）：manifest.jsonl 逐条记录，
   恢复按批次（同一 ts）、恢复即消费，连续 undo 可逐批回溯（无 redo）；每原件保留 3 份。
3. **编辑工具常驻注入**（不进 `_CONTENT_TOOLS`），`document_outline` 进 `_READ_ONLY_TOOLS`
   （经 frozenset 并集自动获得 `_LOCK_FREE_TOOLS` 免锁并行）。
4. **xlsx 编辑引擎**落在 `docgen/xlsx_editor.py`（设计文档写的是 docgen/xlsx_editor.py，一致）；
   `add_sheet` 复用 spreadsheet.py 的 `_style_header_cell/_style_data_cell/_coerce_cell`；
   日期字符串经 `_coerce_cell` 转 Excel 原生 date（生成器既有行为）。
5. **PPT 编辑引擎**落在 `docgen/ppt/editor.py`：replace_text（run 级保格式、递归组合形状与
   表格内文本、页范围限定）+ set_title；只动文本不碰母版。
6. **office_files.resolve_office_path** 以 kind 参数（doc/sheet/slide）统一三格式校验，
   `.doc` 一律拒绝并引导转换。
7. 期三实施中修复一处引擎 bug：pptx 单 run 命中误走多 run 路径导致文本被清空
   （last_run 与 first_run 为同一对象时后缀赋值覆盖替换结果）——以
   test_replace_cross_run_keeps_first_run_format 等用例固化回归。
