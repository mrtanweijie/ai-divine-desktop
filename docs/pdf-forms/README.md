# PDF 表单模板库

面向 `PDF_FORM_GENERATE` 工具的表单模板参考集。位于 `docs/pdf-forms/`。

## 文件

| 文件 | 说明 |
| --- | --- |
| `00-index.html` | 模板导览 + 字段协议 + design tokens 速查 |
| `forms.css` | 共享样式层（tokens / 控件 / 表格 / 签名 / print 规则） |
| `tagger.js` | 字段名标注器，浏览器预览用，`@media print` 下完全隐藏 |
| `01-application.html` | 事项申请表 — 分节流式 + 下划线填空 + 三级审批 |
| `02-registration.html` | 员工信息登记表 — 网格表格 + 子表 + 声明签字 |
| `03-survey.html` | 满意度调查问卷 — 量表矩阵 + NPS + 开放题 |
| `04-expense.html` | 费用报销单 — 可重复明细表 + 金额合计 + 收款 + 审批 |

## 字段协议

任一可填写单元用 4 个属性自描述，HTML 即 schema 源，无需额外 JSON：

```
data-field    字段唯一名（snake_case），生成 AcroForm 时直接作为字段名
data-type     text | textarea | number | money | date | select | radio | checkbox
              | rating | nps | signature | table | group
data-label    中文标签 → AcroForm 的 tooltip / 无障碍标签
data-required true 时渲染必填星号，生成 PDF 时置 required
```

附加属性：`data-checked`（选项预填状态）、`data-repeatable`（明细表可动态扩行）。

检视方式：浏览器打开任一模板 → 右上角「字段名标注」；或在控制台读 `window.__PDF_FORM_SCHEMA__`。

## 工具接入建议

1. **解析**：用 lxml/BeautifulSoup 选 `[data-field]`，读 4 个属性得到字段清单。
2. **定位**：取元素的 bounding box（渲染后）→ 换算为 PDF 坐标，放置 AcroForm 控件。
3. **渲染**：HTML → PDF 建议 WeasyPrint 或 Chromium `--print-to-pdf`，需开启
   `print-color-adjust: exact`，否则背景色（表头、审批栏、NPS 选中态）会丢失。
4. **换肤**：改 `<html data-theme="...">`，已内置 `minimal`（默认）/`corporate`/`tech`/`forest`，
   变量体系与 `docs/pdf-modules` 一致，可直接追加该库的 11 主题变量。

## 排版约定

- A4 210×297mm，页边距 15–16mm，`@page { size: A4; margin: 0 }`
- 12 列栅格 `.col-1` ~ `.col-12`，间距 10px
- 控件标准高度 40px（`--field-h`），紧凑 32px，圆角 6px，勾选框 15px
- 字号：标题 22 / 分节 15 / 标签 12 / 正文 12.5 / 辅助 11 / 页脚 9.5
- 超长表单在 `.form-section` 上加 `break-inside: avoid` 可避免跨页断裂
