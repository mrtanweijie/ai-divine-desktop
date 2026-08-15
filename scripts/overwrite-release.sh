#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT/divine-app"
REPO="${REPO:-mrtanweijie/ai-divine-desktop}"
ARCH="${ARCH:-$(uname -m)}"

case "$ARCH" in
  arm64)
    ARCH_TARGET="aarch64"
    ;;
  x86_64 | amd64)
    ARCH_TARGET="x86_64"
    ;;
  *)
    echo "错误: 不支持的架构 $ARCH" >&2
    exit 1
    ;;
esac

usage() {
  cat <<'EOF'
用法: ./scripts/overwrite-release.sh <version>

示例:
  ./scripts/overwrite-release.sh 0.1.1

环境变量:
  REPO   覆盖 GitHub repo，默认 mrtanweijie/ai-divine-desktop
  ARCH   覆盖目标架构，默认当前机器架构
EOF
}

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
  usage >&2
  exit 1
fi

TAG="v$VERSION"
TARBALL="$APP_DIR/src-tauri/target/release/bundle/macos/Divine_${VERSION}_${ARCH_TARGET}.app.tar.gz"
DMG="$APP_DIR/src-tauri/target/release/bundle/dmg/Divine_${VERSION}_${ARCH_TARGET}.dmg"
MANIFEST="$ROOT/release-assets/latest.json"

if ! command -v gh >/dev/null 2>&1; then
  echo "错误: 未找到 gh，请先执行 brew install gh" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "错误: gh 未登录，请先执行 gh auth login" >&2
  exit 1
fi

for file in "$TARBALL" "$DMG" "$MANIFEST"; do
  if [[ ! -f "$file" ]]; then
    echo "错误: 缺少文件 $file" >&2
    exit 1
  fi
done

if ! gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
  echo "错误: GitHub 上不存在 Release $TAG，覆盖脚本只更新已有 Release" >&2
  exit 1
fi

NOTES="$(awk -v target="## v$VERSION" '
  $0 == target { found = 1; next }
  found && /^#{1,2}[[:space:]]/ { exit }
  found { print }
' "$ROOT/release-notes.md" | sed '/./,$!d')"

echo "覆盖 $TAG 资产..."
gh release upload "$TAG" \
  "$TARBALL" \
  "$DMG" \
  "$MANIFEST" \
  --repo "$REPO" \
  --clobber

if [[ -n "$NOTES" ]]; then
  echo "更新 $TAG 发布说明..."
  gh release edit "$TAG" \
    --repo "$REPO" \
    --notes "$NOTES"
fi

echo "完成: https://github.com/$REPO/releases/tag/$TAG"
