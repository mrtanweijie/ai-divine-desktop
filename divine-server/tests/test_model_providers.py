"""模型提供商目录：JSON 配置文件加载/保存/增删 与 API。"""

import json
from pathlib import Path


def _init(tmp_path, monkeypatch):
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "ws"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "m.db"))
    from app import model_providers

    return model_providers


def test_load_auto_creates_default_file(tmp_path, monkeypatch):
    mp = _init(tmp_path, monkeypatch)
    providers, path = mp.load_model_providers()
    assert path.exists()
    assert path.name == "divine-model-provider.json"
    values = [p["value"] for p in providers]
    assert values[:3] == ["deepseek", "xiaomi", "glm"]
    assert values[-1] == "custom"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved[0]["default_model"] == "deepseek-flash"


def test_file_overrides_defaults(tmp_path, monkeypatch):
    mp = _init(tmp_path, monkeypatch)
    path = mp.providers_config_path()
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            [
                {
                    "value": "acme",
                    "label": "Acme AI",
                    "base_url": "https://api.acme.cn/v1",
                    "default_model": "acme-max",
                    "list": ["acme-max", "acme-lite"],
                    "prefix": ["acme"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    providers, _ = mp.load_model_providers()
    assert [p["value"] for p in providers] == ["acme"]
    assert providers[0]["list"] == ["acme-max", "acme-lite"]


def test_invalid_entries_are_dropped(tmp_path, monkeypatch):
    mp = _init(tmp_path, monkeypatch)
    path = mp.providers_config_path()
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            [
                {"label": "没有 value"},
                "不是对象",
                {"value": "ok", "label": "有效", "list": ["m1", 42, ""]},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    providers, _ = mp.load_model_providers()
    assert [p["value"] for p in providers] == ["ok"]
    assert providers[0]["list"] == ["m1"]  # 非字符串项被清洗


def test_upsert_inserts_before_custom_and_updates_in_place(tmp_path, monkeypatch):
    mp = _init(tmp_path, monkeypatch)
    providers = mp.upsert_model_provider(
        {"value": "acme", "label": "Acme", "list": ["acme-1"], "prefix": ["acme"]}
    )
    values = [p["value"] for p in providers]
    assert "acme" in values
    assert values[-1] == "custom"  # 新提供商排在 custom 之前

    providers = mp.upsert_model_provider(
        {"value": "acme", "label": "Acme AI", "default_model": "acme-2", "list": ["acme-2"]}
    )
    acme = next(p for p in providers if p["value"] == "acme")
    assert acme["label"] == "Acme AI"  # 原位更新
    assert values.count("acme") == 1


def test_remove_and_reserved_guard(tmp_path, monkeypatch):
    mp = _init(tmp_path, monkeypatch)
    providers = mp.remove_model_provider("xiaomi")
    assert "xiaomi" not in [p["value"] for p in providers]

    import pytest

    for reserved in ("custom", "local"):
        with pytest.raises(ValueError):
            mp.remove_model_provider(reserved)
    with pytest.raises(ValueError):
        mp.remove_model_provider("不存在")


def test_api_get_put_roundtrip(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        body = client.get("/api/model-providers").json()
        assert body["providers"][0]["value"] == "deepseek"
        assert body["path"].endswith("divine-model-provider.json")

        body["providers"][0]["list"].append("deepseek-new")
        resp = client.put("/api/model-providers", json={"providers": body["providers"]})
        assert resp.status_code == 200

        again = client.get("/api/model-providers").json()
        assert "deepseek-new" in again["providers"][0]["list"]

        resp = client.put("/api/model-providers", json={"providers": []})
        assert resp.status_code == 400
