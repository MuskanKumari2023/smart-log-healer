from __future__ import annotations

import json
from typing import Any

from openai import OpenAI
from pydantic import ValidationError

from backend.analyzer import line_window_bounds
from backend.models import BugFixResponse
from backend.observability import TraceContext, span_generation
from backend.settings import require_groq_api_key
from backend.tools import get_scenario_source, get_scenario_tests, read_file_lines

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT_BASE = """You are an automated software patching utility.
Analyze the provided stack trace and source context, then return a fix.

The fix MUST pass all acceptance tests below. Do not change test files or weaken assertions.
Match expected return values and types exactly (e.g. return None where tests expect None).

fixed_code MUST be the COMPLETE buggy.py file: every function from the original must remain
unless you have an exceptional reason. Apply a minimal edit (e.g. add a null check) — do NOT
delete helper functions such as database_fetch_by_id.

Respond with valid JSON only using this schema:
{
  "explanation": "brief root cause",
  "fixed_code": "complete updated buggy.py file without markdown fences",
  "confidence": "low" | "medium" | "high"
}
"""


def _get_client() -> OpenAI:
    return OpenAI(base_url=GROQ_BASE_URL, api_key=require_groq_api_key())


def _read_file_lines_tool(scenario_id: str, start: int, end: int) -> str:
    return read_file_lines(scenario_id, start, end)


def _parse_bug_fix_response(raw_content: str) -> BugFixResponse:
    payload = json.loads(raw_content)
    return BugFixResponse.model_validate(payload)


def _system_prompt(scenario_id: str) -> str:
    tests = get_scenario_tests(scenario_id)
    source = get_scenario_source(scenario_id).strip()
    parts = [SYSTEM_PROMPT_BASE]
    parts.append(
        "ORIGINAL buggy.py (fixed_code must be a full-file edit — keep all `def` functions):\n"
        f"```python\n{source}\n```"
    )
    if tests.strip():
        parts.append(
            "ACCEPTANCE_TESTS (test_buggy.py — must pass after your fix):\n"
            f"```python\n{tests.strip()}\n```"
        )
    return "\n\n".join(parts)


def generate_patch(
    scenario_id: str,
    stack_trace: str,
    line: int | None,
    *,
    trace_ctx: TraceContext | None = None,
    pytest_feedback: str | None = None,
    failed_patch: str | None = None,
) -> BugFixResponse:
    """Generate a structured patch using Groq tool-calling for context retrieval."""
    client = _get_client()
    source = get_scenario_source(scenario_id)
    total_lines = len(source.splitlines())
    start, end = line_window_bounds(line, total_lines=total_lines)
    system_prompt = _system_prompt(scenario_id)

    tools = [
        {
            "type": "function",
            "function": {
                "name": "read_file_lines",
                "description": "Read a numbered window from the buggy source file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "scenario_id": {"type": "string"},
                        "start": {"type": "integer"},
                        "end": {"type": "integer"},
                    },
                    "required": ["scenario_id", "start", "end"],
                },
            },
        }
    ]

    user_prompt = (
        f"CRASH_TRACE:\n{stack_trace}\n\n"
        f"Scenario ID: {scenario_id}\n"
        f"Failing line hint: {line}\n"
        "Use read_file_lines to inspect the relevant code before proposing a fix."
    )
    if pytest_feedback and failed_patch:
        user_prompt += (
            "\n\nPREVIOUS_PATCH_FAILED_PYTEST:\n"
            f"```python\n{failed_patch}\n```\n\n"
            f"PYTEST_OUTPUT:\n{pytest_feedback}\n\n"
            "Revise fixed_code so all acceptance tests pass."
        )

    ctx = trace_ctx or TraceContext()
    last_error: Exception | None = None
    span_name = "generate_patch_retry" if pytest_feedback else "generate_patch"

    for attempt in range(2):
        try:
            with span_generation(
                ctx,
                name=span_name,
                model=DEFAULT_MODEL,
                input_data={"stack_trace": stack_trace, "scenario_id": scenario_id},
            ) as span_meta:
                first = client.chat.completions.create(
                    model=DEFAULT_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    tools=tools,
                    tool_choice={
                        "type": "function",
                        "function": {"name": "read_file_lines"},
                    },
                    temperature=0.1,
                )

                message = first.choices[0].message
                tool_calls = message.tool_calls or []
                if not tool_calls:
                    file_content = _read_file_lines_tool(scenario_id, start, end)
                else:
                    args = json.loads(tool_calls[0].function.arguments)
                    file_content = _read_file_lines_tool(
                        args.get("scenario_id", scenario_id),
                        int(args.get("start", start)),
                        int(args.get("end", end)),
                    )

                messages: list[dict[str, Any]] = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                    {
                        "role": "assistant",
                        "content": message.content,
                        "tool_calls": [
                            {
                                "id": tool_calls[0].id,
                                "type": "function",
                                "function": {
                                    "name": tool_calls[0].function.name,
                                    "arguments": tool_calls[0].function.arguments,
                                },
                            }
                        ]
                        if tool_calls
                        else None,
                    },
                ]
                if tool_calls:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_calls[0].id,
                            "name": "read_file_lines",
                            "content": file_content,
                        }
                    )
                else:
                    messages.append(
                        {
                            "role": "user",
                            "content": f"SOURCE_CONTEXT:\n{file_content}",
                        }
                    )

                final = client.chat.completions.create(
                    model=DEFAULT_MODEL,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.1,
                )
                raw = final.choices[0].message.content or "{}"
                patch = _parse_bug_fix_response(raw)
                usage = final.usage
                span_meta["output"] = patch.model_dump()
                if usage is not None:
                    span_meta["usage"] = {
                        "input": usage.prompt_tokens,
                        "output": usage.completion_tokens,
                        "total": usage.total_tokens,
                    }
                return patch
        except (json.JSONDecodeError, ValidationError, KeyError, IndexError) as exc:
            last_error = exc
            continue

    raise RuntimeError(f"Failed to parse AI patch response: {last_error}")
