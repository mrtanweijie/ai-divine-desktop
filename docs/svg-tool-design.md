# SVG 工具设计

> 版本：v1.0
> 日期：2026-08-11
> 状态：已实现
> 关联模块：`divine-server/app/tools/adapters`、`divine-server/app/tools/scripts`、`divine-server/app/agent.py`

## 1. 背景与目标

AI 在生成 SVG 矢量图时，目前缺少从“创建”到“局部修改”再到“导出位图”的完整工具链。本设计补齐四个工具，让模型可以：

- 首轮用 `draw_svg` 从零生成 SVG。
- 后续修改时基于现有 SVG 用 `edit_svg` 做局部更新，不重新生成。
- 需要理解当前 SVG 时用可选的 `describe_svg` 获取结构摘要。
- 用户要求导出位图时用 `svg_to_png` 得到 PNG。

核心约束是“可继续编辑”：生成 SVG 时给关键元素打语义化 id，后续所有修改都通过 id 精确定位。

## 2. 工具契约

### 2.1 draw_svg

用途：从零生成 SVG。

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `content` | string | 完整合法 SVG 源码，必填，不要带围栏代码块 |
| `title` | string | 标题，用于生成文件名，可选 |
| `file_name` | string | 指定文件名，可选 |
| `path` | string | workspace 内相对目录，默认 `svg` |

行为：解析并校验 SVG 根元素，写入 `svg/` 输出目录，返回画布尺寸、元素数量、关键 id。

### 2.2 edit_svg

用途：基于现有 SVG 修改。

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `file_path` | string | 当前 SVG 文件路径，必填 |
| `content` | string | 完整更新后的 SVG 源码，必填 |

行为：读取并校验现有 SVG，再把完整更新后的 SVG 写回同一文件。只改用户指令提到的元素，其他元素、属性、层级和顺序保持原样。

### 2.3 describe_svg

用途：让模型先“看懂”当前 SVG，可选。

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `file_path` | string | 当前 SVG 文件路径，必填 |
| `include_source` | boolean | 是否返回完整源码，默认 false |

行为：返回画布尺寸、元素清单、关键 id、关键属性和结构摘要。

### 2.4 svg_to_png

用途：将最终 SVG 导出为 PNG。

参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `file_path` | string | 当前 SVG 文件路径，必填 |
| `output_path` | string | 输出 PNG 路径，可选 |
| `width` | integer | 目标宽度，可选 |
| `height` | integer | 目标高度，可选 |

行为：优先使用 `resvg_py` 渲染，其次尝试 `cairosvg` / `svglib`；macOS 上无可用 Python 渲染后端时回退到系统 `qlmanage`。

## 3. Agent 规则

### 3.1 触发规则

1. 首轮用户要求画 SVG / 图标 / 插画 → 用 `draw_svg`。
2. 后续修改 → 用 `edit_svg`，不要重新生成。
3. 用户说“导出 / 转 PNG / 我要位图” → 用 `svg_to_png`。
4. 生成或编辑 SVG 时不要加解释，只输出代码。
5. 给关键元素打 id（`eye-left`、`hair`、`body` 等），方便后续修改。

### 3.2 Prompt 模板

```text
用户要求生成/绘制 SVG 矢量图、图标、插画、角色或自定义图形时：
- 首轮从零生成使用 draw_svg，后续修改必须使用 edit_svg，不要重新生成；
- 需要先理解当前 SVG 时可用 describe_svg；
- 用户说“导出/转 PNG/我要位图”时使用 svg_to_png；
- edit_svg 的 file_path 传当前 SVG 文件路径，content 传完整更新后的 SVG 源码；
- 只改用户指令中提到的元素，其他元素保持原样；
- 生成或编辑 SVG 时正文不要加解释，只输出 SVG 代码；
- 关键元素必须带简短、语义化、唯一的 id。
```

## 4. 安全与稳定性

| 风险 | 对策 |
| --- | --- |
| 模型生成非 SVG 内容 | 工具解析根元素，失败时报错不落盘 |
| 修改时误改无关元素 | Agent 规则要求只改指令提到的 id，并传完整更新源码 |
| SVG 过大 | 限制 60000 字符 |
| 导出工具不可用 | 优先 `resvg_py`，macOS 回退 `qlmanage`，仍失败时给出明确错误 |
| 外部路径访问 | `edit_svg` / `describe_svg` / `svg_to_png` 访问外部路径时走现有确认流程 |

## 5. 验收标准

- 对话中首轮要求“画一个机器人”会调用 `draw_svg` 并生成带 id 的 SVG。
- 后续“把眼睛改大”会调用 `edit_svg`，其他元素保持不变。
- “导出成 PNG”会调用 `svg_to_png` 并生成 PNG 文件。
- 生成的 SVG 文件可在工作区文件面板查看。
- `npx tsc --noEmit` 和后端工具脚本冒烟测试通过。
