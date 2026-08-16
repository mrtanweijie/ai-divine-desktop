# Divine

Divine：本地优先、隐私可控的桌面 AI 助手。后端为 FastAPI sidecar，前端为 Vite + React + TypeScript，桌面壳为 Tauri 2 + Rust。

默认端口约定：

| 服务 | 端口 | 说明 |
| --- | --- | --- |
| FastAPI sidecar | `8019` | Agent、SSE、SQLite、工具系统 |
| Vite dev server | `8010` | 前端开发服务，`/api` 代理到 sidecar |

## 功能特性

- DeepSeek 流式对话，支持深度思考、会话历史、会话搜索和标题自动生成
- 项目化会话：项目工作区、项目图标、会话按项目组织
- 本地文件分析：Word、Excel、Markdown、PDF、图片识别、网页抓取
- 文档生成：Markdown 笔记、Word、PPT、Excel
- 本地 RAG：工作区文档向量索引与检索
- 计划与审批：复杂任务先创建待办计划，高危操作请求用户确认
- 定时任务与日程：提醒、定时任务、日历事件，macOS 可同步系统日历
- 终端工具：可交互终端，高危命令需用户确认
- Markdown 渲染与 Shiki 代码高亮
- SQLite 本地存储，数据默认保存在本机
- Tauri 2 + Rust 桌面壳，启动时自动拉起并监控 FastAPI sidecar
- 自研 React UI 组件，不引入 AntD

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | FastAPI、Uvicorn、SQLite、LangChain DeepSeek、GLM 视觉模型、PyInstaller |
| 前端 | Vite、React 19、TypeScript、react-markdown、Shiki、自研组件 |
| 桌面壳 | Tauri 2 + Rust，sidecar 生命周期管理、托盘、macOS Calendar 桥接 |

## 目录结构

| 目录 | 说明 |
| --- | --- |
| `divine-server` | FastAPI sidecar：API、Agent、SSE、SQLite、工具系统 |
| `divine-server/app/agent` | Agent 编排、prompt、工具执行与 SSE 流拆分的子模块 |
| `divine-server/app/db` | SQLite 连接、迁移与按领域拆分的仓储 |
| `divine-server/app/llm` | LLM provider、DSML 流解析与 LangChain 适配 |
| `divine-server/app/tools/adapters` | 工具注册与参数定义 |
| `divine-server/app/tools/scripts` | 工具子进程脚本 |
| `divine-app` | Vite + React + TypeScript 前端，自研组件 |
| `divine-app/src-tauri` | Tauri 2 + Rust 桌面壳 |
| `docs` | 项目方案文档 |
| `scripts` | macOS 签名与公证脚本 |

## 快速开始

### 1. 启动后端

需要 Python 3.11+，开发环境当前使用 Python 3.14.6。

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

| 工具 | 用途 |
| --- | --- |
| `calculator` | 安全计算数学表达式 |
| `clipboard` | 读取、写入、清空系统剪贴板 |
| `create_plan` | 为复杂任务创建待办计划 |
| `directory_tree` | 查看目录树结构 |
| `describe_svg` | 读取现有 SVG，返回画布、元素、关键 id 和结构摘要 |
| `draw_svg` | 从零生成 SVG 矢量图/图标/插画，默认保存到 `svg/`；正文中的 SVG 代码块会在前端自动渲染预览 |
| `edit_files` | 按 SEARCH/REPLACE 批量修改或创建多个文本文件；SEARCH 必须精确匹配，创建新文件时 search 传空字符串 |
| `edit_svg` | 基于现有 SVG 修改，只改动用户提到的元素并保持其他不变 |
| `generate_chart` | 根据分析结果生成 ECharts 图表并在对话中内联展示 |
| `image_resize` | 缩放图片 |
| `mermaid_export` | 把 Mermaid 流程图源码保存为 `.mmd` 文件 |
| `notes` | 生成 Markdown 笔记 |
| `pdf_split_merge` | 拆分、合并 PDF |
| `presentation` | 生成 PPT 演示文稿 |
| `rag_index` | 建立工作区本地向量索引 |
| `rag_search` | 检索工作区本地资料 |
| `read_file` | 读取文本、Office、PDF、表格等文件；支持 start_line/end_line 分段读取 |
| `read_image` | 用 GLM 视觉模型识别图片 |
| `ux_html` | 保存 Agent 按用户选择的风格与需求文档自定义设计的完整 UX 交互 HTML，默认写入项目工作区 `html/`；HTML/SVG 文件可在文件面板直接预览 |
| `schedule_task` | 创建和管理定时提醒/定时任务 |
| `search_files` | 按文件名搜索工作区文件 |
| `spreadsheet` | 生成 Excel 表格 |
| `sqlite_query` | 只读查询本地 SQLite 数据库 |
| `svg_to_png` | 将最终 SVG 导出为 PNG 位图 |
| `terminal` | 执行终端命令，高危命令需确认 |
| `web_fetch` | 抓取网页内容 |
| `web_fetch_batch` | 批量抓取多个网页/数据源并汇总返回 |
| `word_document` | 生成 Word 文档 |
| `write_calendar` | 创建和管理日程/日历事件 |

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
| `/api/settings` | 运行时设置 |
| `WS /api/terminal` | 交互式终端 |
| `POST /api/terminal/decide` | 审批待确认的终端命令 |

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

本地打包并上传 GitHub Release：

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
