from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from .. import db
from ..schemas import (
    ProjectCreate,
    ProjectUpdate,
    ProjectOrderUpdate,
    ProjectPinUpdate,
    ProjectReorderRequest,
)

router = APIRouter(prefix="/projects", tags=["projects"])
logger = logging.getLogger("divine.projects")

PROJECT_ICONS = {
    "folder",
    "file-sliders",
    "brick-wall",
    "mail",
    "calendar-days",
    "wallet",
    "chart-area",
    "database-zap",
    "code",
    "bug",
    "git-branch-plus",
    "gamepad-2",
}


def _resolve_path(raw: str | None) -> Path:
    if not raw or not raw.strip():
        raise HTTPException(status_code=400, detail="请填写项目文件夹路径")
    path = Path(raw.strip()).expanduser()
    if not path.is_absolute():
        path = Path.home() / path
    return path.resolve()


@router.get("")
def list_projects():
    return {"projects": db.list_projects()}


@router.post("", status_code=201)
def create_project(body: ProjectCreate):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="项目名称不能为空")
    icon = body.icon or "folder"
    if icon not in PROJECT_ICONS:
        raise HTTPException(status_code=400, detail="项目图标不支持")

    path = _resolve_path(body.path)
    if path.exists() and not path.is_dir():
        raise HTTPException(status_code=400, detail=f"路径已存在且不是文件夹：{path}")
    if not path.is_dir():
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"创建文件夹失败：{exc}") from exc

    project = db.create_project(name, str(path), icon)
    logger.info(
        "project created id=%s name=%s path=%s icon=%s",
        project["id"],
        name,
        path,
        icon,
    )
    return project


@router.patch("/{project_id}")
def update_project(project_id: str, body: ProjectUpdate):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    updates: dict[str, str] = {}
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="项目名称不能为空")
        updates["name"] = name
    if body.path is not None:
        path = _resolve_path(body.path)
        if not path.is_dir():
            raise HTTPException(status_code=400, detail=f"文件夹不存在：{path}")
        updates["path"] = str(path)
    if body.icon is not None:
        if body.icon not in PROJECT_ICONS:
            raise HTTPException(status_code=400, detail="项目图标不支持")
        updates["icon"] = body.icon
    if not updates:
        return project
    updated = db.update_project(
        project_id,
        name=updates.get("name"),
        path=updates.get("path"),
        icon=updates.get("icon"),
    )
    logger.info(
        "project updated id=%s name=%s path=%s icon=%s",
        project_id,
        updated["name"],
        updated["path"],
        updated.get("icon", "folder"),
    )
    return updated


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    db.delete_project(project_id)
    logger.info("project deleted id=%s name=%s", project_id, project["name"])


@router.patch("/{project_id}/order")
def update_project_order(project_id: str, body: ProjectOrderUpdate):
    """Update a project's sort order."""
    try:
        project = db.update_project_order(project_id, body.sort_order)
    except KeyError:
        raise HTTPException(status_code=404, detail="项目不存在")
    logger.info(
        "project order updated id=%s sort_order=%s",
        project_id,
        body.sort_order,
    )
    return project


@router.patch("/{project_id}/pin")
def pin_project(project_id: str, body: ProjectPinUpdate):
    """Pin or unpin a project."""
    try:
        project = db.pin_project(project_id, body.pinned)
    except KeyError:
        raise HTTPException(status_code=404, detail="项目不存在")
    logger.info(
        "project pin updated id=%s pinned=%s",
        project_id,
        body.pinned,
    )
    return project


@router.post("/reorder", status_code=204)
def reorder_projects(body: ProjectReorderRequest):
    """Batch update sort orders for multiple projects."""
    db.reorder_projects([item.model_dump() for item in body.orders])
    logger.info("projects reordered count=%s", len(body.orders))
