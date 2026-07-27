from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ParsedTrace(BaseModel):
    error_type: str
    message: str
    file: str | None = None
    line: int | None = None


class BugFixResponse(BaseModel):
    explanation: str
    fixed_code: str
    confidence: Literal["low", "medium", "high"] = "medium"


class TestRunResult(BaseModel):
    __test__ = False
    passed: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    terminal_output: str = ""

    @classmethod
    def from_subprocess(
        cls,
        *,
        exit_code: int,
        stdout: str,
        stderr: str,
        duration_ms: int,
    ) -> TestRunResult:
        terminal = stdout
        if stderr:
            terminal = f"{stdout}\n{stderr}" if stdout else stderr
        return cls(
            passed=exit_code == 0,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=duration_ms,
            terminal_output=terminal,
        )


class JudgeResult(BaseModel):
    approved: bool
    security_score: int = Field(ge=0, le=10)
    logic_preserved: bool
    issues: list[str] = Field(default_factory=list)
    summary: str = ""


class CacheLookupResult(BaseModel):
    fixed_code: str
    similarity_score: float
    matched_signature: str


class PipelineStage(BaseModel):
    label: str
    status: str
    detail: str = ""


class PipelineResult(BaseModel):
    parsed_trace: ParsedTrace
    signature: str
    patch: BugFixResponse
    original_code: str
    test_result: TestRunResult
    judge_result: JudgeResult | None = None
    cache_hit: bool = False
    similarity_score: float | None = None
    langfuse_trace_url: str | None = None
    tokens_used: int = 0
    stages: list[PipelineStage] = Field(default_factory=list)
    patch_attempts: int = 1
    judge_skipped: bool = False
