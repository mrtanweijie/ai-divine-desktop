"""Memory audit & pending-confirmation API (design doc 022 §5.1).

用户可以查看 AI 记住了什么、确认/拒绝冲突记忆、删除错误记忆——
对应设计原则 4「可审计可编辑」。pending 消费入口不依赖模型自觉。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import db

router = APIRouter(prefix="/memories", tags=["memories"])


class MemoryReviewRequest(BaseModel):
    note: str | None = None  # 预留：确认/拒绝时的备注，暂不落库


class MemoryImportRequest(BaseModel):
    """L3 程序记忆的人工导入通道（022 §4.4：只人工导入，不自动写）。"""

    content: str
    category: str = "procedure"  # procedure=做法/runbook；也接受 preference/fact/event
    importance: float = 0.7
    confidence: float = 1.0
    project_id: str | None = None


@router.post("", status_code=201)
def import_memory(payload: MemoryImportRequest):
    try:
        memory = db.save_memory(
            payload.content.strip(),
            category=payload.category,
            importance=payload.importance,
            confidence=payload.confidence,
            project_id=payload.project_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"memory": memory}


@router.get("")
def list_memories(status: str = "active", category: str | None = None):
    try:
        items = db.list_memories(status=status, category=category, limit=200)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"memories": items, "pending_count": len(db.list_pending_memories())}


@router.get("/pending")
def list_pending():
    return {"memories": db.list_pending_memories()}


@router.post("/{memory_id}/confirm")
def confirm_memory(memory_id: str):
    if not db.confirm_pending_memory(memory_id):
        raise HTTPException(status_code=404, detail="待确认记忆不存在")
    return {"success": True}


@router.post("/{memory_id}/reject")
def reject_memory(memory_id: str):
    if not db.reject_pending_memory(memory_id):
        raise HTTPException(status_code=404, detail="待确认记忆不存在")
    return {"success": True}


@router.delete("/{memory_id}")
def delete_memory(memory_id: str):
    if not db.forget_memory(memory_id):
        raise HTTPException(status_code=404, detail="记忆不存在或已失效")
    return {"success": True}
