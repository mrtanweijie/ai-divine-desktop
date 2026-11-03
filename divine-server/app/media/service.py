"""视频生成服务层（035 §6）：提交即返回 + 后台轮询 + 落盘 + 事件广播。

职责边界：
- 适配器（video_generate）只做参数校验 + 调 :func:`submit_video_task`，毫秒级返回；
- 真正的轮询/下载/旁车文件在这里的后台协程里，不占对话流；
- 状态变化一律 ``events.broadcast("media_tasks_changed")``——面板/卡片/徽标
  三处消费同一份事件，不许各自拉数据（035 §9.3）。
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .. import events
from ..config import normalize_media_models, output_dir, settings_store
from ..db import media_tasks
from .providers import ProviderError, get_provider

logger = logging.getLogger("divine.media")

#: 轮询间隔：官方向导建议 10s（MiniMax / 智谱都在这个量级收敛）
POLL_INTERVAL_SECONDS = 10
#: 任务最长等待：超过视为过期（云端保留 7 天，这里 30 分钟足够兜住正常生成）
MAX_TASK_AGE_SECONDS = 30 * 60
#: 并发上限（035 §9.6）：一次提交 5 条不该同时打 5 个任务、扣 5 份钱
DEFAULT_CONCURRENCY = 2

_poll_semaphore: asyncio.Semaphore | None = None
_spawned: set[asyncio.Task] = set()


def _semaphore() -> asyncio.Semaphore:
    global _poll_semaphore
    if _poll_semaphore is None:
        concurrency = _video_concurrency()
        _poll_semaphore = asyncio.Semaphore(max(1, concurrency))
    return _poll_semaphore


def _video_concurrency() -> int:
    raw = settings_store.load().get("video_concurrency")
    try:
        return max(1, min(4, int(raw)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_CONCURRENCY


def active_video_model(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """生效的视频模型条目；未配置时抛带引导的 ValueError（适配器转人话）。"""
    settings = settings if settings is not None else settings_store.load()
    entries = [
        entry
        for entry in normalize_media_models(settings.get("media_models"))
        if entry["kind"] == "video"
    ]
    entry = next((item for item in entries if item["active"]), entries[0] if entries else None)
    if not entry:
        raise ValueError(
            "尚未配置视频模型：请在「设置 → 生成模型」里添加（供应商 / 模型 / API Key）"
        )
    if not str(entry.get("api_key") or "").strip():
        raise ValueError(
            f"视频模型「{entry.get('label') or entry.get('provider')}」没有配置 API Key，"
            "请在「设置 → 生成模型」里补上"
        )
    return entry


def estimate_cost(params: dict[str, Any], model_entry: dict[str, Any]) -> float | None:
    """预估费用（036 拍板要显示）：duration × price_per_second；没配单价返回 None。"""
    options = model_entry.get("options") if isinstance(model_entry.get("options"), dict) else {}
    price = options.get("price_per_second")
    try:
        price = float(price)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    try:
        duration = int(params.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0
    if price <= 0 or duration <= 0:
        return None
    return round(price * duration, 2)


def submit_video_task(
    *,
    prompt: str,
    params: dict[str, Any],
    session_id: str | None = None,
    call_id: str | None = None,
) -> dict[str, Any]:
    """校验 + 建任务 + 挂后台轮询；**同步返回**，绝不等待生成（035 §6）。

    返回 ``{"task": …, "duplicate": bool, "estimate": float|None}``。
    抛 ``ValueError`` 表示没到上游就失败（缺配置/缺图/URL 缺失），不扣费。
    """
    settings = settings_store.load()
    model_entry = active_video_model(settings)
    provider = str(model_entry.get("provider") or "").lower()

    # 幂等护栏：60s 内相同参数复用（重试按钮显式传 force=True 绕过）
    if not params.get("_force"):
        duplicate = media_tasks.find_recent_duplicate(
            provider=provider, prompt=prompt, params=params, seconds=60
        )
        if duplicate:
            return {"task": duplicate, "duplicate": True, "estimate": None}

    # 并发上限：worker 侧信号量控制真正轮询的并发；超出的行保持 queued
    running = media_tasks.count_running()
    concurrency = _video_concurrency()

    task = media_tasks.create_task(
        kind="video",
        provider=provider,
        prompt=prompt,
        params=dict(params),
        session_id=session_id,
        call_id=call_id,
        model=str(model_entry.get("model") or "") or None,
    )

    # 提交上游（同步，一次 HTTP POST）：拿到 remote_task_id 才算提交成功；
    # 失败 → 行标 failed + 抛给适配器（未到生成环节，不产生视频费用）
    entry_base = str(model_entry.get("base_url") or "")
    entry_key = str(model_entry.get("api_key") or "")
    entry_model = str(model_entry.get("model") or "")
    try:
        remote_id = get_provider(provider)["submit"](
            base_url=entry_base,
            api_key=entry_key,
            model=entry_model,
            prompt=prompt,
            params=params,
        )
    except ProviderError as exc:
        media_tasks.update_task(task["id"], status="failed", error=str(exc))
        _broadcast(task["id"], "failed")
        raise
    except Exception as exc:  # noqa: BLE001 - 网络层异常同样转人话
        media_tasks.update_task(task["id"], status="failed", error=f"提交视频任务失败：{exc}")
        _broadcast(task["id"], "failed")
        raise ProviderError(f"提交视频任务失败：{exc}") from exc

    task = media_tasks.update_task(task["id"], remote_task_id=remote_id)
    _spawn_poll(task["id"])
    estimate = estimate_cost(params, model_entry)
    return {"task": task, "duplicate": False, "estimate": estimate, "queued": running >= concurrency}


def _spawn_poll(task_id: str) -> None:
    """挂后台轮询协程；引用持有防 GC（asyncio 文档要求）。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("无事件循环，任务 %s 留待启动恢复", task_id)
        return
    spawned = loop.create_task(_poll_task(task_id))
    _spawned.add(spawned)
    spawned.add_done_callback(_spawned.discard)


def resume_pending() -> int:
    """启动恢复：把 queued/running 的行重新挂上轮询（035 §6 护栏 3）。"""
    resumed = 0
    for task in media_tasks.list_resumable():
        if task["kind"] != "video":
            continue
        _spawn_poll(task["id"])
        resumed += 1
    if resumed:
        logger.info("恢复 %d 个未完成的视频生成任务", resumed)
    return resumed


async def _poll_task(task_id: str) -> None:
    """后台轮询：拿到信号量才真正开始（并发上限）；每 10s 查一次上游。"""
    semaphore = _semaphore()
    async with semaphore:
        task = media_tasks.get_task(task_id)
        if not task or task["status"] in media_tasks.TERMINAL_STATUSES:
            return
        if not task.get("remote_task_id"):
            _finish(task_id, status="failed", error="任务缺少上游任务号，无法继续跟踪")
            return
        deadline = time.monotonic() + MAX_TASK_AGE_SECONDS
        if task["status"] != "running":
            media_tasks.update_task(task_id, status="running")
            _broadcast(task_id, "running")
        last_error: str | None = None
        while time.monotonic() < deadline:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            task = media_tasks.get_task(task_id)
            if not task or task["status"] in media_tasks.TERMINAL_STATUSES:
                return
            settings = settings_store.load()
            entry = _model_entry_for(settings, task["provider"])
            if not entry:
                _finish(task_id, status="failed", error="视频模型配置已被移除")
                return
            try:
                result = await asyncio.to_thread(
                    get_provider(task["provider"])["query"],
                    base_url=str(entry.get("base_url") or ""),
                    api_key=str(entry.get("api_key") or ""),
                    remote_task_id=str(task.get("remote_task_id") or ""),
                )
            except ProviderError as exc:
                last_error = str(exc)
                _finish(task_id, status="failed", error=last_error)
                return
            except Exception as exc:  # noqa: BLE001 - 网络抖动不该杀死任务，记下重试
                last_error = str(exc)
                logger.warning("查询任务 %s 失败：%s", task_id, exc)
                continue

            status = str(result.get("status") or "running")
            if status == "succeeded" and result.get("url"):
                try:
                    file_path = await asyncio.to_thread(
                        _download_and_write, task, str(result["url"])
                    )
                except Exception as exc:  # noqa: BLE001 - 下载失败=任务失败，视频还在云端
                    _finish(task_id, status="failed", error=f"视频下载失败：{exc}")
                    return
                _write_sidecars(task, file_path)
                _finish(task_id, status="succeeded", file_path=file_path)
                return
            if status in ("failed", "expired"):
                _finish(task_id, status=status, error=last_error or "上游任务未成功")
                return
        _finish(task_id, status="failed", error="视频生成超时，请稍后重试（不要重复提交）")


def _model_entry_for(settings: dict[str, Any], provider: str) -> dict[str, Any] | None:
    entries = [
        entry
        for entry in normalize_media_models(settings.get("media_models"))
        if entry["kind"] == "video" and entry.get("provider") == provider
    ]
    return next((entry for entry in entries if entry["active"]), entries[0] if entries else None)


def _finish(task_id: str, *, status: str, error: str | None = None, file_path: str | None = None) -> None:
    fields: dict[str, Any] = {"status": status}
    if error is not None:
        fields["error"] = error
    if file_path is not None:
        fields["file_path"] = file_path
    media_tasks.update_task(task_id, **fields)
    _broadcast(task_id, status)


def _broadcast(task_id: str, status: str) -> None:
    broadcast_changed(task_id, status)


def broadcast_changed(task_id: str, status: str) -> None:
    """状态变化广播：API 层（dismiss/reshow）与 worker 共用。"""
    try:
        events.broadcast("media_tasks_changed", {"task_id": task_id, "status": status})
    except Exception:  # noqa: BLE001 - 事件广播失败不影响任务本身
        logger.warning("media_tasks_changed 广播失败（task=%s）", task_id)


def _download_and_write(task: dict[str, Any], url: str) -> str:
    """下载成品到 ``output_dir/videos/``（重试 2 次），返回本地路径。

    云端 URL 只做一次性中转（MiniMax 任务留 7 天、链接有时效），不进消息。
    """
    import httpx

    target_dir = Path(output_dir()) / "videos"
    target_dir.mkdir(parents=True, exist_ok=True)
    name = _video_filename(task)
    target = target_dir / name
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with httpx.stream("GET", url, timeout=300, follow_redirects=True) as response:
                response.raise_for_status()
                tmp = target.with_suffix(target.suffix + ".part")
                with open(tmp, "wb") as handle:  # noqa: SIM115 - 流式写盘
                    for chunk in response.iter_bytes(chunk_size=1 << 20):
                        handle.write(chunk)
                tmp.replace(target)
            return str(target)
        except Exception as exc:  # noqa: BLE001 - 重试 2 次再放弃
            last_error = exc
            time.sleep(1 + attempt)
    raise RuntimeError(str(last_error or "下载失败"))


def _video_filename(task: dict[str, Any]) -> str:
    params = task.get("params") or {}
    raw = str(params.get("filename") or "").strip()
    slug = re.sub(r"[\\/:*?\"<>|\s]+", "-", raw).strip("-.")[:60]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{slug or 'video'}.mp4"


def _write_sidecars(task: dict[str, Any], video_path: str) -> None:
    """旁车文件：字幕 .srt + 旁白稿 .txt（036 拍板前 035 §7.7 的 P1 边界）。

    P1 没有烧制能力，.srt/.txt 只是**伴随产物**；文件缺失时任务不受影响。
    """
    params = task.get("params") or {}
    voiceover = str(params.get("voiceover") or "").strip()
    video = Path(video_path)
    try:
        if voiceover:
            (video.with_suffix(".txt")).write_text(voiceover, encoding="utf-8")
            if params.get("subtitles"):
                (video.with_suffix(".srt")).write_text(
                    _build_srt(voiceover, _task_duration(params)), encoding="utf-8"
                )
        elif params.get("subtitles"):
            # 没有口播稿时的字幕没有内容来源：只落一个说明文件，不装作有字幕
            (video.with_suffix(".srt")).write_text(
                "1\n00:00:00,000 --> 00:00:05,000\n（未提供口播文案，无法生成字幕内容）\n",
                encoding="utf-8",
            )
    except OSError as exc:
        logger.warning("旁车文件写入失败（task=%s）：%s", task["id"], exc)


def _task_duration(params: dict[str, Any]) -> int:
    try:
        return max(1, int(params.get("duration") or 5))
    except (TypeError, ValueError):
        return 5


def _build_srt(voiceover: str, duration: int) -> str:
    """把口播稿按句切分，均匀铺满整个时长（P1 的朴素实现，够 .srt 语义）。"""

    def _stamp(seconds: float) -> str:
        ms = int(round(seconds * 1000))
        hours, rest = divmod(ms, 3_600_000)
        minutes, rest = divmod(rest, 60_000)
        secs, millis = divmod(rest, 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    sentences = [part.strip() for part in re.split(r"[。！？!?\n]+", voiceover) if part.strip()]
    if not sentences:
        sentences = [voiceover.strip() or "（空）"]
    per = duration / len(sentences)
    blocks: list[str] = []
    for index, sentence in enumerate(sentences):
        start = index * per
        end = min(duration, (index + 1) * per)
        blocks.append(f"{index + 1}\n{_stamp(start)} --> {_stamp(end)}\n{sentence}\n")
    return "\n".join(blocks)


def resume_expired_remote() -> None:
    """把超过 MAX_TASK_AGE 的 running 行标为 failed（启动时调用，防僵尸行）。"""
    cutoff = (
        datetime.now(timezone.utc) - timedelta(seconds=MAX_TASK_AGE_SECONDS)
    ).strftime("%Y-%m-%dT%H:%M:%S")
    for task in media_tasks.list_tasks(statuses=["running"], limit=200):
        if str(task["created_at"]) < cutoff:
            _finish(task["id"], status="failed", error="视频生成超时，请稍后重试")
