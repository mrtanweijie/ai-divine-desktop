from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..config import output_dir

router = APIRouter(prefix="/files", tags=["files"])

ALLOWED_CATEGORIES = {"documents", "spreadsheets", "notes", "presentations"}


def _category_dir(category: str) -> Path:
    if category not in ALLOWED_CATEGORIES:
        raise HTTPException(status_code=400, detail="不支持的类别")
    path = (output_dir() / category).resolve()
    if not str(path).startswith(str(output_dir().resolve())):
        raise HTTPException(status_code=400, detail="路径越界")
    return path


@router.get("")
def list_workspace():
    root = output_dir().resolve()
    result = []
    for category in sorted(ALLOWED_CATEGORIES):
        files = []
        for path in sorted((root / category).glob("*")):
            if path.is_file() and not path.name.startswith("."):
                files.append(
                    {
                        "name": path.name,
                        "size": path.stat().st_size,
                        "download_url": f"/api/files/{category}/{path.name}",
                    }
                )
        result.append({"category": category, "files": files})
    return {"workspace": str(root), "categories": result}


@router.get("/{category}")
def list_category(category: str):
    path = _category_dir(category)
    files = []
    for item in sorted(path.glob("*")):
        if item.is_file() and not item.name.startswith("."):
            files.append(
                {
                    "name": item.name,
                    "size": item.stat().st_size,
                    "download_url": f"/api/files/{category}/{item.name}",
                }
            )
    return {"category": category, "files": files}


@router.get("/{category}/{filename}")
def download_file(category: str, filename: str):
    path = (_category_dir(category) / filename).resolve()
    if not str(path).startswith(str(_category_dir(category))):
        raise HTTPException(status_code=400, detail="路径越界")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, filename=path.name)
