"""Settings multi-model configuration helpers."""

from app.config import (
    active_model,
    apply_legacy_to_active,
    merge_model_updates,
    mirror_active,
    normalize_models,
)


def test_fresh_models_defaults():
    settings = {"provider": "auto", "model": "deepseek-v4-flash"}
    settings["models"] = normalize_models(None, settings)
    assert len(settings["models"]) == 1
    entry = settings["models"][0]
    assert entry["active"] is True
    assert entry["id"] == "default"
    assert entry["model"] == "deepseek-v4-flash"


def test_legacy_fields_migrate_into_models():
    legacy = {
        "provider": "langchain",
        "model": "deepseek-v4-pro",
        "base_url": "https://example.com",
        "api_key": "sk-legacy",
    }
    models = normalize_models(None, legacy)
    assert models[0]["model"] == "deepseek-v4-pro"
    assert models[0]["base_url"] == "https://example.com"
    assert models[0]["api_key"] == "sk-legacy"
    assert models[0]["provider"] == "langchain"


def test_normalize_ensures_single_active():
    raw = [
        {"id": "a", "name": "A", "model": "m1", "active": True},
        {"id": "b", "name": "B", "model": "m2", "active": True},
        {"id": "c", "name": "C", "model": "m3", "active": False},
    ]
    models = normalize_models(raw, {})
    actives = [entry["id"] for entry in models if entry["active"]]
    assert actives == ["a"]


def test_normalize_picks_first_when_none_active():
    raw = [{"id": "x", "name": "X", "model": "m1", "active": False}]
    models = normalize_models(raw, {})
    assert models[0]["active"] is True


def test_merge_keeps_stored_key_when_submitted_empty():
    stored = [
        {
            "id": "default",
            "name": "D",
            "provider": "langchain",
            "model": "m1",
            "base_url": "u",
            "api_key": "sk-kept",
            "active": True,
        }
    ]
    submitted = [
        {
            "id": "default",
            "name": "D",
            "provider": "langchain",
            "model": "m1",
            "base_url": "u",
            "api_key": "",
            "active": True,
        },
        {
            "name": "GLM",
            "provider": "langchain",
            "model": "glm-4.6v",
            "base_url": "https://open.bigmodel.cn",
            "api_key": "sk-glm",
            "active": False,
        },
    ]
    merged = merge_model_updates(stored, submitted)
    by_id = {entry["id"]: entry for entry in merged}
    assert by_id["default"]["api_key"] == "sk-kept"
    glm = [entry for entry in merged if entry["name"] == "GLM"][0]
    assert glm["api_key"] == "sk-glm"
    assert glm["id"]  # new entries get an id


def test_merge_replaces_key_when_submitted_new():
    stored = [
        {
            "id": "a",
            "name": "A",
            "provider": "langchain",
            "model": "m1",
            "base_url": "u",
            "api_key": "old",
            "active": True,
        }
    ]
    submitted = [
        {
            "id": "a",
            "name": "A",
            "provider": "langchain",
            "model": "m1",
            "base_url": "u",
            "api_key": "new",
            "active": True,
        }
    ]
    merged = merge_model_updates(stored, submitted)
    assert merged[0]["api_key"] == "new"


def test_mirror_active_syncs_top_level():
    settings = {
        "models": [
            {
                "id": "a",
                "name": "A",
                "provider": "langchain",
                "model": "m1",
                "base_url": "u1",
                "api_key": "k1",
                "active": False,
            },
            {
                "id": "b",
                "name": "B",
                "provider": "mock",
                "model": "m2",
                "base_url": "u2",
                "api_key": "k2",
                "active": True,
            },
        ]
    }
    mirror_active(settings)
    assert settings["provider"] == "mock"
    assert settings["model"] == "m2"
    assert settings["api_key"] == "k2"


def test_active_model_falls_back_to_first():
    settings = {
        "models": [
            {"id": "a", "name": "A", "model": "m1", "active": False},
            {"id": "b", "name": "B", "model": "m2", "active": False},
        ]
    }
    entry = active_model(settings)
    assert entry["id"] == "a"


def test_apply_legacy_to_active_updates_active_entry():
    settings = {
        "models": [
            {
                "id": "a",
                "name": "A",
                "provider": "langchain",
                "model": "m1",
                "base_url": "u1",
                "api_key": "k1",
                "active": True,
            }
        ]
    }
    apply_legacy_to_active(settings, {"provider": "mock", "model": "local"})
    assert settings["models"][0]["provider"] == "mock"
    assert settings["models"][0]["model"] == "m1"  # empty model ignored


def test_strip_local_model_entries_removes_virtual_entries():
    """本地模型虚拟条目（id="local"）绝不能被持久化。

    历史缺陷：GET 时动态注入的 local 条目被前端回传保存，与下次注入叠加，
    模型列表按保存次数翻倍（出现多个重复的 Qwen2.5-1.5B-Instruct）。
    """
    from app.api.settings import _strip_local_model_entries

    models = [
        {"id": "m1", "name": "DeepSeek", "model": "deepseek-v4-flash"},
        {"id": "local", "name": "Qwen2.5-1.5B-Instruct", "provider": "local"},
        {"id": "m2", "name": "MiMo", "model": "mimo-v2.5-pro"},
        {"id": "local", "name": "Qwen2.5-1.5B-Instruct", "provider": "local"},
        {"id": "local", "name": "Qwen2.5-1.5B-Instruct", "provider": "local"},
    ]
    stripped = _strip_local_model_entries(models)
    assert [m["id"] for m in stripped] == ["m1", "m2"]


def test_merge_after_strip_does_not_reintroduce_local():
    from app.api.settings import _strip_local_model_entries
    from app.config import merge_model_updates

    stored = [
        {"id": "local", "name": "Qwen2.5-1.5B-Instruct", "provider": "local"},
        {"id": "local", "name": "Qwen2.5-1.5B-Instruct", "provider": "local"},
        {"id": "local", "name": "Qwen2.5-1.5B-Instruct", "provider": "local"},
        {"id": "m1", "name": "DeepSeek", "model": "deepseek-v4-flash"},
    ]
    submitted = [
        {"id": "m1", "name": "DeepSeek", "model": "deepseek-v4-flash", "api_key": ""},
        {"id": "local", "name": "Qwen2.5-1.5B-Instruct", "provider": "local"},
    ]
    merged = merge_model_updates(
        _strip_local_model_entries(stored),
        _strip_local_model_entries(submitted),
    )
    assert all(m["id"] != "local" for m in merged)
    assert [m["id"] for m in merged] == ["m1"]
