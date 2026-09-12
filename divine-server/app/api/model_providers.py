"""模型提供商目录 API：读取/保存用户可编辑的 divine-model-provider.json。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import model_providers

router = APIRouter(prefix="/model-providers", tags=["model-providers"])


class ProviderSaveRequest(BaseModel):
    providers: list[dict]


@router.get("")
def get_model_providers():
    providers, path = model_providers.load_model_providers()
    return {"providers": providers, "path": str(path)}


@router.post("/open-dir")
def open_config_dir():
    """在系统文件管理器中打开配置文件所在目录（用户手动编辑用）。"""
    import subprocess
    import sys

    _, path = model_providers.load_model_providers()
    directory = str(path.parent)
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", directory])
        elif sys.platform == "win32":
            subprocess.Popen(["explorer", directory])
        else:
            subprocess.Popen(["xdg-open", directory])
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"无法打开目录: {exc}") from exc
    return {"path": directory}


@router.put("")
def put_model_providers(payload: ProviderSaveRequest):
    try:
        providers = model_providers.save_model_providers(payload.providers)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"providers": providers, "path": str(model_providers.providers_config_path())}
