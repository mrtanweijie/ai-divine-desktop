import config

from service import call_remote


def test_default_timeout_used():
    assert call_remote("https://x.test")["timeout"] == config.DEFAULT_TIMEOUT


def test_default_timeout_is_30():
    assert call_remote("https://x.test")["timeout"] == 30


def test_explicit_timeout_wins():
    assert call_remote("https://x.test", timeout=5)["timeout"] == 5


def test_other_config_values_intact():
    assert config.MAX_RETRIES == 3
