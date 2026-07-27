from backend.validator import validate_patch

NONE_TYPE_FIX = """def get_user_email(user_id: int):
    user_record = database_fetch_by_id(user_id)
    if user_record is None:
        return None
    return user_record["email"]


def database_fetch_by_id(user_id: int):
    if user_id == 999:
        return None
    return {"email": f"user{user_id}@example.com"}
"""

DIVISION_FIX = """def calculate_ctr(total_clicks: int, total_impressions: int) -> float:
    if total_impressions == 0:
        return 0.0
    return total_clicks / total_impressions
"""

INDEX_FIX = """def first_item(items: list):
    if not items:
        return None
    return items[0]
"""


def test_known_good_none_type_fix_passes_pytest():
    result = validate_patch("none_type", NONE_TYPE_FIX)
    assert result.passed, result.terminal_output


def test_known_good_division_fix_passes_pytest():
    result = validate_patch("division_by_zero", DIVISION_FIX)
    assert result.passed, result.terminal_output


def test_known_good_index_fix_passes_pytest():
    result = validate_patch("index_error", INDEX_FIX)
    assert result.passed, result.terminal_output


def test_buggy_code_fails_pytest():
    buggy = "def get_user_email(user_id: int):\n    return None['email']\n"
    result = validate_patch("none_type", buggy)
    assert not result.passed
