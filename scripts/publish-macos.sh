#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT/divine-app"
RELEASE_NOTES_FILE="$ROOT/release-notes.md"

VERSION=""
TAG=""
UPDATER_KEY=""
REPO=""
NOTES=""
NOTES_FILE=""
ARCH="$(uname -m)"
BUNDLES="app,dmg"
UPLOAD=0
RELEASE_ARGS=()

usage() {
  cat <<'EOF'
用法: ./scripts/publish-macos.sh [选项]

选项:
  --version <ver>          必填，例如 0.2.0
  --tag <tag>              可选，默认 v<version>
  --updater-key <path>     必填，更新签名私钥，例如 ~/.tauri/divine.key
  --repo <owner/repo>      可选，自动从 git remote 推断；--upload 时建议指定
  --notes "<text>"         更新说明
  --notes-file <path>      从文件读取更新说明；默认读取 release-notes.md 中对应版本区块
  --arch arm64|x64         目标架构，默认当前机器架构
  --bundles <list>         传给 tauri build 的 bundle，默认 app,dmg
  --upload                 构建后调用 gh release create/upload
  --keychain-profile <name> 公证 profile
  --adhoc                  本机 ad-hoc 签名，跳过公证
  --skip-sidecar           跳过 PyInstaller，使用已有 sidecar
  -h, --help               显示帮助
EOF
}

extract_release_notes() {
  local file="$1"
  local version="$2"
  awk -v target="v${version}" '
    BEGIN { found = 0 }
    $0 ~ "^#{1,2}[[:space:]]+" target "[[:space:]]*$" { found = 1; next }
    found && $0 ~ /^#{1,2}[[:space:]]/ { exit }
    found { print }
  ' "$file" | sed '/./,$!d'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      VERSION="${2:-}"
      shift 2
      ;;
    --tag)
      TAG="${2:-}"
      shift 2
      ;;
    --updater-key)
      UPDATER_KEY="${2:-}"
      shift 2
      ;;
    --repo)
      REPO="${2:-}"
      shift 2
      ;;
    --notes)
      NOTES="${2:-}"
      shift 2
      ;;
    --notes-file)
      NOTES_FILE="${2:-}"
      shift 2
      ;;
    --arch)
      ARCH="${2:-}"
      shift 2
      ;;
    --bundles)
      BUNDLES="${2:-}"
      shift 2
      ;;
    --upload)
      UPLOAD=1
      shift
      ;;
    --keychain-profile)
      RELEASE_ARGS+=(--keychain-profile "${2:-}")
      shift 2
      ;;
    --adhoc)
      RELEASE_ARGS+=(--adhoc)
      shift
      ;;
    --skip-sidecar)
      RELEASE_ARGS+=(--skip-sidecar)
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

if [[ -z "$NOTES" && -z "$NOTES_FILE" && -f "$RELEASE_NOTES_FILE" ]]; then
  NOTES_FILE="$RELEASE_NOTES_FILE"
fi

if [[ -z "$VERSION" ]]; then
  echo "错误: --version 必填" >&2
  exit 1
fi
CONFIG_VERSION="$(python3 -c "import json; print(json.load(open('$APP_DIR/src-tauri/tauri.conf.json'))['version'])")"
CARGO_VERSION="$(python3 -c "import tomllib; print(tomllib.load(open('$APP_DIR/src-tauri/Cargo.toml','rb'))['package']['version'])" 2>/dev/null || true)"
if [[ "$CONFIG_VERSION" != "$VERSION" ]]; then
  echo "错误: tauri.conf.json 版本为 ${CONFIG_VERSION}，与 --version $VERSION 不一致，请先更新版本号" >&2
  exit 1
fi
if [[ -n "$CARGO_VERSION" && "$CARGO_VERSION" != "$VERSION" ]]; then
  echo "错误: Cargo.toml 版本为 ${CARGO_VERSION}，与 --version $VERSION 不一致，请先更新版本号" >&2
  exit 1
fi
if [[ -z "$UPDATER_KEY" ]]; then
  echo "错误: --updater-key 必填" >&2
  exit 1
fi
if [[ ! -f "$UPDATER_KEY" ]]; then
  echo "错误: updater 私钥不存在: $UPDATER_KEY" >&2
  exit 1
fi
if [[ -z "$TAG" ]]; then
  TAG="v$VERSION"
fi
if [[ "$UPLOAD" == 1 && -z "$REPO" ]]; then
  REMOTE="$(git -C "$ROOT" remote get-url origin 2>/dev/null || true)"
  REPO="$(printf '%s' "$REMOTE" \
    | sed -E 's#(https://github.com/|git@github.com:)([^/]+/[^/.]+)(\.git)?#\2#')"
fi
if [[ "$UPLOAD" == 1 && -z "$REPO" ]]; then
  echo "错误: --upload 需要 --repo owner/repo，或配置 origin remote" >&2
  exit 1
fi

case "$ARCH" in
  arm64)
    ARCH_TARGET="aarch64"
    PLATFORM="darwin-aarch64"
    ;;
  x64)
    ARCH_TARGET="x86_64"
    PLATFORM="darwin-x86_64"
    ;;
  *)
    echo "错误: --arch 只支持 arm64 或 x64" >&2
    exit 1
    ;;
esac

export TAURI_SIGNING_PRIVATE_KEY_PATH="$UPDATER_KEY"
unset TAURI_SIGNING_PRIVATE_KEY || true

"$ROOT/scripts/release-macos.sh" \
  --arch "$ARCH" \
  --bundles "$BUNDLES" \
  "${RELEASE_ARGS[@]}"

BUNDLE_MAC="$APP_DIR/src-tauri/target/release/bundle/macos"
APP_PATH="$BUNDLE_MAC/Divine.app"
if [[ ! -d "$APP_PATH" ]]; then
  echo "错误: 未找到 $APP_PATH" >&2
  exit 1
fi

ARTIFACT_NAME="Divine_${VERSION}_${ARCH_TARGET}.app.tar.gz"
TARBALL="$BUNDLE_MAC/$ARTIFACT_NAME"
tar -czf "$TARBALL" -C "$BUNDLE_MAC" Divine.app

SHA256="$(shasum -a 256 "$TARBALL" | awk '{print $1}')"
SIGNATURE="$(cd "$APP_DIR" \
  && env -u TAURI_SIGNING_PRIVATE_KEY \
  pnpm tauri signer sign \
    -f "$UPDATER_KEY" \
    ${TAURI_SIGNING_PRIVATE_KEY_PASSWORD:+-p "$TAURI_SIGNING_PRIVATE_KEY_PASSWORD"} \
    "$TARBALL" | tail -1)"
rm -f "$TARBALL.sig"

if [[ -n "$NOTES_FILE" ]]; then
  if [[ "$NOTES_FILE" == "$RELEASE_NOTES_FILE" ]]; then
    NOTES="$(extract_release_notes "$NOTES_FILE" "$VERSION")"
    if [[ -z "$NOTES" ]]; then
      echo "警告: release-notes.md 中未找到 \"## v$VERSION\" 区块，将使用默认更新说明" >&2
    fi
  else
    NOTES="$(cat "$NOTES_FILE")"
  fi
fi
if [[ -z "$NOTES" ]]; then
  NOTES="$TAG 更新"
fi

if [[ -n "$REPO" ]]; then
  URL="https://github.com/$REPO/releases/download/$TAG/$ARTIFACT_NAME"
else
  URL="https://REPLACE_WITH_UPDATE_URL/$ARTIFACT_NAME"
fi

ASSET_DIR="$ROOT/release-assets"
mkdir -p "$ASSET_DIR"
MANIFEST="$ASSET_DIR/latest.json"
PUB_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

python3 - "$MANIFEST" "$VERSION" "$NOTES" "$PUB_DATE" \
  "$PLATFORM" "$URL" "$SIGNATURE" "$SHA256" <<'PY'
import json
import os
import sys

path, version, notes, pub_date, platform, url, signature, sha256 = sys.argv[1:]
payload = {}
if os.path.exists(path):
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        payload = {}
payload["version"] = version
payload["notes"] = notes
payload["pub_date"] = pub_date
payload.setdefault("platforms", {})[platform] = {
    "url": url,
    "signature": signature,
    "sha256": sha256,
}
with open(path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
PY

echo "更新包: $TARBALL"
echo "SHA256: $SHA256"
echo "更新清单: $MANIFEST"

if [[ "$UPLOAD" == 1 ]]; then
  if ! command -v gh >/dev/null 2>&1; then
    echo "错误: --upload 需要安装 gh（brew install gh）" >&2
    exit 1
  fi

  FILES=("$TARBALL" "$MANIFEST")
  DMG_PATH="$(find "$APP_DIR/src-tauri/target/release/bundle/dmg" \
    -maxdepth 1 -name '*.dmg' 2>/dev/null | head -1 || true)"
  if [[ -n "$DMG_PATH" ]]; then
    FILES+=("$DMG_PATH")
  fi

  if gh release view "$TAG" >/dev/null 2>&1; then
    gh release upload "$TAG" "${FILES[@]}" --clobber
  else
    gh release create "$TAG" \
      --title "$TAG" \
      --notes "$NOTES" \
      "${FILES[@]}"
  fi
  echo "已发布: https://github.com/$REPO/releases/tag/$TAG"
else
  echo
  echo "未上传。确认无误后加 --upload 上传；"
  echo "或手动上传 $TARBALL 和 $MANIFEST 到 GitHub Release $TAG"
fi
