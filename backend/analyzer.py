from __future__ import annotations

import re

from backend.models import ParsedTrace

_FILE_LINE_PATTERN = re.compile(
    r'File\s+["\']([^"\']+)["\'],\s+line\s+(\d+)',
    re.IGNORECASE,
)
_ISO_TIMESTAMP_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)
_UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_HEX_ADDRESS_PATTERN = re.compile(r"\b0x[0-9a-fA-F]+\b")
_REQUEST_ID_PATTERN = re.compile(r"request_id\s*=\s*\S+", re.IGNORECASE)
_TIMESTAMP_KV_PATTERN = re.compile(r"timestamp\s*=\s*\S+", re.IGNORECASE)
_NUMERIC_ID_PATTERN = re.compile(r"\breq-\d+\b", re.IGNORECASE)


def calculate_levenshtein_distance(str1: str, str2: str) -> int:
    """Compute edit distance using a 2D dynamic programming grid."""
    m, n = len(str1), len(str2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if str1[i - 1] == str2[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost,
            )
    return dp[m][n]


def get_log_similarity_score(log1: str, log2: str) -> float:
    """Normalize edit distance into a 0.0-1.0 similarity score."""
    distance = calculate_levenshtein_distance(log1, log2)
    max_len = max(len(log1), len(log2))
    if max_len == 0:
        return 1.0
    return 1.0 - (distance / max_len)


def normalize_trace_signature(stack_trace: str) -> str:
    """Strip volatile fields so near-duplicate errors cluster together."""
    normalized = stack_trace.strip()
    normalized = _ISO_TIMESTAMP_PATTERN.sub("<TIMESTAMP>", normalized)
    normalized = _UUID_PATTERN.sub("<UUID>", normalized)
    normalized = _REQUEST_ID_PATTERN.sub("request_id=<ID>", normalized)
    normalized = _TIMESTAMP_KV_PATTERN.sub("timestamp=<TIMESTAMP>", normalized)
    normalized = _NUMERIC_ID_PATTERN.sub("req-<ID>", normalized)
    normalized = _HEX_ADDRESS_PATTERN.sub("<ADDR>", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def parse_stack_trace(stack_trace: str) -> ParsedTrace:
    """Parse exception type, message, and last file/line from a stack trace."""
    file_matches = list(_FILE_LINE_PATTERN.finditer(stack_trace))
    file_hint: str | None = None
    line_number: int | None = None
    if file_matches:
        last_match = file_matches[-1]
        file_hint = last_match.group(1)
        line_number = int(last_match.group(2))

    lines = [line.strip() for line in stack_trace.strip().splitlines() if line.strip()]
    error_line = ""
    for line in lines:
        if _FILE_LINE_PATTERN.search(line):
            continue
        if "request_id=" in line.lower() or "timestamp=" in line.lower():
            continue
        if re.match(r"^[A-Za-z_][\w.]*Error", line) or re.match(r"^[A-Za-z_][\w.]*Exception", line):
            error_line = line
            break

    if not error_line:
        for line in reversed(lines):
            if _FILE_LINE_PATTERN.search(line):
                continue
            if "request_id=" in line.lower() or "timestamp=" in line.lower():
                continue
            error_line = line
            break

    if not error_line and lines:
        error_line = lines[-1]

    error_type = "UnknownError"
    message = error_line or "Unknown failure"
    if ":" in error_line:
        error_type, message = error_line.split(":", 1)
        error_type = error_type.strip()
        message = message.strip()

    return ParsedTrace(
        error_type=error_type,
        message=message,
        file=file_hint,
        line=line_number,
    )


def line_window_bounds(line: int | None, *, padding: int = 5, total_lines: int | None = None) -> tuple[int, int]:
    """Compute inclusive 1-based start/end bounds around a failing line."""
    if line is None:
        return 1, max(padding * 2, 1)
    start = max(1, line - padding)
    end = line + padding
    if total_lines is not None:
        end = min(end, total_lines)
    return start, end
