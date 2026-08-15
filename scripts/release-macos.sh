#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT/divine-app"
SIDECAR_DIR="$ROOT/divine-server"

load_env_file() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  while IFS='=' read -r key value; do
    [[ -z "$key" || "$key" == \#* ]] && continue
    key="${key#export }"
    key="$(printf '%s' "$key" | tr -d '[:space:]')"
    value="${value#\"}"
    value="${value%\"}"
    value="${value#\'}"
    value="${value%\'}"
    export "$key=$value"
  done < "$file"
}

load_env_file "$ROOT/.env"

ARCH=""
BUNDLES="app,dmg"
ADHOC=0
SKIP_NOTARIZE=0
SKIP_SIDECAR=0
NOTARY_PROFILE="${NOTARY_PROFILE:-}"

usage() {
  cat <<'EOF'
用法: ./scripts/release-macos.sh [选项]

选项:
  --arch arm64|x64   目标架构，默认当前机器架构
  --bundles <list>   传给 tauri build 的 bundle 类型，默认 app,dmg
  --adhoc            使用 ad-hoc 签名（本机测试），跳过公证
  --skip-notarize    使用 Developer ID 签名，但跳过公证
  --keychain-profile <name>
                     使用已保存的 notarytool profile 公证
  --skip-sidecar     跳过 PyInstaller，直接使用已有 sidecar 产物
  -h, --help         显示帮助
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --arch)
      ARCH="${2:-}"
      if [[ -z "$ARCH" ]]; then
        echo "错误: --arch 需要参数" >&2
        exit 1
      fi
      shift 2
      ;;
    --bundles)
      BUNDLES="${2:-}"
      if [[ -z "$BUNDLES" ]]; then
        echo "错误: --bundles 需要参数" >&2
        exit 1
      fi
      shift 2
      ;;
    --adhoc)
      ADHOC=1
      shift
      ;;
    --skip-notarize)
      SKIP_NOTARIZE=1
      shift
      ;;
    --keychain-profile)
      NOTARY_PROFILE="${2:-}"
      if [[ -z "$NOTARY_PROFILE" ]]; then
        echo "错误: --keychain-profile 需要参数" >&2
        exit 1
      fi
      shift 2
      ;;
    --skip-sidecar)
      SKIP_SIDECAR=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "未知参数: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "错误: 签名和公证只能在 macOS 上执行" >&2
  exit 1
fi

if [[ -z "$ARCH" ]]; then
  case "$(uname -m)" in
    arm64)
      ARCH="arm64"
      ;;
    x86_64)
      ARCH="x64"
      ;;
    *)
      echo "不支持当前架构: $(uname -m)" >&2
      exit 1
      ;;
  esac
fi

case "$ARCH" in
  arm64)
    TARGET="darwin-arm64"
    TRIPLE="aarch64-apple-darwin"
    ;;
  x64)
    TARGET="darwin-x64"
    TRIPLE="x86_64-apple-darwin"
    ;;
  *)
    echo "错误: --arch 只支持 arm64 或 x64" >&2
    exit 1
    ;;
esac

NATIVE_ARCH="$(uname -m)"
if [[ "$NATIVE_ARCH" == "arm64" && "$ARCH" == "x64" ]]; then
  echo "错误: x64 包需要在 Intel Mac 上构建" >&2
  exit 1
fi
if [[ "$NATIVE_ARCH" == "x86_64" && "$ARCH" == "arm64" ]]; then
  echo "错误: arm64 包需要在 Apple Silicon Mac 上构建" >&2
  exit 1
fi

if [[ "$ADHOC" == 1 ]]; then
  IDENTITY="-"
elif [[ -n "${APPLE_SIGNING_IDENTITY:-}" ]]; then
  IDENTITY="$APPLE_SIGNING_IDENTITY"
else
  IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null \
    | awk '/Developer ID Application/ {print $2}' \
    | head -1 || true)"
  if [[ -z "$IDENTITY" ]]; then
    echo "错误: 未找到 Developer ID Application 证书。" >&2
    echo "请先安装证书并设置 APPLE_SIGNING_IDENTITY，或使用 --adhoc 做本机测试。" >&2
    exit 1
  fi
fi
echo "签名身份: $IDENTITY"

if [[ "$ADHOC" == 1 && -n "$NOTARY_PROFILE" ]]; then
  echo "错误: --adhoc 与 --keychain-profile 不能同时使用" >&2
  exit 1
fi

if [[ -n "$NOTARY_PROFILE" && ",$BUNDLES," != *",dmg,"* ]]; then
  echo "错误: --keychain-profile 公证需要 DMG，--bundles 需包含 dmg" >&2
  exit 1
fi

if [[ "$ADHOC" != 1 && "$SKIP_NOTARIZE" != 1 && -z "$NOTARY_PROFILE" ]]; then
  HAS_APPLE_ID=0
  HAS_API_KEY=0
  if [[ -n "${APPLE_ID:-}" && -n "${APPLE_PASSWORD:-}" && -n "${APPLE_TEAM_ID:-}" ]]; then
    HAS_APPLE_ID=1
  fi
  if [[ -n "${APPLE_API_ISSUER:-}" && -n "${APPLE_API_KEY:-}" && -n "${APPLE_API_KEY_PATH:-}" ]]; then
    HAS_API_KEY=1
  fi
  if [[ "$HAS_APPLE_ID" != 1 && "$HAS_API_KEY" != 1 ]]; then
    echo "错误: 缺少公证凭据。" >&2
    echo "使用 Apple ID: 设置 APPLE_ID、APPLE_PASSWORD、APPLE_TEAM_ID" >&2
    echo "或使用 App Store Connect API Key: 设置 APPLE_API_ISSUER、APPLE_API_KEY、APPLE_API_KEY_PATH" >&2
    echo "或使用已保存的 notarytool profile: --keychain-profile <name>" >&2
    exit 1
  fi
fi

if command -v pnpm >/dev/null 2>&1; then
  PNPM="$(command -v pnpm)"
else
  echo "错误: 未找到 pnpm" >&2
  exit 1
fi

if [[ "$SKIP_SIDECAR" != 1 ]]; then
  if [[ -x "$SIDECAR_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$SIDECAR_DIR/.venv/bin/python"
  else
    PYTHON_BIN="$(command -v python3 || true)"
    if [[ -z "$PYTHON_BIN" ]]; then
      echo "错误: 未找到 python3" >&2
      exit 1
    fi
  fi
  if ! "$PYTHON_BIN" -m PyInstaller --version >/dev/null 2>&1; then
    echo "错误: 当前 Python 环境没有 PyInstaller" >&2
    echo "安装方式: $PYTHON_BIN -m pip install pyinstaller" >&2
    exit 1
  fi
  echo "构建 sidecar ($TARGET)..."
  (
    cd "$SIDECAR_DIR"
    PYTHON="$PYTHON_BIN" bash build-sidecar.sh "$TARGET"
  )
fi

echo "安装前端依赖..."
(
  cd "$APP_DIR"
  "$PNPM" install --frozen-lockfile
)

export APPLE_SIGNING_IDENTITY="$IDENTITY"
if [[ "$ADHOC" == 1 || "$SKIP_NOTARIZE" == 1 || -n "$NOTARY_PROFILE" ]]; then
  unset APPLE_ID APPLE_PASSWORD APPLE_TEAM_ID APPLE_API_ISSUER APPLE_API_KEY APPLE_API_KEY_PATH || true
fi

echo "构建并打包桌面端..."
(
  cd "$APP_DIR"
  CONFIG_ARGS=(--config src-tauri/tauri.prod.conf.json)
  OVERLAY="$(mktemp "${TMPDIR:-/tmp}/divine-signing.XXXXXX.json")"
  printf '{"bundle":{"macOS":{"signingIdentity":"%s"}}}\n' "$IDENTITY" > "$OVERLAY"
  CONFIG_ARGS+=(--config "$OVERLAY")
  "$PNPM" exec tauri build "${CONFIG_ARGS[@]}" --bundles "$BUNDLES"
  rm -f "$OVERLAY"
)

BUNDLE_DIR="$APP_DIR/src-tauri/target/release/bundle/macos"
BUNDLE_DMG_DIR="$APP_DIR/src-tauri/target/release/bundle/dmg"
APP_PATH="$BUNDLE_DIR/Divine.app"
if [[ ! -d "$APP_PATH" ]]; then
  echo "错误: 未找到构建产物 $APP_PATH" >&2
  exit 1
fi

DMG_PATH="$(find "$BUNDLE_DMG_DIR" -maxdepth 1 -name '*.dmg' | head -1 || true)"
if [[ -z "$DMG_PATH" ]]; then
  DMG_PATH="$(find "$BUNDLE_DIR" -maxdepth 1 -name '*.dmg' | head -1 || true)"
fi

echo "验证 codesign..."
codesign --verify --deep --strict --verbose=2 "$APP_PATH"

if [[ -n "$NOTARY_PROFILE" ]]; then
  if [[ -z "$DMG_PATH" ]]; then
    echo "错误: 未找到 DMG，无法使用 keychain profile 公证" >&2
    exit 1
  fi
  echo "提交公证 (profile: $NOTARY_PROFILE)..."
  xcrun notarytool submit "$DMG_PATH" \
    --keychain-profile "$NOTARY_PROFILE" \
    --wait --timeout 30m
  xcrun stapler staple "$DMG_PATH"
  xcrun stapler validate -v "$DMG_PATH"
elif [[ "$ADHOC" != 1 && "$SKIP_NOTARIZE" != 1 ]]; then
  echo "验证 Gatekeeper..."
  spctl --assess --type execute --verbose=2 "$APP_PATH"
  echo "验证 stapler..."
  xcrun stapler validate -v "$APP_PATH"
fi

if [[ -n "$DMG_PATH" ]]; then
  echo "验证 DMG..."
  hdiutil verify "$DMG_PATH"
  if [[ "$ADHOC" != 1 && "$SKIP_NOTARIZE" != 1 ]]; then
    xcrun stapler validate -v "$DMG_PATH"
  fi
fi

echo
echo "完成!"
echo "App:  $APP_PATH"
if [[ -n "$DMG_PATH" ]]; then
  echo "DMG:  $DMG_PATH"
fi
