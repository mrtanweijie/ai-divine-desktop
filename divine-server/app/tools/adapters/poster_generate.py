"""poster_generate — 商品海报生成（底图 + 系统排版文字）。

链路：
  1. 校验商品图 / 商品名 / 比例；
  2. 要求当前生效的图像模型支持参考图（否则商品会被「重画」，不是海报）；
  3. 用「只出画面、不出字」的提示词调 image_generate 生成底图（图生图，保留商品原样）；
  4. `poster.layout.compose` 用系统中文字体叠主标题与卖点，输出 PNG；
  5. 成功即删底图（中间产物，避免卡片墙里多出一张无字图）。

为什么分两步：图像模型写中文必错字，而商品名与卖点必须一字不差。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ...config import output_dir_for_workspace
from ...file_types import is_image_path
from ...media import active_image_provider, image_capabilities
from ..base import ToolAdapter, ToolExecutionError, ToolResult
from ..poster.layout import PosterText, compose
from ..poster.prompt import STYLE_LABELS, build_prompt
from ..registry import register_tool, registry

#: 卖点分隔：以换行为主，兼容分号与顿号。
#: **不按中文逗号拆**——一句话里常有逗号（「现做现卖，2 小时送达」），拆开反而碎。
_POINT_SPLIT = re.compile(r"[\n\r]+|[；;、]+")

_MAX_POINTS = 4
_NAME_MAX = 24
_POINT_MAX = 40

_UNSAFE_FILENAME = re.compile(r"[\\/:*?\"<>|\s]+")


def _split_points(raw: str) -> list[str]:
    """卖点文本 → 条目列表（去重、截断、限 4 条）。"""
    seen: set[str] = set()
    points: list[str] = []
    for chunk in _POINT_SPLIT.split(raw or ""):
        item = " ".join(chunk.split()).strip(" -·•*")
        if not item or item in seen:
            continue
        seen.add(item)
        points.append(item[:_POINT_MAX])
        if len(points) >= _MAX_POINTS:
            break
    return points


def _resolve_image(workspace: Path, raw: str) -> Path:
    value = (raw or "").strip()
    if not value:
        raise ToolExecutionError("缺少商品图：请先选一张商品照片")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = workspace / path
    path = path.resolve()
    if not path.exists():
        raise ToolExecutionError(f"商品图不存在：{path.name}")
    if not is_image_path(path):
        raise ToolExecutionError("商品图格式不支持（需要 JPG / PNG / WebP）")
    return path


def _safe_name(name: str) -> str:
    cleaned = _UNSAFE_FILENAME.sub("", name).strip()
    return (cleaned or "poster")[:24]


@register_tool(
    "poster_generate",
    "生成商品海报：用商品图作参考生成无字底图，再由服务端用中文字体排版标题与卖点。"
    "**必须**先用 poster_brief 收齐参数（商品图 / 商品名称），不要在缺图时调用。"
    "适合商品海报、促销图、门店上新图；纯插画/壁纸请用 image_generate。",
    {
        "type": "object",
        "properties": {
            "product_image": {
                "type": "string",
                "description": "商品图本地路径（必填）：用户选定的商品照片，作为图生图参考",
            },
            "product_name": {
                "type": "string",
                "description": "商品名称（必填）：作为海报主标题，建议 12 字以内",
            },
            "selling_points": {
                "type": "string",
                "description": "核心卖点（可空）：换行或分号分隔，最多取前 4 条；既画进构图也排在海报底部",
            },
            "style": {
                "type": "string",
                "description": "海报风格：clean（简约留白，默认）/ promo（促销冲击）/ premium（高级质感）",
            },
            "aspect_ratio": {
                "type": "string",
                "description": "画面比例：3:4（默认，竖版）/ 9:16（长竖版）/ 1:1（方形）",
            },
            "extra": {
                "type": "string",
                "description": "补充画面描述（可空），如节日氛围、场景道具",
            },
            "filename": {
                "type": "string",
                "description": "输出文件名（不含扩展名），默认按商品名 + 时间戳",
            },
        },
        "required": ["product_image", "product_name"],
    },
)
class PosterGenerateAdapter(ToolAdapter):
    category = "files"
    timeout = 240
    allow_external_paths = True

    async def run(
        self,
        workspace: Path,
        arguments: dict[str, Any],
        locale: str | None = None,
        progress_callback: Any | None = None,
    ) -> ToolResult:
        del locale, progress_callback

        from app.config import settings_store

        arguments = arguments or {}
        image_path = _resolve_image(workspace, str(arguments.get("product_image") or ""))
        product_name = " ".join(str(arguments.get("product_name") or "").split())
        if not product_name:
            raise ToolExecutionError("缺少商品名称：海报主标题不能为空")
        product_name = product_name[:_NAME_MAX]
        points = _split_points(str(arguments.get("selling_points") or ""))

        style = str(arguments.get("style") or "clean").strip()
        if style not in STYLE_LABELS:
            style = "clean"
        aspect_ratio = str(arguments.get("aspect_ratio") or "3:4").strip()
        if aspect_ratio not in {"3:4", "9:16", "1:1"}:
            aspect_ratio = "3:4"

        settings = settings_store.load()
        provider = active_image_provider(settings)
        caps = image_capabilities(provider)
        if not caps["supports_reference"]:
            raise ToolExecutionError(
                "海报需要支持「参考图」的图像模型（当前生效的模型不支持）。"
                "请到「设置 → 生成模型」启用 MiniMax image-01 后再试。"
            )

        image_adapter = registry.get("image_generate")
        if image_adapter is None:
            raise ToolExecutionError("图像生成能力不可用（image_generate 未注册）")

        prompt = build_prompt(
            product_name=product_name,
            selling_points=points,
            style=style,
            aspect_ratio=aspect_ratio,
            extra=str(arguments.get("extra") or ""),
        )

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        base_result = await image_adapter.run(
            workspace,
            {
                "prompt": prompt,
                "reference_image": str(image_path),
                "aspect_ratio": aspect_ratio,
                "n": 1,
                # 自动优化会把「不要文字」这类约束改写掉，这里必须关
                "prompt_optimizer": False,
                "filename": f"poster-base-{stamp}",
            },
        )
        if not base_result.filepath:
            raise ToolExecutionError("底图生成失败：未返回文件")

        base_path = Path(base_result.filepath)
        out_dir = output_dir_for_workspace(workspace) / "posters"
        out_name = str(arguments.get("filename") or "").strip()
        out_path = out_dir / f"{_safe_name(out_name or product_name)}-{stamp}.png"

        try:
            compose(
                base_path,
                PosterText(title=product_name, points=points),
                out_path,
                aspect_ratio=aspect_ratio,
            )
        except Exception as exc:  # noqa: BLE001 - 底图保留，便于用户直接取用
            raise ToolExecutionError(f"海报排版失败：{exc}") from exc
        finally:
            if base_path.exists():
                base_path.unlink(missing_ok=True)

        message = f"已生成商品海报《{product_name}》（{aspect_ratio}"
        if points:
            message += f"，{len(points)} 条卖点"
        message += "，文字由系统排版）"

        base_data = base_result.data if isinstance(base_result.data, dict) else {}
        return ToolResult(
            success=True,
            message=message,
            file_name=out_path.name,
            filepath=str(out_path),
            file_size=out_path.stat().st_size,
            data={
                "files": [
                    {"path": str(out_path), "filepath": str(out_path), "name": out_path.name}
                ],
                "poster": {
                    "title": product_name,
                    "points": points,
                    "style": style,
                    "aspect_ratio": aspect_ratio,
                },
                "provider": base_data.get("provider") or provider,
                "model": base_data.get("model"),
                "base_prompt": prompt,
            },
        )
