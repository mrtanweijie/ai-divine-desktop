"""视频生成服务层（035）回归：任务表 / 提交护栏 / 参数裁剪 / 面板能力差异。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.media import service
from app.config import settings_store
from app.db import media_tasks
from app.tools.registry import registry


# --------------------------------------------------------------------------
# 夹具
# --------------------------------------------------------------------------


def _setup_db(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "media.db"))
    from app import db as db_mod

    db_mod.init_db()


def _with_model(monkeypatch, *, provider: str = "minimax", price: float | None = None):
    """配置一个视频模型 + 假 provider（submit/query 不触网）。"""
    options: dict = {}
    if price is not None:
        options["price_per_second"] = price
    settings = {
        "media_models": [
            {
                "id": "mv1",
                "kind": "video",
                "provider": provider,
                "base_url": "https://api.minimaxi.com",
                "api_key": "sk-video",
                "model": "MiniMax-H3",
                "options": options,
                "active": True,
            }
        ]
    }
    monkeypatch.setattr(settings_store, "load", lambda: settings)

    calls: list[str] = []

    def fake_submit(**kwargs):
        calls.append(f"submit:{kwargs.get('model')}")
        return "remote-1"

    def fake_query(**kwargs):
        calls.append("query")
        return {"status": "running", "url": None}

    monkeypatch.setattr(
        service,
        "get_provider",
        lambda name: {"submit": fake_submit, "query": fake_query},
    )
    return calls


def _cancel_spawned():
    for task in list(service._spawned):
        task.cancel()


def _make_image(tmp_path: Path) -> str:
    path = tmp_path / "frame.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    return str(path)


# --------------------------------------------------------------------------
# media_tasks 仓储
# --------------------------------------------------------------------------


def test_task_crud_and_listing(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    task = media_tasks.create_task(
        kind="video", provider="minimax", prompt="海边日落", params={"duration": 5}
    )
    assert task["status"] == "queued"
    assert task["params"]["duration"] == 5

    updated = media_tasks.update_task(
        task["id"], status="succeeded", file_path="/x/a.mp4", extras={"dismissed": True}
    )
    assert updated["status"] == "succeeded"
    assert updated["extras"]["dismissed"] is True

    done = media_tasks.list_tasks(statuses=["succeeded"])
    assert [item["id"] for item in done] == [task["id"]]
    assert media_tasks.count_running() == 0


def test_find_recent_duplicate_matches_params(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    params = {"duration": 5, "resolution": "768P"}
    media_tasks.create_task(kind="video", provider="minimax", prompt="日落", params=params)
    hit = media_tasks.find_recent_duplicate(
        provider="minimax", prompt="日落", params={"resolution": "768P", "duration": 5}
    )
    assert hit is not None, "键序不同也应命中（canonical json）"
    miss = media_tasks.find_recent_duplicate(
        provider="minimax", prompt="日落", params={"duration": 10}
    )
    assert miss is None


# --------------------------------------------------------------------------
# submit_video_task
# --------------------------------------------------------------------------


def test_submit_creates_running_task_without_network(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    calls = _with_model(monkeypatch)
    result = service.submit_video_task(
        prompt="海边日落", params={"duration": 5}, session_id="s1", call_id="c1"
    )
    task = result["task"]
    assert task["status"] in ("queued", "running")
    assert calls and calls[0].startswith("submit:"), "提交必须打到上游（拿到 remote id）"
    assert task["remote_task_id"] == "remote-1"
    assert result["duplicate"] is False
    assert result["estimate"] is None, "未配置单价 → 不显示费用"
    _cancel_spawned()


def test_submit_is_idempotent_within_window(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    _with_model(monkeypatch)
    first = service.submit_video_task(prompt="日落", params={"duration": 5})
    second = service.submit_video_task(prompt="日落", params={"duration": 5})
    assert second["duplicate"] is True
    assert second["task"]["id"] == first["task"]["id"]
    _cancel_spawned()


def test_estimate_uses_price_from_model_options(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    _with_model(monkeypatch, price=0.07)
    result = service.submit_video_task(prompt="日落", params={"duration": 5})
    assert result["estimate"] == 0.35
    _cancel_spawned()


# --------------------------------------------------------------------------
# video_generate 适配器：校验与静默裁剪（都不触网）
# --------------------------------------------------------------------------


def _adapter():
    return registry.get("video_generate")


def _run(adapter, args):
    return asyncio.run(adapter.run(None, args))


def test_no_model_configured_is_actionable_error(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    monkeypatch.setattr(settings_store, "load", lambda: {})
    with pytest.raises(Exception) as excinfo:
        _run(_adapter(), {"prompt": "日落"})
    assert "生成模型" in str(excinfo.value)


def test_missing_frame_is_needs_media(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    _with_model(monkeypatch)
    with pytest.raises(Exception) as excinfo:
        _run(_adapter(), {"prompt": "x", "mode": "first_frame"})
    assert "needs_media" in str(excinfo.value)


def test_frame_must_be_image(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    _with_model(monkeypatch)
    text_file = tmp_path / "frame.txt"
    text_file.write_text("不是图片")
    with pytest.raises(Exception) as excinfo:
        _run(_adapter(), {"prompt": "x", "first_frame": str(text_file)})
    assert "必须是图片" in str(excinfo.value)


def test_article_without_url_is_needs_source(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    _with_model(monkeypatch)
    with pytest.raises(Exception) as excinfo:
        _run(_adapter(), {"prompt": "x", "source": "article"})
    assert "needs_source" in str(excinfo.value)


def test_zhipu_drops_last_frame_with_note(tmp_path, monkeypatch):
    """智谱不支持尾帧：静默裁剪（mode 降级）并在 message 里说明。"""
    _setup_db(tmp_path, monkeypatch)
    _with_model(monkeypatch, provider="zhipu")
    frame = _make_image(tmp_path)
    result = _run(
        _adapter(),
        {"prompt": "日落", "first_frame": frame, "last_frame": frame, "session_id": "s"},
    )
    assert "不支持尾帧" in result.message
    assert result.data["status"] in ("queued", "running")
    _cancel_spawned()


def test_out_of_range_params_are_clamped_with_note(tmp_path, monkeypatch):
    """模型乱填参数：就近取合法值 + message 写明实际参数（035 §11 风险表）。"""
    _setup_db(tmp_path, monkeypatch)
    _with_model(monkeypatch, provider="zhipu")
    result = _run(
        _adapter(),
        {"prompt": "日落", "duration": 8, "resolution": "2K", "aspect_ratio": "21:9"},
    )
    assert result.data["duration"] == 10, "8s 不在智谱合法集（5/10），就近取 10"
    assert "就近取 10s" in result.message
    _cancel_spawned()


# --------------------------------------------------------------------------
# 旁车文件：.srt / .txt（P1 边界，§7.7）
# --------------------------------------------------------------------------


def test_build_srt_splits_sentences_across_duration(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    srt = service._build_srt("第一句。第二句！第三句", 6)
    assert srt.count("-->") == 3
    assert "00:00:02,000 --> 00:00:04,000" in srt
    assert "第三句" in srt


def test_write_sidecars_creates_srt_and_txt(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    task = media_tasks.create_task(
        kind="video",
        provider="minimax",
        prompt="p",
        params={"duration": 5, "subtitles": True, "voiceover": "甲。乙。"},
    )
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    service._write_sidecars(task, str(video))
    assert video.with_suffix(".srt").exists()
    assert video.with_suffix(".txt").read_text(encoding="utf-8") == "甲。乙。"


# --------------------------------------------------------------------------
# video_brief 面板
# --------------------------------------------------------------------------


def test_video_brief_panel_validates_and_hides_last_frame_for_zhipu(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    from app.tools.adapters.video_brief import prepare
    from app.tools.ui.validator import validate_ui_surface
    from app.tools.ui.versions.v0_9_1 import to_messages

    _with_model(monkeypatch, provider="zhipu")
    surface = prepare({})["surface"]
    validation = validate_ui_surface(surface)
    assert validation.ok, [e.message for e in validation.errors]
    ids = {item["id"] for item in surface["components"]}
    assert "last_pick" not in ids, "智谱不支持尾帧，整行不渲染"
    assert "last_label" not in ids
    assert to_messages(validation.normalized or surface)

    # 回流 context 覆盖所有 form 字段
    go = next(item for item in surface["components"] if item["id"] == "go")
    context_keys = {item["key"] for item in go["action"]["context"]}
    assert context_keys == set(surface["data"]["form"])


def test_video_brief_duration_desc_carries_price(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    from app.tools.adapters.video_brief import prepare

    _with_model(monkeypatch, price=0.07)
    surface = prepare({})["surface"]
    dur = next(item for item in surface["components"] if item["id"] == "dur_pick")
    priced = {option["value"]: option.get("desc") for option in dur["options"]}
    assert priced["5"] == "≈¥0.35"
    assert priced["10"] == "≈¥0.70"
    assert priced[""] is None, "「智能」没有确定时长，不带价格"

    # 未配置单价：desc 全部缺席（绝不显示 ¥0）
    _with_model(monkeypatch)
    surface = prepare({})["surface"]
    dur = next(item for item in surface["components"] if item["id"] == "dur_pick")
    assert all("desc" not in option for option in dur["options"])
