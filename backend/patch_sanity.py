from __future__ import annotations

import re


def top_level_function_names(code: str) -> set[str]:
    return set(re.findall(r"^def (\w+)\s*\(", code, re.MULTILINE))


def missing_top_level_functions(original: str, patched: str) -> list[str]:
    """Return function names present in original but missing from the patch."""
    missing = top_level_function_names(original) - top_level_function_names(patched)
    return sorted(missing)
