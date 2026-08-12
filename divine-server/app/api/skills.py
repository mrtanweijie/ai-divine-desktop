from __future__ import annotations

from fastapi import APIRouter

from ..config import workspace_dir
from ..skills import skill_registry

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("")
def list_skills():
    skills = skill_registry.refresh(workspace_dir())
    return {"skills": skills}


@router.post("/reload")
def reload_skills():
    skills = skill_registry.refresh(workspace_dir())
    return {"ok": True, "skills": skills}
