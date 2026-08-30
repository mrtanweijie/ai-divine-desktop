import pytest

from durations import parse_duration


def test_hours():
    assert parse_duration("2h") == 7200


def test_minutes():
    assert parse_duration("12m") == 720


def test_seconds():
    assert parse_duration("45s") == 45


def test_none_raises_value_error():
    with pytest.raises(ValueError):
        parse_duration(None)


def test_empty_raises_value_error():
    with pytest.raises(ValueError):
        parse_duration("")


def test_garbage_raises_value_error():
    with pytest.raises(ValueError):
        parse_duration("soon")
