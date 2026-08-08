# ai-divine-desktop

AI Divine Desktop：本地优先、隐私可控的桌面 AI 助手。

## 功能特性

- DeepSeek 流式对话，支持深度思考和会话历史
- 本地文件分析：Word、Excel、Markdown、图片识别、网页抓取
- 工具系统：`notes`、`presentation`、`read_file`、`read_image`、`spreadsheet`、`web_fetch`、`word_document`
- SQLite 本地存储，数据默认保存在本机
- Tauri 2 + Rust 桌面壳，启动时自动拉起 FastAPI sidecar
- 自研 React UI 组件，不引入 AntD

## 目录结构

| 目录 | 说明 |
| --- | --- |
| `divine-server` | FastAPI sidecar：Agent、SSE、SQLite、工具系统 |
| `divine-app` | Vite + React + TypeScript 前端，自研组件 |
| `divine-app/src-tauri` | Tauri 2 + Rust 桌面壳 |
| `docs` | 项目方案文档 |

## 快速开始

### divine-server

```bash
cd divine-server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

### divine-app

```bash
cd divine-app
pnpm install
pnpm dev
```

前端通过 `divine-app/.env*` 配置环境，API 地址由 `VITE_SERVICE_API_URL` 控制。

### 打包 sidecar

```bash
cd divine-server
bash build-sidecar.sh darwin-arm64   # darwin-x64 / win32-x64 / linux-x64
```

产物会输出到 `divine-server/bin/<target>/`。

### 打包桌面端

```bash
cd divine-app
pnpm tauri:build:prod    # 正式包，不包含右键调试菜单
pnpm tauri:build:test    # test 包，保留右键 Reload / Inspect Element
pnpm tauri:build:debug   # 调试包
```

## GitHub Actions

仓库内置 `Build Desktop Apps` 工作流，可手动触发或推送 `v*` tag 触发，自动构建：

- macOS ARM64
- macOS x64
- Windows x64
- Linux x64

构建产物会作为 Actions Artifact 上传。
