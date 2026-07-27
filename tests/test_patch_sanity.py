from backend.patch_sanity import missing_top_level_functions


def test_detects_omitted_helper_function():
    original = (
        "def get_user_email(user_id: int):\n"
        "    return database_fetch_by_id(user_id)\n\n"
        "def database_fetch_by_id(user_id: int):\n"
        "    return None\n"
    )
    patched = "def get_user_email(user_id: int):\n    return None\n"
    assert missing_top_level_functions(original, patched) == ["database_fetch_by_id"]
