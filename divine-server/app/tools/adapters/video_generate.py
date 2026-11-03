"""video_generate — 视频生成（035）：提交即返回，绝不占住对话。

链路（§6）：校验参数 → ``service.submit_video_task``（建 media_tasks 行 + 挂
后台轮询）→ **毫秒级返回 task_id**。轮询/下载/旁车文件全在 service 的后台
协程里，状态变化走 ``media_tasks_changed`` 事件到任务面板与工具卡。

这里的校验只有四类（失败都**不扣费**，因为还没到上游）：
1. 未配置视频模型 → 引导去设置；
2. 图生视频缺图 / 文件不存在 / 不是图片 → ``needs_media`` 语义的报错；
3. 资讯模式缺 URL → ``needs_source``；
4. 参数越界 → **静默裁剪**（就近取合法值），并在 message 里写明实际参数
   （035 §11 风险表：模型不知道各家合法集，靠适配器兜）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...file_types import is_image_path
from ...media import service
from ...media.config import video_capabilities
from ..base import ToolAdapter, ToolExecutionError, ToolResult
from ..registry import register_tool

DESCRIPTION = (
    "生成视频（文生视频 / 首帧·首尾帧图生视频 / 资讯视频）。**提交即返回**："
    "返回 task_id 后任务进入后台，完成情况看「生成任务」面板，不要说已生成。\n"
    "【何时调用】① 参数没说清（比例/时长/分辨率任一缺）→ 先调 video_brief 弹面板；"
    "② 用户已说全，或收到 video_create 回流 → 直接调本工具，参数原样传入，"
    "不要二次确认、不要自行改写；③ 资讯视频：先 web_fetch 提炼正文，"
    "再把要点作为 prompt 传入，source=article 并带 source_url。\n"
    "【硬约束】返回 status=running 只代表已提交；**禁止**向用户声称已完成。"
    "同一会话 60s 内相同参数会被幂等护栏拦截（防重复扣费）。"
)


def _clamp_choice(value: Any, legal: tuple, default: Any) -> tuple[Any, str | None]:
    """就近取合法值；返回 (value, note)。"""
    raw = str(value or "").strip()
    if raw in legal:
        return raw, None
    if not raw:
        return default, None
    if isinstance(default, int):
        numbers = [item for item in legal if isinstance(item, int)]
        if numbers:
            nearest = min(numbers, key=lambda item: abs(item - _to_int(raw, default)))
            return nearest, f"时长不在支持区间，已就近取 {nearest}s"
    return default, f"{raw} 不被当前模型支持，已用 {default}"


def _to_int(raw: str, default: int) -> int:
    digits = "".join(ch for ch in raw if ch.isdigit())
    return int(digits) if digits else default


def _nearest_ratio(value: str, legal: tuple[str, ...]) -> tuple[str, str | None]:
    """比例就近匹配：按宽高比数值距离。"""
    raw = str(value or "").strip()
    if raw in legal:
        return raw, None
    if ":" not in raw:
        return "", f"比例 {raw} 不合法，已交给模型自适应"

    def _ratio(label: str) -> float:
        try:
            width, height = label.split(":")
            return float(width) / float(height)
        except (ValueError, ZeroDivisionError):
            return 1.0

    target = _ratio(raw)
    nearest = min(legal, key=lambda item: abs(_ratio(item) - target))
    return nearest, f"比例 {raw} 不被当前模型支持，已就近取 {nearest}"


@register_tool("video_generate", DESCRIPTION, {
    "type": "object",
    "properties": {
        "prompt": {
            "type": "string",
            "description": "视频内容描述（含镜头语言）。资讯视频传**提炼后的要点稿**，"
            "不要把原文整段贴进来",
        },
        "model_id": {"type": "string", "description": "可选；多个视频模型时指定，缺省取生效条目"},
        "mode": {
            "type": "string",
            "enum": ["text", "first_frame", "first_last"],
            "description": "缺省按传了几张帧图推断：0=纯文本、1=首帧、2=首尾帧",
        },
        "duration": {"type": "integer", "description": "秒；越界会被就近裁剪"},
        "resolution": {"type": "string", "description": "480P/720P/768P/1080P/2K，按 provider 合法集裁剪"},
        "aspect_ratio": {"type": "string", "description": "16:9 等；非法值就近匹配"},
        "first_frame": {"type": "string", "description": "首帧图片的本地路径（用户选定/附件路径）"},
        "last_frame": {"type": "string", "description": "尾帧图片路径（仅 MiniMax 支持）"},
        "subtitles": {"type": "boolean", "description": "true 时同步产出同名 .srt（P1 不烧制进画面）"},
        "voiceover": {"type": "string", "description": "口播/旁白文案；落 .txt 并写进 prompt 的音频提示"},
        "source": {"type": "string", "enum": ["custom", "article"], "description": "素材来源（§7.9）"},
        "source_url": {"type": "string", "description": "资讯页面 URL（source=article 时必填，落任务表供溯源）"},
        "filename": {"type": "string", "description": "落盘文件名（不含扩展名）"},
    },
    "required": ["prompt"],
})
class VideoGenerateAdapter(ToolAdapter):
    """提交视频生成任务；同步段只做校验与建行。"""

    category = "media"
    timeout = 30
    allow_external_paths = True

    def external_paths(self, workspace: Path, arguments: dict[str, Any]) -> list[str]:
        paths = []
        for key in ("first_frame", "last_frame"):
            value = str(arguments.get(key) or "").strip()
            if value:
                paths.append(value)
        return paths

    async def run(
        self,
        workspace: Path,
        arguments: dict[str, Any],
        locale: str | None = None,
        progress_callback: Any | None = None,
    ) -> ToolResult:
        del workspace, locale, progress_callback
        args = arguments or {}

        prompt = str(args.get("prompt") or "").strip()
        if not prompt:
            raise ToolExecutionError("缺少 prompt（视频内容描述）")

        first_frame = str(args.get("first_frame") or "").strip() or None
        last_frame = str(args.get("last_frame") or "").strip() or None
        notes: list[str] = []

        # —— 帧校验：存在 + 是图片（失败都在上游之前，不扣费）——
        for label, path in (("首帧", first_frame), ("尾帧", last_frame)):
            if not path:
                continue
            if not Path(path).is_file():
                raise ToolExecutionError(f"{label}图片不存在：{path}，请确认路径或重新选择")
            if not is_image_path(path):
                raise ToolExecutionError(f"{label}必须是图片文件（png/jpg/webp 等）：{path}")

        # —— mode 推断 + provider 能力裁剪 ——
        from app.config import settings_store
        from app.media.config import active_video_provider, video_capabilities

        settings = settings_store.load()
        provider = active_video_provider(settings)
        caps = video_capabilities(provider)

        if first_frame and last_frame:
            mode = "first_last"
        elif first_frame:
            mode = "first_frame"
        else:
            mode = str(args.get("mode") or "text")
        if mode == "first_last" and not caps["supports_last_frame"]:
            notes.append("当前模型不支持尾帧，已忽略 last_frame")
            last_frame = None
            mode = "first_frame" if first_frame else "text"
        if mode in ("first_frame", "first_last") and not first_frame:
            raise ToolExecutionError(
                "图生视频需要先帧图片：请在面板里选择图片，或直接发图后重试（needs_media）"
            )

        # —— 参数静默裁剪（就近取合法值，并在 message 里说明实际参数）——
        duration, duration_note = _clamp_choice(
            args.get("duration"), caps["durations"], caps["durations"][0]
        )
        if duration_note:
            notes.append(duration_note)
        resolution, resolution_note = _clamp_choice(
            args.get("resolution"), caps["resolutions"], caps["resolutions"][0]
        )
        if resolution_note:
            notes.append(resolution_note)
        aspect_ratio, ratio_note = _nearest_ratio(
            str(args.get("aspect_ratio") or ""), caps["ratios"]
        )
        if ratio_note:
            notes.append(ratio_note)

        source = str(args.get("source") or "custom").strip().lower()
        source_url = str(args.get("source_url") or "").strip()
        if source not in ("custom", "article"):
            source = "custom"
        if source == "article" and not source_url:
            raise ToolExecutionError(
                "资讯视频（source=article）需要提供文章 URL（needs_source）；"
                "没有 URL 请改用 source=custom"
            )

        voiceover = str(args.get("voiceover") or "").strip()
        params: dict[str, Any] = {
            "mode": mode,
            "duration": duration,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio or "",
            "first_frame": first_frame,
            "last_frame": last_frame,
            "subtitles": bool(args.get("subtitles")),
            "voiceover": voiceover,
            "source": source,
            "source_url": source_url,
            "filename": str(args.get("filename") or "").strip(),
        }

        try:
            submitted = service.submit_video_task(
                prompt=prompt,
                params=params,
                session_id=str(args.get("session_id") or "") or None,
                call_id=str(args.get("call_id") or "") or None,
            )
        except ValueError as exc:
            # 未配置视频模型 / 未配 key：人话 + 设置入口，不出现堆栈
            raise ToolExecutionError(str(exc)) from exc

        task = submitted["task"]
        message = (
            f"已提交视频生成任务（{provider}，{duration}s/{resolution}"
            f"{'/' + aspect_ratio if aspect_ratio else ''}），预计 1–3 分钟。"
            "任务进入后台，用户可在「生成任务」面板查看进度；**先告知用户生成中，"
            "不要声称已完成**。"
        )
        if submitted["duplicate"]:
            message = "60 秒内已有相同参数的任务在跑，已复用该任务（防重复扣费），未重复提交。"
        elif submitted.get("queued"):
            message = "当前并发已满，任务已排队（前面还有生成中的任务）。" + message
        if notes:
            message += " 参数调整：" + "；".join(notes) + "。"

        return ToolResult(
            success=True,
            message=message,
            content=json_dumps(
                {
                    "success": True,
                    "message": message,
                    "task_id": task["id"],
                    "status": task["status"],
                    "duplicate": submitted["duplicate"],
                    "estimate_cny": submitted["estimate"],
                }
            ),
            data={
                "task_id": task["id"],
                "status": task["status"],
                "provider": provider,
                "duration": duration,
                "resolution": resolution,
                "aspect_ratio": aspect_ratio,
                "estimate_cny": submitted["estimate"],
            },
        )


def json_dumps(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)
