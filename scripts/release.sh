#!/usr/bin/env bash
set -euo pipefail

# 一键打包发布：前置校验 → 侧车/前端构建 → 签名公证 → 更新器签名 → (可选)上传 Release
# 底层复用 publish-macos.sh（其内部再调 release-macos.sh 完成构建与签名公证）。
#
# 用法:
#   ./scripts/release.sh                      # 以 tauri.conf.json 当前版本发布
#   ./scripts/release.sh 0.3.0                # 指定版本（须与 tauri.conf 一致）
#   ./scripts/release.sh 0.3.0 --upload       # 构建后上传 GitHub Release
#   ./scripts/release.sh 0.3.0 --tag-push     # 构建前打 v0.3.0 tag 并推送（触发 CI）
#   ./scripts/release.sh 0.3.0 --adhoc        # 本机 ad-hoc（无证书/公证，仅测试）
#
# 可用环境变量:
#   DIVINE_UPDATER_KEY     更新签名私钥（默认 ~/.tauri/divine.key）
#   DIVINE_NOTARY_PROFILE  notarytool 凭据 profile（等价 --keychain-profile）

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONF="$ROOT/divine-app/src-tauri/tauri.conf.json"
PKG="$ROOT/divine-app/package.json"
NOTES_FILE="$ROOT/release-notes.md"

VERSION="$(grep -o '"version": "[^"]*"' "$CONF" | head -1 | cut -d'"' -f4)"
UPLOAD=0
TAG_PUSH=0
ADHOC=0
FORCE=0
KEYCHAIN_PROFILE="${DIVINE_NOTARY_PROFILE:-}"
UPDATER_KEY="${DIVINE_UPDATER_KEY:-$HOME/.tauri/divine.key}"

usage() {
  sed -n '3,15p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

for arg in "$@"; do
  case "$arg" in
    -h|--help) usage ;;
  esac
done
while [[ $# -gt 0 ]]; do
  case "$1" in
    [0-9]*.[0-9]*.[0-9]*) VERSION="$1"; shift ;;
    --upload) UPLOAD=1; shift ;;
    --tag-push) TAG_PUSH=1; shift ;;
    --adhoc) ADHOC=1; shift ;;
    --force) FORCE=1; shift ;;
    --keychain-profile) KEYCHAIN_PROFILE="${2:-}"; shift 2 ;;
    *) echo "未知参数: $1（--help 查看用法）" >&2; exit 1 ;;
  esac
done

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m错误: %s\033[0m\n' "$*" >&2; exit 1; }

[[ -n "$VERSION" ]] || die "无法从 tauri.conf.json 读取版本号"

step "[1/6] 前置校验（版本 ${VERSION}）"
PKG_VERSION="$(grep -o '"version": "[^"]*"' "$PKG" | head -1 | cut -d'"' -f4)"
[[ "$PKG_VERSION" == "$VERSION" ]] || die "package.json($PKG_VERSION) 与 tauri.conf.json($VERSION) 版本不一致"
CARGO_VERSION="$(grep -m1 '^version' "$ROOT/divine-app/src-tauri/Cargo.toml" | cut -d'"' -f2)"
[[ "$CARGO_VERSION" == "$VERSION" ]] || die "Cargo.toml($CARGO_VERSION) 与 tauri.conf.json($VERSION) 版本不一致（发版前同步三处版本号）"
grep -q "^## v${VERSION}[[:space:]]*$" "$NOTES_FILE" || die "release-notes.md 缺少 ## v$VERSION 区块"
[[ -f "$UPDATER_KEY" ]] || die "更新签名私钥不存在: $UPDATER_KEY（用 pnpm tauri signer generate 生成或设置 DIVINE_UPDATER_KEY）"
if [[ $ADHOC -eq 0 ]]; then
  HAS_PROFILE=$([[ -n "$KEYCHAIN_PROFILE" ]] && echo 1 || echo 0)
  HAS_APPLE_ID=$([[ -n "${APPLE_ID:-}" && -n "${APPLE_PASSWORD:-}" && -n "${APPLE_TEAM_ID:-}" ]] && echo 1 || echo 0)
  HAS_API_KEY=$([[ -n "${APPLE_API_ISSUER:-}" && -n "${APPLE_API_KEY:-}" && -n "${APPLE_API_KEY_PATH:-}" ]] && echo 1 || echo 0)
  if [[ "$HAS_PROFILE" != 1 && "$HAS_APPLE_ID" != 1 && "$HAS_API_KEY" != 1 ]]; then
    die "公证凭据缺失（三选一）：--keychain-profile/DIVINE_NOTARY_PROFILE、
环境变量 APPLE_ID+APPLE_PASSWORD+APPLE_TEAM_ID、或 APPLE_API_ISSUER+APPLE_API_KEY(+PATH)；
本机测试可用 --adhoc 跳过签名公证"
  fi
fi
if [[ $UPLOAD -eq 1 ]] && ! gh auth status >/dev/null 2>&1; then
  die "--upload 需要 gh 已登录（gh auth login）"
fi
echo "版本/发布说明/私钥/公证凭据 ✓"
if [[ $FORCE -eq 0 ]] && [[ -n "$(git -C "$ROOT" status --porcelain)" ]]; then
  echo "⚠️  工作树有未提交改动："
  git -C "$ROOT" status --short | head -5
  die "先提交，或用 --force 跳过该检查"
fi

step "[2/6] 重建 sidecar（PyInstaller，源码变更必须重建）"
( cd "$ROOT/divine-server" && bash build-sidecar.sh )

if [[ $TAG_PUSH -eq 1 ]]; then
  step "[3/6] 打 tag v$VERSION 并推送"
  git -C "$ROOT" tag "v$VERSION"
  git -C "$ROOT" push origin "v$VERSION"
fi

step "[4/6] 构建 + 签名 + 公证 + 更新器签名（publish-macos.sh）"
PUBLISH_ARGS=(--version "$VERSION" --updater-key "$UPDATER_KEY")
[[ $UPLOAD -eq 1 ]] && PUBLISH_ARGS+=(--upload)
[[ $ADHOC -eq 1 ]] && PUBLISH_ARGS+=(--adhoc)
[[ -n "$KEYCHAIN_PROFILE" ]] && PUBLISH_ARGS+=(--keychain-profile "$KEYCHAIN_PROFILE")
# sidecar 刚在上面重建过，跳过重复构建
PUBLISH_ARGS+=(--skip-sidecar)
"$ROOT/scripts/publish-macos.sh" "${PUBLISH_ARGS[@]}"

step "[5/6] 产物清单"
BUNDLE="$ROOT/divine-app/src-tauri/target/release/bundle"
find "$BUNDLE" -maxdepth 3 \( -name "Divine.app" -o -name "*.dmg" -o -name "*.tar.gz" -o -name "latest.json" \) -newer "$CONF" -print 2>/dev/null || ls -la "$BUNDLE/macos" "$BUNDLE/dmg" 2>/dev/null

step "[6/6] 完成"
if [[ $UPLOAD -eq 1 ]]; then
  echo "已上传 Release v$VERSION；客户端启动后将自动检查更新。"
else
  echo "本地构建完成（未上传）。上传命令："
  echo "  ./scripts/release.sh $VERSION --upload --keychain-profile <profile>"
fi
