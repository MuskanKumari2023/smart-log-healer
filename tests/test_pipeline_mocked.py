from unittest.mock import patch

from backend.judge import run_judge
from backend.models import BugFixResponse, JudgeResult, TestRunResult
from backend.pipeline import run_healing_pipeline


def test_pipeline_with_mocked_ai_and_judge():
    patch_response = BugFixResponse(
        explanation="Guarded null user record.",
        fixed_code=(
            "def get_user_email(user_id: int):\n"
            "    user_record = database_fetch_by_id(user_id)\n"
            "    if user_record is None:\n"
            "        return None\n"
            "    return user_record['email']\n\n"
            "def database_fetch_by_id(user_id: int):\n"
            "    if user_id == 999:\n"
            "        return None\n"
            "    return {'email': f'user{user_id}@example.com'}\n"
        ),
        confidence="high",
    )
    judge_response = JudgeResult(
        approved=True,
        security_score=9,
        logic_preserved=True,
        issues=[],
        summary="Safe minimal fix.",
    )

    trace = (
        "request_id=demo-1\n"
        "TypeError: 'NoneType' object is not subscriptable\n"
        "  File \"buggy.py\", line 3, in get_user_email"
    )

    with patch("backend.pipeline.generate_patch", return_value=patch_response), patch(
        "backend.pipeline.run_judge", return_value=judge_response
    ):
        result = run_healing_pipeline("none_type", trace)

    assert result.cache_hit is False
    assert result.test_result.passed
    assert result.judge_result is not None
    assert result.judge_result.approved


def test_pipeline_cache_hit_skips_ai(monkeypatch):
    from backend import cache

    cache.clear_cache()
    fixed = (
        "def get_user_email(user_id: int):\n"
        "    user_record = database_fetch_by_id(user_id)\n"
        "    if user_record is None:\n"
        "        return None\n"
        "    return user_record['email']\n\n"
        "def database_fetch_by_id(user_id: int):\n"
        "    if user_id == 999:\n"
        "        return None\n"
        "    return {'email': f'user{user_id}@example.com'}\n"
    )
    signature_trace = (
        "request_id=abc123\n"
        "TypeError: 'NoneType' object is not subscriptable\n"
        "  File \"buggy.py\", line 3, in get_user_email"
    )
    cache.store_fix(
        __import__("backend.analyzer", fromlist=["normalize_trace_signature"]).normalize_trace_signature(
            signature_trace
        ),
        fixed,
    )

    called = {"ai": 0}

    def fake_generate_patch(*args, **kwargs):
        called["ai"] += 1
        return BugFixResponse(explanation="should not run", fixed_code=fixed, confidence="high")

    variant_trace = (
        "request_id=xyz789\n"
        "TypeError: 'NoneType' object is not subscriptable\n"
        "  File \"buggy.py\", line 3, in get_user_email"
    )

    with patch("backend.pipeline.generate_patch", side_effect=fake_generate_patch):
        result = run_healing_pipeline("none_type", variant_trace)

    assert called["ai"] == 0
    assert result.cache_hit is True
    assert result.test_result.passed
    assert result.judge_skipped is True
    assert result.judge_result is None
