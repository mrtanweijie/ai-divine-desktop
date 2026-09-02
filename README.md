# Divine

Divine：本地优先、隐私可控的桌面 AI 助手。后端为 FastAPI sidecar，前端为 Vite + React + TypeScript，桌面壳为 Tauri 2 + Rust。

默认端口约定：

| 服务 | 端口 | 说明 |
| --- | --- | --- |
| FastAPI sidecar | `8019` | Agent、SSE、SQLite、工具系统 |
| Vite dev server | `8010` | 前端开发服务，`/api` 代理到 sidecar |

## 功能特性

- 多模型对话：DeepSeek 流式对话（深度思考），支持多模型配置与按会话切换；无 Key 时自动降级本地演示 Agent
- 会话能力：会话历史、标题自动生成、会话搜索（含拼音检索）、项目化组织（项目工作区/图标）
- 会话记忆：长期记忆（偏好/事实/事件，写入时去重、纠正时自动过期）+ 会话内历史回溯（提问窗口外问题时自动检索早期对话并注入）
- 本地文件分析：Word、Excel、Markdown、PDF、图片识别（GLM 视觉）、网页抓取（JS 动态页自动浏览器兜底）、批量抓取、联网搜索
- 文档与可视化生成：Word、PPT、Excel、PDF（报告/商业分析/旅行/路线图/书/幻灯片配方）、Markdown、SVG 矢量图、ECharts 图表、Mermaid 图、完整 UX 交互 HTML
- 本地 RAG：工作区文档自研 SQLite 倒排索引检索（词频 + doc_freq，无需 embedding 模型）
- 技能系统：安装/迁移/预览第三方 SKILL.md 技能（GitHub/Gitee），内置技能中心
- MCP 连接器：配置并连接外部 MCP server，工具自动并入 Agent（隐私：连接结果需信任授权）
- 本地模型（可选）：llama-server 驱动的意图识别、长文本预整理与本地问答，数据不出本机
- 计划与审批：复杂任务先建待办计划，高危操作（终端命令、git 提交、文件改动）请求用户确认
- 定时任务与日程：提醒、定时任务、日历事件，macOS 可同步系统日历
- 后台任务与子代理：dev server/长任务后台运行并可查状态；大任务并行拆分给多个子 Agent
- 交互式终端、Markdown 渲染与 Shiki 代码高亮
- SQLite 本地存储，数据默认保存在本机，不依赖云端账号
- 快捷键：应用内统一 keymap（macOS ⌘ / 其他平台 Ctrl），系统级全局快捷键唤起/隐藏窗口
- Tauri 2 + Rust 桌面壳：启动自动拉起并监控 FastAPI sidecar（掉线重启）
- 自研 React UI 组件，不引入 AntD

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | FastAPI、Uvicorn、SQLite（自研倒排索引检索）、LangChain + LangGraph Agent、多模型（DeepSeek/GLM/MiniMax）、llama-server 本地模型、PyInstaller |
| 前端 | Vite、React 19、TypeScript、react-markdown、Shiki、ECharts、自研组件 |
| 桌面壳 | Tauri 2 + Rust，sidecar 生命周期管理、托盘、macOS Calendar 桥接 |

## 目录结构

| 目录 | 说明 |
| --- | --- |
| `divine-server` | FastAPI sidecar：API、Agent、SSE、SQLite、工具系统 |
| `divine-server/app/agent` | Agent 编排（LangGraph）、prompt、工具执行、意图裁剪与 SSE 拆分 |
| `divine-server/app/api` | HTTP/SSE/WebSocket 路由（chat、settings、mcp、skills、local_llm 等） |
| `divine-server/app/db` | SQLite 连接、迁移与按领域拆分的仓储（含自研检索原语） |
| `divine-server/app/docgen` | 文档生成（PDF/Word/PPT/图表/简历等渲染器） |
| `divine-server/app/llm` | LLM provider、DSML 流解析与 LangChain 适配 |
| `divine-server/app/mcp` | MCP server 连接管理（stdio/SSE） |
| `divine-server/app/skills` | SKILL.md 技能注册与执行 |
| `divine-server/app/tools/adapters` | 工具注册与参数定义 |
| `divine-server/app/tools/scripts` | 工具子进程脚本 |
| `divine-server/evals` | 独立评测 harness（fake_model + scenarios，agent 离线验证） |
| `divine-app` | Vite + React + TypeScript 前端，自研组件 |
| `divine-app/src-tauri` | Tauri 2 + Rust 桌面壳 |
| `docs` | 项目方案文档 |
| `scripts` | macOS 签名与公证脚本 |

## 快速开始

### 1. 启动后端

需要 Python 3.12+（代码使用了 3.12 f-string 语法），开发环境当前使用 Python 3.14。

```bash
cd divine-server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

后端启动后可通过 <http://127.0.0.1:8019/api/health> 检查健康状态。未配置 `DEEPSEEK_API_KEY` 时，`AI_PROVIDER=auto` 会使用本地演示 Agent；填入 Key 后自动切换为真实 DeepSeek 流式对话。

开发时用 `python run.py`；`python entry.py` 模拟打包后的 sidecar 启动方式，并把日志写入数据目录下的 `divine-server.log`，PyInstaller 也以 `entry.py` 为入口。

### 2. 启动前端

需要 Node.js 20+ 和 pnpm 9+。

```bash
cd divine-app
pnpm install
pnpm dev
```

浏览器访问 <http://localhost:8010>，Vite 会把 `/api` 请求代理到 `http://127.0.0.1:8019`。

### 3. 桌面开发

Tauri 会自行拉起并监控 sidecar，但需要先为本机平台生成 sidecar 可执行文件：

```bash
cd divine-server
pip install -r requirements.txt pyinstaller
bash build-sidecar.sh        # 自动检测当前平台

cd ../divine-app
pnpm install
pnpm tauri:dev
```

## 环境变量

### divine-server

配置文件为 `divine-server/.env`，参考 [.env.example](divine-server/.env.example)。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek OpenAI 兼容接口地址 |
| `DEEPSEEK_API_KEY` | 空 | DeepSeek API Key |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | DeepSeek 模型名 |
| `AI_PROVIDER` | `auto` | `auto` 有 Key 时用 DeepSeek，否则用本地演示；`mock` 强制本地演示；`langchain` 使用 LangChain DeepSeek |
| `GLM_BASE_URL` | `https://open.bigmodel.cn/api/paas/v4` | GLM 视觉模型地址 |
| `GLM_API_KEY` | 空 | GLM API Key，用于 `read_image` |
| `GLM_MODEL` | `glm-4.6v-flash` | GLM 视觉模型名 |
| `HOST` | `127.0.0.1` | sidecar 监听地址 |
| `PORT` | `8019` | sidecar 监听端口 |
| `CORS_ORIGINS` | `http://localhost:8010,...` | 逗号分隔的允许来源 |
| `DIVINE_DATA_DIR` | `divine-server/data` | 数据目录：数据库、`settings.json`、日志 |
| `DIVINE_WORKSPACE_DIR` | `divine-server/workspace` | 工作区根目录 |
| `DIVINE_PROJECTS_DIR` | 空 | 预留的项目根目录变量，当前代码未使用 |
| `DB_PATH` | `<data_dir>/ai_workspace.db` | SQLite 数据库路径 |

#### 多模型配置

`settings.json` 支持配置多个模型（在设置 → 模型里维护，也可手改文件）：

```json
{
  "models": [
    {
      "id": "default",
      "name": "DeepSeek V4 Flash",
      "provider": "auto",
      "model": "deepseek-v4-flash",
      "base_url": "https://api.deepseek.com",
      "api_key": "sk-...",
      "active": true
    }
  ]
}
```

- `active` 为 `true` 的条目是默认模型，同时会镜像到顶层 `provider` / `model` / `base_url` / `api_key` 字段，保持与旧配置兼容。
- 对话时可在输入框发送按钮左侧的模型选择器中按会话切换模型（每个会话记住各自的模型选择，未选择时用默认模型）。
- `provider`：`auto`（有 Key 用 DeepSeek，否则本地演示）、`langchain`（LangChain DeepSeek）、`mock`（本地演示）。
- 网络参数（可选手动编辑 `settings.json`）：`max_retries`（请求重试次数，默认 2）、`timeout`（请求超时秒数，默认跟随 openai 客户端）；可写在顶层或某个模型条目内，provider 初始化时会输出一条含生效值的日志。

桌面端启动 sidecar 时会注入 `DIVINE_DATA_DIR` 和 `DIVINE_WORKSPACE_DIR`，指向系统应用数据目录，因此打包后不会依赖仓库内的 `data/` 和 `workspace/`。

普通字段优先读取 `data/settings.json`，未保存时回退到环境变量或默认值；`HOST` 和 `PORT` 始终以环境变量为准。UI 中的设置会写入 `settings.json`，`DIVINE_WORKSPACE_DIR` 只在设置中未指定工作区时生效。

### divine-app

前端使用模式对应的 env 文件：

| 文件 | 模式 | 使用场景 |
| --- | --- | --- |
| `.env.dev` | `dev` | `pnpm dev`、`pnpm tauri:dev` |
| `.env.test` | `test` | `pnpm build:test`、`pnpm tauri:build:test` |
| `.env.prod` | `prod` | `pnpm build`、`pnpm tauri:build:prod` |

| 变量 | 说明 |
| --- | --- |
| `VITE_SERVICE_API_URL` | sidecar API 地址，默认 `http://127.0.0.1:8019/api` |
| `VITE_DISABLE_CONTEXT_MENU` | 正式包禁用 WebView 右键菜单 |

## 工具系统

当前注册 62 个工具（随 MCP/技能动态增减），按名称排序：

| 工具 | 用途 |
| --- | --- |
| `apply_patch` | 应用 unified diff 补丁（多文件/新建），允许行号漂移与空白容错 |
| `bg_kill` / `bg_output` / `bg_status` | 后台任务：停止、读取最近输出、查看状态 |
| `calculator` | 安全计算数学表达式 |
| `clipboard` | 读取、写入、清空系统剪贴板 |
| `create_plan` | 为复杂任务创建待办计划 |
| `describe_svg` | 读取现有 SVG，返回画布、元素、关键 id 与结构摘要 |
| `directory_tree` | 查看目录树结构（忽略 .gitignore/node_modules） |
| `discover_importable_skills` | 扫描本机其他 AI 工具已安装的技能，列出可迁移候选 |
| `draw_svg` | 从零生成 SVG 矢量图/图标/插画 |
| `edit_files` | 按 SEARCH/REPLACE 批量修改/创建文件（SEARCH 需精确匹配） |
| `edit_lines` | 按行号范围精确编辑单个文件 |
| `edit_svg` | 基于现有 SVG 局部修改，只动用户提到的元素 |
| `forget_memory` | 删除一条长期记忆（用户纠正"记错了"时） |
| `format_code` | 代码格式化（ruff format / prettier 自动识别） |
| `generate_chart` | 生成 ECharts 图表并在对话中内联展示 |
| `git_commit` / `git_revert` | 提交改动 / 还原未提交改动（均需确认） |
| `git_diff` / `git_log` / `git_status` | 查看未提交 diff / 提交历史 / 仓库状态 |
| `glob_files` | 按 glob 模式匹配文件（`**` 递归），新→旧排序 |
| `grep_files` | 按内容搜索文本文件（正则），返回行级命中 |
| `image_generate` | 文生图/图生图（MiniMax 与 GLM-Image 后端） |
| `image_resize` | 缩放本地图片 |
| `install_skill` | 从 GitHub/Gitee 安装 SKILL.md 技能 |
| `lint_check` | 静态检查（ruff/mypy/eslint/tsc 自动识别），返回结构化问题 |
| `list_definitions` | 代码文件结构大纲（类/函数 + 起始行号） |
| `mermaid_export` | 把 Mermaid 源码保存为 `.mmd` 文件 |
| `migrate_skill` / `migrate_skills` | 把本机发现的技能迁移到 AI Divine（单个/批量） |
| `move_file` | workspace 内移动/重命名文件或目录 |
| `notes` | 生成 Markdown 笔记 |
| `pdf_generate` | 统一 PDF 生成入口（报告/商业/旅行/路线图/书/幻灯片配方） |
| `pdf_render` | 把 Markdown 渲染为排版 PDF（weasyprint，失败自动转 reportlab 富渲染） |
| `pdf_split_merge` | 拆分、合并 PDF |
| `presentation` | 生成 PPT（14 种版式） |
| `preview_skill_repo` | 只读预览远程仓库中的 SKILL.md 后再决定安装 |
| `rag_index` | 扫描工作区文本并建立本地索引 |
| `rag_search` | 在工作区本地索引中检索相关内容（自研倒排，非向量库） |
| `read_file` | 读取文本/Office/PDF/表格等；支持行号分段 |
| `read_image` | 用 GLM 视觉模型识别图片（本地路径或 URL） |
| `remember` | 保存用户稳定的偏好/事实/事件到长期记忆（自动去重与过期） |
| `review_changes` | 对工作区未提交改动做自动 code review，输出问题清单 |
| `run_subagents` | 把大任务拆成独立子任务，并行委托子 Agent 并汇总 |
| `run_tests` | 运行自动化测试（pytest/jest/vitest 自动识别），返回失败列表 |
| `schedule_task` | 创建定时提醒/定时任务 |
| `search_files` | 按文件名/路径关键字搜索工作区文件 |
| `spreadsheet` | 生成带专业样式的 Excel（主题/斑马纹/冻结表头/自动筛选） |
| `sqlite_query` | 只读查询本地 SQLite（仅 SELECT/PRAGMA/WITH） |
| `svg_to_png` / `svg_to_png_batch` | SVG 导出 PNG / 批量导出多尺寸（iOS/Android 图标） |
| `terminal` | 执行终端命令，高危命令需确认；会话内工作目录延续 |
| `undo_last_turn` | 撤销 Agent 最近的文件改动（恢复快照） |
| `ux_html` | 保存 Agent 设计的完整 UX 交互 HTML，可文件面板预览 |
| `web_fetch` / `web_fetch_batch` | 抓取网页/批量抓取，JS 动态页自动浏览器兜底，可监听数据接口取 JSON |
| `web_search` | 联网搜索，返回标题/链接/摘要 |
| `word_document` | 生成 Word 文档（标题/表格/图片/代码块等元素） |
| `write_calendar` | 写入日程/日历事件 |
| `write_file` | 创建/写入 workspace 内文本文件 |

工具行为的两条默认：输出路径必须落在 workspace 内（越界拒绝）；高危操作（terminal、git 提交/还原、文件改动等）一律先征求用户确认。

## API

| 路由 | 说明 |
| --- | --- |
| `POST /api/stream_chat` | SSE 流式对话 |
| `GET /api/health` | 健康检查，返回 provider、model、工具数量 |
| `/api/sessions` | 会话管理 |
| `/api/projects` | 项目管理 |
| `/api/scheduled-tasks` | 定时任务管理 |
| `/api/calendar-events` | 日程管理 |
| `/api/files` | 工作区文件列表与下载 |
| `/api/settings` | 运行时设置（含多模型、MCP 配置） |
| `/api/mcp` | MCP server 状态查询与连接测试 |
| `/api/skills` | 技能（SKILL.md）安装与管理 |
| `/api/local_llm` | 本地模型（llama-server）状态、启停与模型管理 |
| `/api/pdf-themes` | PDF 主题管理 |
| `/api/git` | git 操作入口 |
| `WS /api/terminal` | 交互式终端 |
| `POST /api/terminal/decide` | 审批待确认的终端命令 |

错误响应统一为 `{"detail": ...}`：业务校验 4xx（HTTPException），未捕获异常 500（全局 exception handler 兜底，detail 截断可读信息）。

## 数据目录

开发模式下：

- 数据库：`divine-server/data/ai_workspace.db`
- 设置：`divine-server/data/settings.json`
- 日志：`divine-server/data/divine-server.log`
- 工作区：`divine-server/workspace/{documents,spreadsheets,notes,presentations,diagrams,html,svg}`

桌面安装版默认使用系统应用数据目录，不写入项目目录。数据库、设置和日志由 `DIVINE_DATA_DIR` 控制，工作区由 `DIVINE_WORKSPACE_DIR` 控制。

## 打包

### 打包 sidecar

```bash
cd divine-server
source .venv/bin/activate
pip install -r requirements.txt pyinstaller
bash build-sidecar.sh                  # 自动检测当前平台
bash build-sidecar.sh darwin-arm64     # 显式指定平台
bash build-sidecar.sh darwin-x64
bash build-sidecar.sh win32-x64
bash build-sidecar.sh linux-x64
```

产物输出到 `divine-server/bin/<target>/`，并同步复制为 Tauri externalBin 文件到 `divine-app/src-tauri/binaries/`。

### 打包桌面端

```bash
cd divine-app
pnpm tauri:build:prod    # 正式包，不包含右键调试菜单
pnpm tauri:build:test    # test 包，保留右键 Reload / Inspect Element，不签名不公证
pnpm tauri:build:debug   # 调试包，开启 devtools
```

### macOS 签名与公证

```bash
./scripts/release-macos.sh                  # Developer ID 签名 + 公证
./scripts/release-macos.sh --skip-notarize  # 只签名，跳过公证
./scripts/release-macos.sh --keychain-profile <profile>  # 使用已保存的 notarytool profile
./scripts/release-macos.sh --adhoc          # 本机测试，ad-hoc 签名
```

完整签名需要安装 Developer ID Application 证书；公证需要设置 `APPLE_ID`、`APPLE_PASSWORD`、`APPLE_TEAM_ID`，或使用 App Store Connect API Key（`APPLE_API_ISSUER`、`APPLE_API_KEY`、`APPLE_API_KEY_PATH`）。
也可以先用 `xcrun notarytool store-credentials <profile> --apple-id ... --team-id ...` 保存凭据，再用 `--keychain-profile` 公证。

签名证书不要写进 `tauri.conf.json`。在项目根目录创建 `.env`（参考 `.env.example`）填入：

```bash
APPLE_SIGNING_IDENTITY="Developer ID Application: Your Name (TEAMID)"
```

`release-macos.sh` 打包时会读取 `.env`，用临时配置覆盖 `signingIdentity`；`.env` 已被 gitignore，不会提交到远程仓库。

### 自动更新与发布

首次为 updater 生成独立签名密钥，公钥会写入 `tauri.conf.json`，私钥不要提交到仓库：

```bash
cd divine-app
pnpm tauri signer generate -w ~/.tauri/divine.key
```

如果本机 shell 里遗留了其他项目的 `TAURI_SIGNING_PRIVATE_KEY` 环境变量，发布前需要取消，避免用错密钥：

```bash
unset TAURI_SIGNING_PRIVATE_KEY
export TAURI_SIGNING_PRIVATE_KEY_PATH="$HOME/.tauri/divine.key"
```

本地打包并上传 Release：

```bash
bash scripts/publish-macos.sh \
  --version 0.1.1 \
  --arch arm64 \
  --updater-key ~/.tauri/divine.key \
  --keychain-profile <profile> \
  --upload
```

脚本会构建签名包、生成 `.app.tar.gz` 和 `release-assets/latest.json`，并上传到 GitHub Release。客户端启动后自动检查该清单，发现新版本后可在设置页或右下角提示中下载并重启。

`--arch` 指定目标架构（`arm64` / `x86_64`，默认取当前机器架构），`--keychain-profile` 使用已保存的 notarytool 凭据；`--repo` 默认从 git remote 推断，`--notes` 默认读取 `release-notes.md`。

更新说明默认读取仓库根目录 `release-notes.md` 中 `## v<version>` 区块（例如 `## v0.1.1`）；也可以用 `--notes` 或 `--notes-file` 覆盖。

## GitHub Actions

仓库内置 `Build Desktop Apps` 工作流，可手动触发或推送 `v*` tag 触发，自动构建：

- macOS ARM64
- macOS x64
- Windows x64
- Linux x64

构建产物会作为 Actions Artifact 上传；推送 `v*` tag 时还会上传到对应 GitHub Release。