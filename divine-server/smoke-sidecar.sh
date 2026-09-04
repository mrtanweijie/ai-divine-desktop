#!/bin/bash
# 冻结 sidecar 冒烟：全模块 import + 启动探活。
#
# 背景（2026-09-02）：PyInstaller 直写 bin/ 期间启动的进程会读到半写归档，
# 运行时模块解压报 "Error -3 while decompressing data"（且惰性模块如
# app.llm.langchain 只在工具调用时才加载，普通冒烟漏检）。本脚本在构建后
# 用 --run-script 逐模块 import 全部 app.* 模块，验证归档可完整解压。
#
# 用法：
#   bash smoke-sidecar.sh [sidecar 路径]     # 默认 bin/darwin-arm64/divine-server
# 退出码：0=通过 1=失败

set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
BIN="${1:-$ROOT/bin/darwin-arm64/divine-server}"

if [ ! -x "$BIN" ]; then
  echo "FATAL: sidecar 不存在: $BIN"
  exit 1
fi
echo "==> 冒烟对象: $BIN"
shasum -a 256 "$BIN" | awk '{print "    SHA:", substr($1,1,12)}'

DATA_DIR="$(mktemp -d /tmp/smoke_data.XXXXXX)"
WS_DIR="$(mktemp -d /tmp/smoke_ws.XXXXXX)"
PORT=$((8090 + RANDOM % 500))
IMPORT_SCRIPT="$(mktemp /tmp/smoke_import.XXXXXX.py)"
FAIL=0

cleanup() {
  rm -rf "$DATA_DIR" "$WS_DIR" "$IMPORT_SCRIPT"
}
trap cleanup EXIT

# ---- 步骤 1：--run-script 全模块 import ----
cat > "$IMPORT_SCRIPT" <<'PY'
import importlib
import json
import pkgutil
import app

bad = []
for mod in pkgutil.walk_packages(app.__path__, "app."):
    if mod.name.endswith("__pycache__"):
        continue
    try:
        importlib.import_module(mod.name)
    except Exception as exc:  # noqa: BLE001
        bad.append(f"{mod.name}: {type(exc).__name__}: {str(exc)[:120]}")
print(json.dumps({"bad": bad}, ensure_ascii=False))
PY

echo "==> [1/2] 全模块 import 冒烟（--run-script）..."
OUTPUT="$(DIVINE_DATA_DIR="$DATA_DIR" DIVINE_WORKSPACE_DIR="$WS_DIR" \
  "$BIN" --run-script "$IMPORT_SCRIPT" 2>&1 | tail -1)"
if echo "$OUTPUT" | grep -q '"bad": \[\]'; then
  echo "    PASS 全部模块可解压加载"
else
  echo "    FAIL 归档损坏或模块加载错误:"
  echo "$OUTPUT" | cut -c1-200
  exit 1
fi

# ---- 步骤 2：启动 + 探活 ----
echo "==> [2/2] 启动探活（端口 $PORT，最多 40s）..."
DIVINE_DATA_DIR="$DATA_DIR" DIVINE_WORKSPACE_DIR="$WS_DIR" PORT="$PORT" \
  "$BIN" >/dev/null 2>&1 &
PID=$!

UP=0
for _ in $(seq 1 40); do
  # --noproxy 绕过本机代理（代理会把请求转发出去导致 502 误判）；-f 要求 2xx
  if curl -fsS --noproxy '*' -m 2 "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
    UP=1
    break
  fi
  sleep 1
done

if [ "$UP" = "1" ]; then
  HEALTH="$(curl -fsS --noproxy '*' -m 3 "http://127.0.0.1:$PORT/api/health" | head -c 120)"
  echo "    PASS 服务就绪: $HEALTH"
else
  echo "    FAIL 服务未在 40s 内就绪"
  kill "$PID" 2>/dev/null
  exit 1
fi

kill "$PID" 2>/dev/null
wait "$PID" 2>/dev/null
echo "==> 冒烟通过 ✓"
exit 0
