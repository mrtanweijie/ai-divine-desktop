"""生成模型（图像/视频）共享层：配置读取与能力矩阵（036/035）。

网络调用与后台任务后续放 ``providers/`` 与 ``service.py``（035 §11）；
这里只保持确定性逻辑。
"""

from .config import (
    active_image_provider,
    image_capabilities,
    image_defaults,
)

__all__ = ["active_image_provider", "image_capabilities", "image_defaults"]
