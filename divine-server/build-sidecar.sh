#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-}"

if [[ -z "$TARGET" ]]; then
  case "$(uname -s)" in
    Darwin)
      case "$(uname -m)" in
        arm64) TARGET="darwin-arm64" ;;
        x86_64) TARGET="darwin-x64" ;;
      esac
      ;;
    Linux)
      case "$(uname -m)" in
        x86_64) TARGET="linux-x64" ;;
        aarch64) TARGET="linux-arm64" ;;
      esac
      ;;
    MINGW*|MSYS*|CYGWIN*)
      TARGET="win32-x64"
      ;;
  esac
fi

case "$TARGET" in
  darwin-arm64|darwin-x64|linux-x64)
    EXE="divine-server"
    ;;
  win32-x64)
    EXE="divine-server.exe"
    ;;
  *)
    echo "未知目标平台: $TARGET" >&2
    exit 1
    ;;
esac

cd "$ROOT"
PYTHON_BIN="${PYTHON:-python3}"
"$PYTHON_BIN" -m PyInstaller --clean --noconfirm divine-server.spec

BIN_DIR="bin/$TARGET"
mkdir -p "$BIN_DIR"
rm -rf "$BIN_DIR"/*
cp -R "dist/divine-server/." "$BIN_DIR/"

echo "sidecar 已生成: $BIN_DIR/$EXE"
