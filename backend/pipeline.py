from __future__ import annotations

from backend.ai_client import generate_patch
from backend.analyzer import normalize_trace_signature, parse_stack_trace
from backend.cache import lookup_cached_fix, store_fix
from backend.judge import run_judge
from backend.models import BugFixResponse, PipelineResult, PipelineStage
from backend.observability import trace_pipeline
from backend.patch_sanity import missing_top_level_functions
from backend.tools import get_scenario_source
from backend.validator import validate_patch

MAX_PATCH_ATTEMPTS = 3


def _retry_if_incomplete_file(
    scenario_id: str,
    stack_trace: str,
    line: int | None,
    original_code: str,
    patch: BugFixResponse,
    trace_ctx,
    patch_attempts: int,
) -> tuple[BugFixResponse, int, list[PipelineStage]]:
    """Regenerate once if the model dropped top-level functions from buggy.py."""
    extra: list[PipelineStage] = []
    missing = missing_top_level_functions(original_code, patch.fixed_code)
    if not missing or patch_attempts >= MAX_PATCH_ATTEMPTS:
        if missing:
            extra.append(
                PipelineStage(
                    label="Patch structure check",
                    status="warning",
                    detail=f"Missing functions: {', '.join(missing)}",
                )
            )
        return patch, patch_attempts, extra

    patch = generate_patch(
        scenario_id,
        stack_trace,
        line,
        trace_ctx=trace_ctx,
        pytest_feedback=(
            f"Your fixed_code omitted function(s): {', '.join(missing)}. "
            "Return the COMPLETE buggy.py with ALL original functions preserved."
        ),
        failed_patch=patch.fixed_code,
    )
    patch_attempts += 1
    extra.append(
        PipelineStage(
            label="AI patch generation",
            status="success",
            detail=f"Attempt {patch_attempts} (incomplete file — missing {', '.join(missing)})",
        )
    )
    return patch, patch_attempts, extra


def run_healing_pipeline(scenario_id: str, stack_trace: str) -> PipelineResult:
    """Execute the full parse -> cache -> AI -> pytest -> judge pipeline."""
    stages: list[PipelineStage] = []
    parsed = parse_stack_trace(stack_trace)
    stages.append(
        PipelineStage(
            label="Parse stack trace",
            status="success",
            detail=f"{parsed.error_type} @ {parsed.file or '?'}:{parsed.line or '?'}",
        )
    )

    signature = normalize_trace_signature(stack_trace)
    stages.append(
        PipelineStage(
            label="Normalize signature",
            status="success",
            detail=signature[:120] + ("…" if len(signature) > 120 else ""),
        )
    )

    original_code = get_scenario_source(scenario_id)

    with trace_pipeline() as trace_ctx:
        cache_hit = False
        similarity_score: float | None = None
        cached = lookup_cached_fix(signature)

        if cached is not None:
            patch = BugFixResponse(
                explanation=(
                    f"[Cache Hit {int(cached.similarity_score * 100)}%] "
                    "Reused validated fix for similar signature."
                ),
                fixed_code=cached.fixed_code,
                confidence="high",
            )
            cache_hit = True
            similarity_score = cached.similarity_score
            stages.append(
                PipelineStage(
                    label="Cache lookup",
                    status="success",
                    detail=f"Hit {int(cached.similarity_score * 100)}% — skipped AI",
                )
            )
            stages.append(
                PipelineStage(
                    label="AI patch generation",
                    status="skipped",
                    detail="Reused cached fix",
                )
            )
            patch_attempts = 0
        else:
            stages.append(
                PipelineStage(label="Cache lookup", status="warning", detail="Miss — calling AI")
            )
            patch = generate_patch(
                scenario_id,
                stack_trace,
                parsed.line,
                trace_ctx=trace_ctx,
            )
            patch_attempts = 1
            stages.append(
                PipelineStage(
                    label="AI patch generation",
                    status="success",
                    detail=f"Attempt {patch_attempts}",
                )
            )
            patch, patch_attempts, structure_stages = _retry_if_incomplete_file(
                scenario_id,
                stack_trace,
                parsed.line,
                original_code,
                patch,
                trace_ctx,
                patch_attempts,
            )
            stages.extend(structure_stages)

        test_result = validate_patch(scenario_id, patch.fixed_code)
        if test_result.passed:
            stages.append(
                PipelineStage(
                    label="Pytest validation",
                    status="success",
                    detail=f"Passed in {test_result.duration_ms}ms",
                )
            )
        else:
            stages.append(
                PipelineStage(
                    label="Pytest validation",
                    status="failed",
                    detail=f"Attempt {patch_attempts} failed",
                )
            )

        if (
            not cache_hit
            and not test_result.passed
            and patch_attempts < MAX_PATCH_ATTEMPTS
        ):
            patch = generate_patch(
                scenario_id,
                stack_trace,
                parsed.line,
                trace_ctx=trace_ctx,
                pytest_feedback=test_result.terminal_output,
                failed_patch=patch.fixed_code,
            )
            patch_attempts += 1
            stages.append(
                PipelineStage(
                    label="AI patch generation",
                    status="success",
                    detail=f"Retry attempt {patch_attempts} (pytest feedback)",
                )
            )
            test_result = validate_patch(scenario_id, patch.fixed_code)
            if test_result.passed:
                stages.append(
                    PipelineStage(
                        label="Pytest validation",
                        status="success",
                        detail=f"Passed on attempt {patch_attempts}",
                    )
                )
            else:
                stages.append(
                    PipelineStage(
                        label="Pytest validation",
                        status="failed",
                        detail=f"Attempt {patch_attempts} failed",
                    )
                )

        judge_result = None
        judge_skipped = False
        if test_result.passed:
            if cache_hit:
                judge_skipped = True
                stages.append(
                    PipelineStage(
                        label="LLM judge",
                        status="skipped",
                        detail="Cached fix — previously validated",
                    )
                )
            else:
                judge_result = run_judge(
                    scenario_id,
                    patch.fixed_code,
                    stack_trace,
                    trace_ctx=trace_ctx,
                )
                if judge_result.approved:
                    stages.append(
                        PipelineStage(
                            label="LLM judge",
                            status="success",
                            detail=judge_result.summary,
                        )
                    )
                else:
                    stages.append(
                        PipelineStage(
                            label="LLM judge",
                            status="warning",
                            detail=judge_result.summary or "Rejected",
                        )
                    )
        else:
            stages.append(
                PipelineStage(
                    label="LLM judge",
                    status="skipped",
                    detail="Pytest did not pass",
                )
            )

        if (
            test_result.passed
            and not cache_hit
            and judge_result is not None
            and judge_result.approved
        ):
            store_fix(signature, patch.fixed_code)

        if patch_attempts == 0:
            patch_attempts = 1

        return PipelineResult(
            parsed_trace=parsed,
            signature=signature,
            patch=patch,
            original_code=original_code,
            test_result=test_result,
            judge_result=judge_result,
            cache_hit=cache_hit,
            similarity_score=similarity_score,
            langfuse_trace_url=trace_ctx.trace_url,
            tokens_used=trace_ctx.tokens_used,
            stages=stages,
            patch_attempts=patch_attempts,
            judge_skipped=judge_skipped,
        )
