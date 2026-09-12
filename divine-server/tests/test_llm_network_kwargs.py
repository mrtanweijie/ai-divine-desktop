"""max_retries / timeout 显式化：网络参数下发与容错。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _prepare_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DIVINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DIVINE_WORKSPACE_DIR", str(tmp_path / "workspace"))


def _entry(**overrides):
    entry = {
        "model": "deepseek-flash",
        "api_key": "sk-test",
        "base_url": "https://api.deepseek.com",
    }
    entry.update(overrides)
    return entry


def _noop_stream():
    return


def test_network_kwargs_defaults(monkeypatch, tmp_path):
    _prepare_env(monkeypatch, tmp_path)
    from app.llm.langchain import _network_kwargs

    kwargs = _network_kwargs(_entry())
    assert kwargs["max_retries"] == 2
    # 未配置 timeout 时不下发，保留 openai 客户端默认行为
    assert "request_timeout" not in kwargs


def test_network_kwargs_overrides(monkeypatch, tmp_path):
    _prepare_env(monkeypatch, tmp_path)
    from app.llm.langchain import _network_kwargs

    kwargs = _network_kwargs(_entry(max_retries=5, timeout=120))
    assert kwargs["max_retries"] == 5
    assert kwargs["request_timeout"] == 120.0

    # 非法值回退默认，不抛异常
    kwargs = _network_kwargs(_entry(max_retries="abc", timeout="x"))
    assert kwargs["max_retries"] == 2
    assert "request_timeout" not in kwargs


def test_deepseek_provider_receives_retries(monkeypatch, tmp_path):
    _prepare_env(monkeypatch, tmp_path)
    from app.llm.langchain import ChatDeepSeekProvider

    provider = ChatDeepSeekProvider(entry=_entry(max_retries=7))
    assert provider.llm.max_retries == 7

    provider = ChatDeepSeekProvider(entry=_entry())
    assert provider.llm.max_retries == 2


def test_openai_provider_receives_retries(monkeypatch, tmp_path):
    _prepare_env(monkeypatch, tmp_path)
    from app.llm.langchain import OpenAIChatProvider

    provider = OpenAIChatProvider(entry=_entry(model="gpt-4o-mini", max_retries=0))
    assert provider.llm.max_retries == 0

    provider = OpenAIChatProvider(entry=_entry(model="gpt-4o-mini", timeout=45))
    assert provider.llm.request_timeout == 45.0
