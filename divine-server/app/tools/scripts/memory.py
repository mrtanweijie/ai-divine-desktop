"""remember / forget_memory tool script — persists long-term user memory."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app import db  # noqa: E402


def _ok(message: str, data: dict | None = None) -> None:
    print(
        json.dumps(
            {"success": True, "message": message, "data": data},
            ensure_ascii=False,
        )
    )


def _err(message: str) -> None:
    print(json.dumps({"success": False, "message": message}, ensure_ascii=False))


def _remember(params: dict) -> None:
    content = str(params.get("content") or "").strip()
    if not content:
        _err("记忆内容不能为空")
        return
    category = str(params.get("category") or "preference").strip()
    supersede_id = str(params.get("supersede_id") or "").strip() or None
    try:
        importance = float(params.get("importance") or 0.5)
        confidence = float(params.get("confidence") or 0.8)
    except (TypeError, ValueError):
        importance, confidence = 0.5, 0.8
    try:
        memory = db.save_memory(
            content,
            category=category,
            importance=importance,
            confidence=confidence,
            supersede_id=supersede_id,
        )
    except ValueError as exc:
        _err(str(exc))
        return
    status = str(memory.get("status") or "active")
    if status == "pending":
        message = (
            f"记忆已保存但处于待确认状态（与已有记忆可能矛盾，用户确认后生效）：{content}"
        )
    else:
        message = f"已记住：{content}"
    _ok(
        message,
        {
            "id": memory["id"],
            "category": memory["category"],
            "status": status,
        },
    )


def _forget(params: dict) -> None:
    content = str(params.get("content") or "").strip()
    if not content:
        _err("要忘记的内容不能为空")
        return
    removed = db.forget_memory_by_content(content)
    if removed:
        _ok(f"已忘记 {removed} 条记忆")
    else:
        _err("没有找到匹配的记忆，请提供更准确的原话")


def main() -> None:
    data = json.load(sys.stdin)
    params = data.get("params") or {}
    action = str(params.get("action") or "").strip()
    if action == "remember":
        _remember(params)
    elif action == "forget":
        _forget(params)
    else:
        _err(f"未知操作: {action}")


if __name__ == "__main__":
    main()
