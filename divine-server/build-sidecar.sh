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
    LLAMA_ARCH="arm64-apple-darwin"
    ;;
  darwin-x64)
    EXE="divine-server"
    TRIPLE="x86_64-apple-darwin"
    TARGET_ARCH="x86_64"
    LLAMA_ARCH="x86_64-apple-darwin"
    ;;
  win32-x64)
    EXE="divine-server.exe"
    TRIPLE="x86_64-pc-windows-msvc"
    LLAMA_ARCH="x86_64-pc-windows-msvc"
    ;;
  linux-x64)
    EXE="divine-server"
    TRIPLE="x86_64-unknown-linux-gnu"
    LLAMA_ARCH="x86_64-unknown-linux-gnu"
    ;;
  *)
    echo "unknown target platform: $TARGET" >&2
    exit 1
    ;;
esac

# ============================================================================
# 下载 llama-server
# ============================================================================
download_llama() {
  local LLAMA_VERSION="b10666"
  local LLAMA_DIR="$ROOT/bin/$TARGET/llama"
  
  echo "==> downloading llama-server ${LLAMA_VERSION} (${TARGET})..."
  
  # 检查是否已下载
  if [[ -f "$LLAMA_DIR/llama-server" ]] || [[ -f "$LLAMA_DIR/llama-server.exe" ]]; then
    echo "    llama-server already exists, skipping download"
    return 0
  fi
  
  mkdir -p "$LLAMA_DIR"
  
  # 构建下载 URL（根据平台选择）
  local ARCHIVE_NAME=""
  case "$TARGET" in
    darwin-arm64) ARCHIVE_NAME="llama-${LLAMA_VERSION}-bin-macos-arm64.tar.gz" ;;
    darwin-x64) ARCHIVE_NAME="llama-${LLAMA_VERSION}-bin-macos-x64.tar.gz" ;;
    linux-x64) ARCHIVE_NAME="llama-${LLAMA_VERSION}-bin-ubuntu-x64.tar.gz" ;;
    linux-arm64) ARCHIVE_NAME="llama-${LLAMA_VERSION}-bin-ubuntu-arm64.tar.gz" ;;
    win32-x64) ARCHIVE_NAME="llama-${LLAMA_VERSION}-bin-win-x64.zip" ;;
    *)
      echo "WARNING: unsupported platform $TARGET, skipping llama-server download"
      return 0
      ;;
  esac
  
  local DOWNLOAD_URL="https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_VERSION}/${ARCHIVE_NAME}"
  local ARCHIVE_FILE="$ROOT/dist/${ARCHIVE_NAME}"
  
  echo "    URL: $DOWNLOAD_URL"
  
  # 下载
  mkdir -p "$ROOT/dist"
  if command -v curl &> /dev/null; then
    curl -L -o "$ARCHIVE_FILE" "$DOWNLOAD_URL"
  elif command -v wget &> /dev/null; then
    wget -O "$ARCHIVE_FILE" "$DOWNLOAD_URL"
  else
    echo "ERROR: curl or wget required" >&2
    exit 1
  fi
  
  # 解压
  if [[ "$ARCHIVE_NAME" == *.tar.gz ]]; then
    tar -xzf "$ARCHIVE_FILE" -C "$LLAMA_DIR"
  else
    unzip -o "$ARCHIVE_FILE" -d "$LLAMA_DIR"
  fi
  
  # 设置可执行权限
  chmod +x "$LLAMA_DIR"/llama-server* 2>/dev/null || true
  
  # 清理
  rm -f "$ARCHIVE_FILE"
  
  echo "    llama-server downloaded to: $LLAMA_DIR"
  ls -la "$LLAMA_DIR/"
}

# ============================================================================
# 补齐 llama-server 的第三方动态库
# ============================================================================
# llama.cpp 官方 macOS 二进制的 libggml-base 依赖 OpenMP (libomp)，且 server
# 二进制链接了 OpenSSL (libssl/libcrypto)。这些库不在官方发布包内，若不随包
# 分发，部署后的 llama-server 会直接 dyld 崩溃（Library not loaded），导致
# "启动本地模型一直失败"。这里把 brew 里的库复制到 llama/ 与 libs/ 目录，
# 由 divine-server.spec 打包，运行时 LocalLLMManager 通过 DYLD_LIBRARY_PATH
# 解析。
bundle_llama_deps() {
  local LLAMA_DIR="$ROOT/bin/$TARGET/llama"
  local LIBS_DIR="$ROOT/bin/$TARGET/libs"
  if [[ "$TARGET" != darwin-* ]]; then
    # Linux/Windows 发布包通常静态链接或自带依赖，无需额外处理
    return 0
  fi

  local EXTRA_LIBS=(
    "/opt/homebrew/opt/openssl@3/lib/libssl.3.dylib"
    "/opt/homebrew/opt/openssl@3/lib/libcrypto.3.dylib"
    "/opt/homebrew/opt/libomp/lib/libomp.dylib"
  )
  mkdir -p "$LLAMA_DIR" "$LIBS_DIR"
  for lib in "${EXTRA_LIBS[@]}"; do
    if [[ -f "$lib" ]]; then
      # -f：brew 的 dylib 是只读文件，重复构建时直接覆盖
      cp -f "$lib" "$LLAMA_DIR/"
      cp -f "$lib" "$LIBS_DIR/"
      chmod +x "$LLAMA_DIR/$(basename "$lib")" "$LIBS_DIR/$(basename "$lib")"
      echo "    bundling dependency: $lib"
    else
      echo "    WARNING: $lib not found (llama-server may fail to start without brew)" >&2
    fi
  done
}

cd "$ROOT"
if [[ -n "${PYTHON:-}" ]]; then
  PYTHON_BIN="$PYTHON"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT/.venv/bin/python"
else
  PYTHON_BIN="python3"
fi

# 下载 llama-server
download_llama

# 补齐 llama-server 的第三方动态库（openssl / libomp）
bundle_llama_deps

rm -rf "dist/divine-server" "dist/divine-server.exe"
if [[ "$TARGET" == darwin-* ]]; then
  # 目标切片经环境变量传给 divine-server.spec（EXE 的 target_arch）。不能走 CLI
  # --target-arch：给 .spec 文件时 PyInstaller 会拒绝 makespec 选项。若宿主 Python
  # 架构与目标不符（arm64 宿主编 x86_64），PyInstaller 会直接报错，不会静默产出
  # 错误的切片——这正是上一轮 lipo 踩的坑。
  export SIDECAR_TARGET_ARCH="$TARGET_ARCH"
fi
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
cp "dist/$EXE" "$BIN_DIR/.$EXE.tmp"
mv -f "$BIN_DIR/.$EXE.tmp" "$BIN_DIR/$EXE"
cp "dist/$EXE" "$TAURI_BIN_DIR/.$EXTERNAL_NAME.tmp"
mv -f "$TAURI_BIN_DIR/.$EXTERNAL_NAME.tmp" "$TAURI_BIN_DIR/$EXTERNAL_NAME"

echo "sidecar generated: $BIN_DIR/$EXE"
echo "externalBin generated: $TAURI_BIN_DIR/$EXTERNAL_NAME"
