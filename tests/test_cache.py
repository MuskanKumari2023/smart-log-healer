from backend.analyzer import normalize_trace_signature
from backend.cache import clear_cache, lookup_cached_fix, store_fix


def test_cache_miss_returns_none():
    clear_cache()
    assert lookup_cached_fix("TypeError: missing") is None


def test_cache_hit_after_store():
    clear_cache()
    signature = normalize_trace_signature("TypeError: boom request_id=abc")
    store_fix(signature, "fixed = True")
    variant = normalize_trace_signature("TypeError: boom request_id=xyz")
    hit = lookup_cached_fix(variant)
    assert hit is not None
    assert hit.fixed_code == "fixed = True"
    assert hit.similarity_score >= 0.85


def test_clear_cache_resets_state():
    clear_cache()
    store_fix("sig", "code")
    clear_cache()
    assert lookup_cached_fix("sig") is None
