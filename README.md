# ai-divine-desktop

AI Divine Desktop：本地优先、隐私可控的桌面 AI 助手。

## 目录结构

| 目录 | 说明 |
| --- | --- |
| `divine-server` | FastAPI sidecar：Agent、SSE、SQLite、工具系统 |
| `divine-app` | Vite + React + TypeScript 前端，自研组件，不引入 AntD |
| `divine-app/src-tauri` | Tauri 2 + Rust 桌面壳 |
| `docs` | 项目方案 |

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

### 打包 sidecar

```bash
cd divine-server
bash build-sidecar.sh darwin-arm64   # darwin-x64 / win32-x64 / linux-x64
```

产物会输出到 `divine-server/bin/<target>/`。

### src-tauri

```bash
cd divine-app
pnpm tauri:dev
```

### 打包

```bash
cd divine-app
pnpm tauri:build          # 发布安装包（DMG / NSIS / AppImage 等）
pnpm tauri:build:debug    # 调试安装包
```
