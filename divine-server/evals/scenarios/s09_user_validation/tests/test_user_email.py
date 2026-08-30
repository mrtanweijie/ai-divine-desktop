import pytest

from models import User


def test_valid_email_ok():
    user = User("Ann", "ann@example.com")
    assert user.email == "ann@example.com"


def test_is_valid_email_true():
    assert User.is_valid_email("ann@example.com") is True


def test_missing_at_raises():
    with pytest.raises(ValueError):
        User("Ann", "ann.example.com")


def test_two_at_raises():
    with pytest.raises(ValueError):
        User("Ann", "a@b@c")


def test_empty_local_raises():
    with pytest.raises(ValueError):
        User("Ann", "@example.com")


def test_domain_without_dot_raises():
    with pytest.raises(ValueError):
        User("Ann", "ann@localhost")


def test_domain_leading_dot_raises():
    with pytest.raises(ValueError):
        User("Ann", "ann@.com")


def test_domain_trailing_dot_raises():
    with pytest.raises(ValueError):
        User("Ann", "ann@example.")


def test_space_in_email_raises():
    with pytest.raises(ValueError):
        User("Ann", "ann example@x.com")
