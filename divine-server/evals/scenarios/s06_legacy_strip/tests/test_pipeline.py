from pipeline import clean_document, clean_line


def test_spaces_trimmed():
    assert clean_line("  hello world  ") == "hello world"


def test_tabs_trimmed():
    assert clean_line("\thello\t") == "hello"


def test_internal_spaces_collapsed():
    assert clean_line("a    b") == "a b"


def test_document_mixed_whitespace():
    assert clean_document("  a \n\tb\t\n c ") == ["a", "b", "c"]
