from __future__ import annotations

import json

from openai import OpenAI
from pydantic import ValidationError

from backend.models import JudgeResult
from backend.observability import TraceContext, span_generation
from backend.settings import get_groq_api_key, require_groq_api_key
from backend.tools import get_scenario_tests

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "llama-3.3-70b-versatile"

JUDGE_PROMPT = """You are an automated code reviewer.
Review the proposed bug fix for security issues and logic drift.

The patch ALREADY PASSED pytest. Acceptance tests are the contract — approve behavior
that satisfies them even if static type hints (e.g. -> str) look inconsistent with
returning None when tests explicitly expect None.

Return JSON only:
{
  "approved": true | false,
  "security_score": 0-10,
  "logic_preserved": true | false,
  "issues": ["list of concrete issues"],
  "summary": "one sentence review"
}

Reject if you see eval/exec, hardcoded secrets, unsafe deserialization, or unrelated behavior changes.
Do NOT reject only because of return type annotations vs None when acceptance tests require None.
Approve only if security_score >= 7 and logic_preserved is true.
"""


def _get_client() -> OpenAI:
    return OpenAI(base_url=GROQ_BASE_URL, api_key=require_groq_api_key())


def _fallback_judge(fixed_code: str) -> JudgeResult:
    """Deterministic lightweight review when LLM judge is unavailable."""
    issues: list[str] = []
    lowered = fixed_code.lower()
    for pattern in ("eval(", "exec(", "pickle.loads", "os.system("):
        if pattern in lowered:
            issues.append(f"Potential unsafe pattern detected: {pattern}")
    approved = not issues
    return JudgeResult(
        approved=approved,
        security_score=8 if approved else 3,
        logic_preserved=approved,
        issues=issues,
        summary="Fallback static review completed.",
    )


def run_judge(
    scenario_id: str,
    fixed_code: str,
    stack_trace: str,
    *,
    trace_ctx: TraceContext | None = None,
) -> JudgeResult:
    """Run an LLM-as-a-Judge review on a patch that already passed pytest."""
    if not get_groq_api_key():
        return _fallback_judge(fixed_code)

    client = _get_client()
    ctx = trace_ctx or TraceContext()
    tests = get_scenario_tests(scenario_id)
    user_content = (
        f"SCENARIO: {scenario_id}\n"
        f"STACK_TRACE:\n{stack_trace}\n\n"
        f"ACCEPTANCE_TESTS (pytest — already passing):\n{tests or '(none)'}\n\n"
        f"PROPOSED_FIX:\n{fixed_code}"
    )

    try:
        with span_generation(
            ctx,
            name="judge_patch",
            model=DEFAULT_MODEL,
            input_data={"scenario_id": scenario_id},
        ) as span_meta:
            response = client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": JUDGE_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            raw = response.choices[0].message.content or "{}"
            payload = json.loads(raw)
            result = JudgeResult.model_validate(payload)
            if result.security_score < 7 or not result.logic_preserved:
                result.approved = False
            span_meta["output"] = result.model_dump()
            usage = response.usage
            if usage is not None:
                span_meta["usage"] = {
                    "input": usage.prompt_tokens,
                    "output": usage.completion_tokens,
                    "total": usage.total_tokens,
                }
            return result
    except (json.JSONDecodeError, ValidationError, RuntimeError):
        return _fallback_judge(fixed_code)
