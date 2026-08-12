from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from ..config import workspace_dir
from ..skills import skill_registry

router = APIRouter(prefix="/api/skills", tags=["skills"])


def _skills_workspace(raw: str | None) -> Path:
    if raw:
        return Path(raw).expanduser().resolve()
    return workspace_dir()


@router.get("")
def list_skills(workspace: str | None = Query(None)):
    skills = skill_registry.refresh(_skills_workspace(workspace))
    return {"skills": skills}


@router.post("/reload")
def reload_skills(workspace: str | None = Query(None)):
    skills = skill_registry.refresh(_skills_workspace(workspace))
    return {"ok": True, "skills": skills}


@router.delete("/{name}")
def delete_skill(name: str, workspace: str | None = Query(None)):
    try:
        return skill_registry.uninstall(
            name, _skills_workspace(workspace)
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail=f"卸载失败：{exc}"
        ) from exc
