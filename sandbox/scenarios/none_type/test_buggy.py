from buggy import get_user_email


def test_existing_user_email():
    assert get_user_email(1) == "user1@example.com"


def test_missing_user_returns_none():
    assert get_user_email(999) is None  # fails on buggy code (TypeError)
