"""media_models（生成模型配置，036）：归一 / 合并 / 掩码。

与 ``test_settings_models.py`` 同范式，但只测纯函数——
HTTP 层的掩码在 ``api/settings._public`` 里，字段映射简单到不值得起 TestClient。
"""

from __future__ import annotations

from app.config import (
    active_media_model,
    merge_media_models,
    normalize_media_models,
)
from app.api.settings import _public


def test_normalize_drops_unknown_kind():
    raw = [
        {"id": "a", "kind": "image", "provider": "minimax"},
        {"id": "b", "kind": "audio", "provider": "x"},  # 非法 kind 整条丢弃
        {"id": "c"},  # 缺 kind 丢弃
        "not-a-dict",  # 非对象丢弃
    ]
    entries = normalize_media_models(raw)
    assert [entry["id"] for entry in entries] == ["a"]
    assert entries[0]["kind"] == "image"
    assert entries[0]["options"] == {}


def test_normalize_single_active_per_kind():
    """每个 kind 至多一个 active：后提交者获胜（列表后面的赢）。"""
    raw = [
        {"id": "a", "kind": "image", "active": True},
        {"id": "b", "kind": "image", "active": True},
        {"id": "v", "kind": "video", "active": True},
    ]
    entries = normalize_media_models(raw)
    actives = {(entry["kind"], entry["id"]) for entry in entries if entry["active"]}
    assert actives == {("image", "b"), ("video", "v")}


def test_merge_keeps_prev_key_when_submitted_empty():
    """与 models 同语义：前端不回传 key（空串）时保留已存密钥。"""
    stored = [
        {"id": "m1", "kind": "image", "provider": "minimax", "api_key": "sk-old"}
    ]
    submitted = [
        {"id": "m1", "kind": "image", "provider": "minimax", "api_key": "", "label": "改名"}
    ]
    merged = merge_media_models(stored, submitted)
    assert merged[0]["api_key"] == "sk-old"
    assert merged[0]["label"] == "改名"


def test_merge_new_entry_and_kind_fallback():
    stored: list = []
    submitted = [
        {"id": "v1", "kind": "video", "provider": "zhipu", "api_key": "sk-v"},
        {"id": "x1", "kind": "audio", "api_key": "sk-x"},  # 非法 kind → 回落 image
    ]
    merged = merge_media_models(stored, submitted)
    kinds = {entry["id"]: entry["kind"] for entry in merged}
    assert kinds["v1"] == "video"
    assert kinds["x1"] == "image"


def test_active_media_model_prefers_active_then_first():
    stored = [
        {"id": "a", "kind": "image", "active": False},
        {"id": "b", "kind": "image", "active": True},
        {"id": "c", "kind": "image", "active": False},
    ]
    entries = normalize_media_models(stored)
    assert active_media_model({"media_models": entries}, "image")["id"] == "b"
    # 没有 active → 第一个
    stored[1]["active"] = False
    entries = normalize_media_models(stored)
    assert active_media_model({"media_models": entries}, "image")["id"] == "a"


def test_public_masks_api_key():
    """GET /api/settings 永不回传 key 明文，只给 has_api_key。"""
    settings = {
        "media_models": [
            {"id": "m1", "kind": "image", "provider": "minimax", "api_key": "sk-secret"}
        ]
    }
    public = _public(settings)
    assert len(public["media_models"]) == 1
    entry = public["media_models"][0]
    assert entry["has_api_key"] is True
    assert "api_key" not in entry
