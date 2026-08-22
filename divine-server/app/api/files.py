from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..config import output_dir, projects_root, workspace_dir
from ..pdf_preview import (
    MAX_PDF_PREVIEW_BYTES,
    MAX_PDF_PREVIEW_PAGES,
    render_pdf_pages,
)

router = APIRouter(prefix="/files", tags=["files"])

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def _resolve_image_path(raw: str) -> Path:
    """把 Markdown 里的图片路径解析为本地文件。

    支持绝对路径、相对路径（如 images/xxx.png）。相对路径依次从
    workspace / output / 所有项目目录（~/Documents/Divine/*）解析，
    保证项目工作区里生成的图片也能被读取。只允许读取这些目录内的图片。
    """
    path = Path(raw)
    if not path.is_absolute():
        roots: list[Path] = [
            workspace_dir().resolve(),
            output_dir().resolve(),
        ]
        projects = projects_root().resolve()
        if projects.exists():
            roots.extend(
                project.resolve()
                for project in projects.iterdir()
                if project.is_dir()
            )
        for root in roots:
            candidate = (root / path).resolve()
            if candidate.is_file():
                path = candidate
                break
    path = path.expanduser().resolve()
    if path.suffix.lower() not in _IMAGE_SUFFIXES:
        raise HTTPException(status_code=400, detail="不是支持的图片格式")
    allowed = [
        workspace_dir().resolve(),
        output_dir().resolve(),
        projects_root().resolve(),
    ]
    if not any(str(path).startswith(str(root)) for root in allowed):
        raise HTTPException(status_code=400, detail="路径越界")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="图片不存在")
    return path


@router.get("/image")
def image_file(path: str):
    """读取 Markdown 中引用的本地图片，供前端 <img> 渲染。"""
    target = _resolve_image_path(path)
    # 图片文件不会变化，缓存一天：前端流式渲染重挂载 <img> 时
    # 直接命中缓存，避免反复请求导致页面闪烁
    return FileResponse(
        target, headers={"Cache-Control": "public, max-age=86400"}
    )


class PdfPreviewRequest(BaseModel):
    path: str

ALLOWED_CATEGORIES = {
    "documents",
    "spreadsheets",
    "notes",
    "pdf",
    "presentations",
    "diagrams",
    "html",
    "svg",
}


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
                        "download_url": f"/files/{category}/{path.name}",
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
                    "download_url": f"/files/{category}/{item.name}",
                }
            )
    return {"category": category, "files": files}


@router.post("/pdf-preview")
def pdf_preview(request: PdfPreviewRequest):
    path = Path(request.path).expanduser().resolve()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    if path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="不是 PDF 文件")
    size = path.stat().st_size
    if size > MAX_PDF_PREVIEW_BYTES:
        raise HTTPException(status_code=413, detail="PDF 文件过大，无法预览")
    try:
        pages = render_pdf_pages(path)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"PDF 渲染失败: {exc}") from exc
    return {
        "pages": pages,
        "page_count": len(pages),
        "truncated": len(pages) >= MAX_PDF_PREVIEW_PAGES,
    }


@router.get("/{category}/{filename}")
def download_file(category: str, filename: str):
    path = (_category_dir(category) / filename).resolve()
    if not str(path).startswith(str(_category_dir(category))):
        raise HTTPException(status_code=400, detail="路径越界")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, filename=path.name)
