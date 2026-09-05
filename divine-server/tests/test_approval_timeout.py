"""审批等待超时：settings.json 的 approval_timeout 可覆盖默认 180s。"""

from app.agent.core.constants import approval_timeout_seconds


def test_defaults_when_unconfigured():
    assert approval_timeout_seconds(None) == 180
    assert approval_timeout_seconds({}) == 180


def test_settings_override():
    assert approval_timeout_seconds({"approval_timeout": 600}) == 600


def test_floor_and_invalid_fall_back():
    assert approval_timeout_seconds({"approval_timeout": 5}) == 30
    assert approval_timeout_seconds({"approval_timeout": "abc"}) == 180
    assert approval_timeout_seconds({"approval_timeout": 0}) == 180
