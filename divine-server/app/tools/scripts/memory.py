"""remember / forget_memory / recall_memories tool script — long-term user memory."""

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


def _format_hit(hit: dict) -> str:
    label = {"preference": "偏好", "fact": "事实", "event": "事件"}.get(
        str(hit.get("category") or ""), "记忆"
    )
    return f"- [{label}] {hit.get('content')}（id: {hit.get('id')}）"


def _forget(params: dict) -> None:
    memory_id = str(params.get("memory_id") or "").strip()
    if memory_id:
        if db.forget_memory(memory_id):
            _ok("已忘记该条记忆", {"id": memory_id})
        else:
            _err("没有找到该 id 对应的有效记忆")
        return
    content = str(params.get("content") or "").strip()
    if not content:
        _err("要忘记的内容不能为空")
        return
    result = db.forget_memory_by_query(content)
    if result["exact_removed"]:
        _ok(f"已忘记 {result['exact_removed']} 条记忆")
        return
    deleted = result.get("deleted") or []
    if deleted:
        _ok(
            f"已忘记：{deleted[0].get('content')}",
            {"id": deleted[0].get("id")},
        )
        return
    candidates = result.get("candidates") or []
    if candidates:
        listing = "\n".join(_format_hit(hit) for hit in candidates)
        _ok(
            "没有自动删除。找到以下相似记忆，请向用户确认要删除哪一条，"
            "然后带 memory_id 重新调用：\n" + listing,
            {"candidates": candidates},
        )
        return
    _err("没有找到匹配的记忆，请提供更准确的原话")


def _recall(params: dict) -> None:
    query = str(params.get("query") or "").strip()
    if not query:
        _err("查询内容不能为空")
        return
    scope = str(params.get("scope") or "user").strip()
    try:
        limit = max(1, min(20, int(params.get("limit") or 5)))
    except (TypeError, ValueError):
        limit = 5
    hits = db.recall_memories(query, scope=scope, limit=limit)
    if not hits:
        _ok("没有找到相关记忆")
        return
    listing = "\n".join(_format_hit(hit) for hit in hits)
    _ok(f"找到 {len(hits)} 条相关记忆：\n{listing}", {"hits": hits})


def main() -> None:
    data = json.load(sys.stdin)
    params = data.get("params") or {}
    action = str(params.get("action") or "").strip()
    if action == "remember":
        _remember(params)
    elif action == "forget":
        _forget(params)
    elif action == "recall":
        _recall(params)
    else:
        _err(f"未知操作: {action}")


if __name__ == "__main__":
    main()
