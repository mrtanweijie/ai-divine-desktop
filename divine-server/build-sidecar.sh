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

# PyInstaller 的 --target-arch 只对 macOS 有意义。darwin-arm64 / darwin-x64
# 各指定 TARGET_ARCH，让构建脚本明确产出的 Mach-O 切片：CI 里 darwin-x64 必须
# 用 x86_64 的 Python（Rosetta 下运行），否则 PyInstaller 会拒绝 cross-arch，
# 或者像上一轮一样在 arm64 宿主机上用 arm64 Python 编出"名为 x86_64 实为 arm64"
# 的二进制，lipo 合并时报 same architectures (arm64)。
case "$TARGET" in
  darwin-arm64)
    EXE="divine-server"
    TRIPLE="aarch64-apple-darwin"
    TARGET_ARCH="arm64"
    ;;
  darwin-x64)
    EXE="divine-server"
    TRIPLE="x86_64-apple-darwin"
    TARGET_ARCH="x86_64"
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
if [[ "$TARGET" == darwin-* ]]; then
  # 显式指定目标切片。若宿主 Python 的架构与 TARGET_ARCH 不符，PyInstaller 会
  # 直接报错（不会静默产出错误的切片）——这正是上一轮 lipo 踩的坑。
  "$PYTHON_BIN" -m PyInstaller --clean --noconfirm --target-arch "$TARGET_ARCH" divine-server.spec
else
  "$PYTHON_BIN" -m PyInstaller --clean --noconfirm divine-server.spec
fi

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
