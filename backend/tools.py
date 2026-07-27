from __future__ import annotations

from pathlib import Path

from backend.analyzer import line_window_bounds

SANDBOX_ROOT = Path(__file__).resolve().parent.parent / "sandbox" / "scenarios"


def read_file_lines(scenario_id: str, start: int, end: int) -> str:
    """Read a numbered window from the scenario's buggy source file."""
    path = SANDBOX_ROOT / scenario_id / "buggy.py"
    if not path.exists():
        return f"Error: scenario file not found at {path}"

    lines = path.read_text().splitlines()
    start_idx = max(0, start - 1)
    end_idx = min(len(lines), end)
    window = lines[start_idx:end_idx]
    return "\n".join(f"{start_idx + idx + 1}: {line}" for idx, line in enumerate(window))


def get_scenario_source(scenario_id: str) -> str:
    """Return the full buggy source for a scenario."""
    path = SANDBOX_ROOT / scenario_id / "buggy.py"
    return path.read_text()


def get_scenario_tests(scenario_id: str) -> str:
    """Return acceptance test source for a scenario (if present)."""
    path = SANDBOX_ROOT / scenario_id / "test_buggy.py"
    if not path.exists():
        return ""
    return path.read_text()


def get_tool_window(scenario_id: str, line: int | None) -> str:
    """Build the default context window around a failing line."""
    source_path = SANDBOX_ROOT / scenario_id / "buggy.py"
    total_lines = len(source_path.read_text().splitlines()) if source_path.exists() else None
    start, end = line_window_bounds(line, total_lines=total_lines)
    return read_file_lines(scenario_id, start, end)
