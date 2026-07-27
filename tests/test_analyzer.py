from backend.analyzer import (
    calculate_levenshtein_distance,
    get_log_similarity_score,
    normalize_trace_signature,
    parse_stack_trace,
)


def test_levenshtein_empty_strings():
    assert calculate_levenshtein_distance("", "") == 0


def test_levenshtein_kitten_sitting():
    assert calculate_levenshtein_distance("kitten", "sitting") == 3


def test_similarity_score_identical():
    assert get_log_similarity_score("abc", "abc") == 1.0


def test_normalize_trace_signature_strips_request_ids():
    trace_a = "request_id=abc123\nTypeError: boom"
    trace_b = "request_id=xyz789\nTypeError: boom"
    assert normalize_trace_signature(trace_a) == normalize_trace_signature(trace_b)


def test_similar_traces_after_normalization():
    trace_a = (
        "request_id=abc123 timestamp=2026-07-18T10:00:00Z\n"
        "TypeError: 'NoneType' object is not subscriptable\n"
        "  File \"buggy.py\", line 3, in get_user_email"
    )
    trace_b = (
        "request_id=xyz789 timestamp=2026-07-18T11:30:00Z\n"
        "TypeError: 'NoneType' object is not subscriptable\n"
        "  File \"buggy.py\", line 3, in get_user_email"
    )
    score = get_log_similarity_score(
        normalize_trace_signature(trace_a),
        normalize_trace_signature(trace_b),
    )
    assert score >= 0.85


def test_dissimilar_traces_score_lower():
    a = normalize_trace_signature("TypeError: bad\nFile buggy.py line 3")
    b = normalize_trace_signature("ZeroDivisionError: zero\nFile analytics.py line 8")
    assert get_log_similarity_score(a, b) < 0.85


def test_parse_stack_trace_extracts_file_and_line():
    trace = (
        "TypeError: 'NoneType' object is not subscriptable\n"
        "  File \"buggy.py\", line 3, in get_user_email\n"
        "    return user_record['email']"
    )
    parsed = parse_stack_trace(trace)
    assert parsed.error_type == "TypeError"
    assert parsed.file == "buggy.py"
    assert parsed.line == 3
