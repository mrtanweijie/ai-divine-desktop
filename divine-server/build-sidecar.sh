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
  darwin-arm64)
    EXE="divine-server"
    TRIPLE="aarch64-apple-darwin"
    ;;
  darwin-x64)
    EXE="divine-server"
    TRIPLE="x86_64-apple-darwin"
    ;;
  win32-x64)
    EXE="divine-server.exe"
    TRIPLE="x86_64-pc-windows-msvc"
    ;;
  linux-x64)
    EXE="divine-server"
    TRIPLE="x86_64-unknown-linux-gnu"
    ;;
  *)
    echo "未知目标平台: $TARGET" >&2
    exit 1
    ;;
esac

cd "$ROOT"
if [[ -n "${PYTHON:-}" ]]; then
  PYTHON_BIN="$PYTHON"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT/.venv/bin/python"
else
  PYTHON_BIN="python3"
fi
rm -rf "dist/divine-server" "dist/divine-server.exe"
"$PYTHON_BIN" -m PyInstaller --clean --noconfirm divine-server.spec

BIN_DIR="bin/$TARGET"
TAURI_BIN_DIR="$ROOT/../divine-app/src-tauri/binaries"
if [[ "$EXE" == *.exe ]]; then
  EXTERNAL_NAME="divine-server-$TRIPLE.exe"
else
  EXTERNAL_NAME="divine-server-$TRIPLE"
fi
mkdir -p "$BIN_DIR"
mkdir -p "$TAURI_BIN_DIR"
rm -rf "$BIN_DIR"/*
rm -f "$TAURI_BIN_DIR/$EXTERNAL_NAME"
cp "dist/$EXE" "$BIN_DIR/$EXE"
cp "dist/$EXE" "$TAURI_BIN_DIR/$EXTERNAL_NAME"

echo "sidecar 已生成: $BIN_DIR/$EXE"
echo "externalBin 已生成: $TAURI_BIN_DIR/$EXTERNAL_NAME"
