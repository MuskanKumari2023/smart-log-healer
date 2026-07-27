from buggy import first_item


def test_non_empty_list():
    assert first_item(["a", "b"]) == "a"


def test_empty_list():
    assert first_item([]) is None  # fails on buggy code (IndexError)
