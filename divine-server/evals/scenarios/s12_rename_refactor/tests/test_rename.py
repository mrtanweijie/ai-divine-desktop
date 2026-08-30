def test_new_api_exists():
    from store import load_records

    assert load_records("users")[0]["name"] == "Ann"


def test_old_name_gone():
    import store

    assert not hasattr(store, "fetch_data")


def test_callers_still_work():
    from api import get_users
    from cache_layer import TableCache
    from report import render_logs

    assert get_users()[1]["name"] == "Bob"
    assert render_logs() == "1: boot"
    assert TableCache().rows("logs")[0]["msg"] == "boot"
