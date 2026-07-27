from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from backend.models import TestRunResult

SANDBOX_ROOT = Path(__file__).resolve().parent.parent / "sandbox" / "scenarios"


def validate_patch(scenario_id: str, fixed_code: str) -> TestRunResult:
    """Write the AI patch into an isolated temp copy and run real pytest."""
    src = SANDBOX_ROOT / scenario_id
    if not src.exists():
        raise FileNotFoundError(f"Scenario not found: {scenario_id}")

    start = time.monotonic()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        shutil.copytree(src, work, dirs_exist_ok=True)
        target = work / "buggy.py"
        target.write_text(fixed_code)

        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(work), "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(work),
        )

    duration_ms = int((time.monotonic() - start) * 1000)
    return TestRunResult.from_subprocess(
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        duration_ms=duration_ms,
    )
