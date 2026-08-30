from slugs import slugify


def test_basic():
    assert slugify("Hello World") == "hello-world"


def test_accents_folded_to_ascii():
    assert slugify("Café Über") == "cafe-uber"


def test_collapses_dashes():
    assert slugify("a  --  b!!") == "a-b"


def test_strips_edges():
    assert slugify("  Résumé  ") == "resume"


def test_drops_cjk():
    assert slugify("笔记 notes") == "notes"
