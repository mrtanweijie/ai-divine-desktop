from cache import FetchCache


def test_key_without_params():
    assert FetchCache.build_key("https://x.test/a", None) == "https://x.test/a"


def test_key_includes_sorted_params():
    key = FetchCache.build_key("https://x.test/a", {"b": "2", "a": "1"})
    assert "a=1" in key
    assert "b=2" in key
    assert key.index("a=1") < key.index("b=2")


def test_different_params_different_entries():
    cache = FetchCache()
    cache.put("https://x.test/a", "page-1", params={"page": "1"})
    cache.put("https://x.test/a", "page-2", params={"page": "2"})
    assert cache.get("https://x.test/a", params={"page": "1"}) == "page-1"
    assert cache.get("https://x.test/a", params={"page": "2"}) == "page-2"


def test_same_params_share_entry():
    cache = FetchCache()
    cache.put("https://x.test/a", "body", params={"q": "z"})
    assert cache.get("https://x.test/a", params={"q": "z"}) == "body"


def test_no_params_share_entry():
    cache = FetchCache()
    cache.put("https://x.test/a", "body")
    assert cache.get("https://x.test/a") == "body"
