# Release Notes

## v0.2.0

### 新增工具

- **edit_lines**：行号范围编辑（replace/delete/insert），作为 SEARCH/REPLACE 的确定性 fallback
- **apply_patch**：unified diff 应用（多文件、上下文定位、空白容错、`/dev/null` 创建新文件）
- **list_definitions**：代码文件结构大纲（Python AST 精确解析 + ts/js/rs/go/java 正则启发式）
- **move_file**：workspace 内移动/重命名文件或目录
- **glob_files**：文件模式匹配（gitignore 支持）
- **format_code**：代码格式化（ruff/prettier 自动识别）
- **lint_check**：静态代码检查（ruff/mypy/eslint/tsc 自动识别）
- **run_tests**：测试运行（pytest/jest 自动识别）

### 子 Agent 增强

- 可写子 Agent 支持终端类任务（`terminal=true`）
- 子 Agent 终端白名单：run_tests/lint_check/format_code + raw terminal
- 安全策略：safe-policy-only（子 Agent 不能触发 confirm/block）

### 性能优化

- SQLite WAL + synchronous=NORMAL 模式，写入吞吐提升 3-5 倍
- ToolMessage 深度压缩（字符串 >400 字符截断、列表 >50 项截断），上下文利用率提升 70%
- 数据库操作异步化（asyncio.to_thread），事件循环响应延迟降低 90%
- SSE 负载深度截断（递归处理，前端渲染流畅）
- ReAct 限制放宽（8192 → 65536）

### 前端改进

- 工具分组扩展：git/bg/list_definitions/memory 系列连续调用自动合并显示
- read_file 文件列表：标题点击展开/收起，收起时无背景条
- grep_files 连续调用合并显示
- 新增 11 个工具图标映射（git/bg/list_definitions/memory 系列）

### 编码工具链完善

- edit_files 重构：独立提交（单文件失败不影响其他）、difflib 模糊匹配、EOL 保护
- 三种编辑路径：SEARCH/REPLACE（语义精确）/ 行号范围（确定性 fallback）/ unified diff（多文件批量）
- 验证闭环：lint_check → run_tests → format_code → git_diff

## v0.1.9

- 提供方模型管理重构：按提供方（DeepSeek / Xiaomi / GLM / MiniMax / OpenAI / Qwen / 自定义）统一管理模型配置，对话框按提供方分组切换全部模型，支持自定义模型（逗号分隔去重）
- MiMo 多模态支持：项目配置 MiMo 模型时直接使用其多模态能力
- 图片识别优化：GLM 免费视觉模型优先，繁忙时自动回退会话模型；会话模型不支持图片时列出配置里可切换的视觉模型；修复 MiniMax 系列（M3 等）多模态识别误判
- 图片生成工具：MiniMax image-01 文生图 / 图生图，文生图支持比例选择卡片，图生图自动读取参考图原始比例；prompt 超长先经 LLM 精简、再自动截断兜底
- 推理模型思考过程：MiniMax-M3 / GLM-5.x 的 think 标签增量流式展示，支持折叠查看
- Markdown 相对路径图片渲染：`![alt](images/xxx.png)` 本地图片直接显示（workspace / 输出 / 项目目录），加载失败自动隐藏
- 工具稳定性：重复 tool_call id 自动去重（修复 MiniMax 历史消息拒绝）、工具进度回调修复、GLM-5.x 文本旗舰强制思考
- UI 修复：启动页浅色主题背景、grep_files 工具图标

## v0.1.6

- 多模型配置：模型切换、余额查询、样式拆分；支持 deepseek-v4-flash-vision-exp 视觉模型
- 图片识别：配置 GLM 时优先使用免费视觉模型，未配置时回退 deepseek-v4-flash-vision-exp；
  支持在对话框直接发送图片链接识别，仅接受图片格式 URL
- 输入框支持粘贴截图与任意文件（file:// 路径直接引用、无路径时本地保存）
- PDF/图片内联预览：图片 base64 直显，PDF 用 PyMuPDF 逐页渲染为高清图，替代 webview 原生查看器
- 图表生成优化：饼图圆环样式（细环、环外标签、无白缝圆角）、数据来源说明排版、
  背景跟随主题；兼容 ECharts 6 数据格式
- 长期记忆与会话上下文压缩：长会话自动折叠为摘要，输入框上下文用量环实时展示
- token 消耗统计：每条回复 / 会话累计 / 项目累计（API 真实用量，缺失时本地估算，千/百万级展示）
- 用户主动选择或粘贴的附件免外部文件访问确认
- 新对话引导页接入 DivineBall 待机动画球（害羞表情、目光跟随鼠标）
- PDF 报告：自定义 HTML 封面、封面风格词、长标题自动换行
- 多项 UI 修复：消息复制按钮 hover 显隐、选项卡片标题换行、文件预览空状态图标等

## v0.1.2

- 支持同时多对话切换
- 修复对话滚动问跳动题
- 修复暂停对话无响应问题

## v0.1.1

- 修复一些已知问题
- 优化桌面端性能
- 对话区域新增缩略列，支持 hover 预览与点击定位
- SSE 回复 SVG/HTML 预览

## v0.1.0

- 初始版本
