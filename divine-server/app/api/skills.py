from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from .. import db
from ..config import workspace_dir
from ..skills import skill_registry

router = APIRouter(prefix="/api/skills", tags=["skills"])


def _skills_workspace(raw: str | None) -> Path:
    if raw:
        return Path(raw).expanduser().resolve()
    return workspace_dir()


def _project_skill_roots() -> list[Path]:
    return [
        Path(project["path"]).expanduser().resolve()
        for project in db.list_projects()
    ]


@router.get("")
def list_skills(workspace: str | None = Query(None)):
    if workspace:
        skills = skill_registry.refresh(_skills_workspace(workspace))
    else:
        skills = skill_registry.refresh(project_roots=_project_skill_roots())
    return {"skills": skills}


@router.post("/reload")
def reload_skills(workspace: str | None = Query(None)):
    if workspace:
        skills = skill_registry.refresh(_skills_workspace(workspace))
    else:
        skills = skill_registry.refresh(project_roots=_project_skill_roots())
    return {"ok": True, "skills": skills}


@router.delete("/{name}")
def delete_skill(name: str, workspace: str | None = Query(None)):
    try:
        if workspace:
            return skill_registry.uninstall(
                name, _skills_workspace(workspace)
            )
        return skill_registry.uninstall(
            name, project_roots=_project_skill_roots()
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail=f"卸载失败：{exc}"
        ) from exc
