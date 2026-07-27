from __future__ import annotations

from backend.analyzer import get_log_similarity_score
from backend.models import CacheLookupResult

SIMILARITY_THRESHOLD = 0.85

# normalized_signature -> fixed_code
HISTORICAL_CACHE: dict[str, str] = {}


def lookup_cached_fix(signature: str) -> CacheLookupResult | None:
    """Return a cached fix if any historical signature is similar enough."""
    best_match: CacheLookupResult | None = None
    for cached_sig, fix in HISTORICAL_CACHE.items():
        score = get_log_similarity_score(signature, cached_sig)
        if score >= SIMILARITY_THRESHOLD and (
            best_match is None or score > best_match.similarity_score
        ):
            best_match = CacheLookupResult(
                fixed_code=fix,
                similarity_score=score,
                matched_signature=cached_sig,
            )
    return best_match


def store_fix(signature: str, fixed_code: str) -> None:
    """Persist a validated fix for future cache hits."""
    HISTORICAL_CACHE[signature] = fixed_code


def clear_cache() -> None:
    """Reset cache — useful for tests and demo resets."""
    HISTORICAL_CACHE.clear()


def cache_entry_count() -> int:
    """Return number of cached fix signatures."""
    return len(HISTORICAL_CACHE)
