"""manage_model_providers 工具脚本：查看/增改/删除模型提供商目录。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app import model_providers  # noqa: E402


def _ok(message: str, data: dict | None = None) -> None:
    print(
        json.dumps(
            {"success": True, "message": message, "data": data},
            ensure_ascii=False,
        )
    )


def _err(message: str) -> None:
    print(json.dumps({"success": False, "message": message}, ensure_ascii=False))


def main() -> None:
    data = json.load(sys.stdin)
    params = data.get("params") or {}
    action = str(params.get("action") or "").strip()

    if action == "list":
        providers, path = model_providers.load_model_providers()
        lines = [
            f"- {p['value']}（{p['label']}）{p['base_url']} 默认模型: {p['default_model']}"
            f" 模型列表: {','.join(p['list']) or '无'}"
            for p in providers
        ]
        _ok(
            f"当前提供商目录（配置文件: {path}，可直接编辑后重启生效）：\n" + "\n".join(lines),
            {"providers": providers, "path": str(path)},
        )
        return

    if action == "upsert":
        try:
            providers = model_providers.upsert_model_provider(params.get("provider") or {})
        except ValueError as exc:
            _err(str(exc))
            return
        entry = next(p for p in providers if p["value"] == str(params.get("provider", {}).get("value")))
        _ok(
            f"提供商 {entry['value']} 已保存（共 {len(providers)} 个）。用户重新打开设置或重启后生效。",
            {"providers": providers},
        )
        return

    if action == "remove":
        try:
            providers = model_providers.remove_model_provider(params.get("value"))
        except ValueError as exc:
            _err(str(exc))
            return
        _ok(
            f"已删除，剩余 {len(providers)} 个提供商。用户重新打开设置或重启后生效。",
            {"providers": providers},
        )
        return

    _err(f"未知操作: {action}")


if __name__ == "__main__":
    main()
