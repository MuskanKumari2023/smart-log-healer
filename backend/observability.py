from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator
from uuid import uuid4

try:
    from langfuse import Langfuse
except ImportError:  # pragma: no cover
    Langfuse = None  # type: ignore[misc, assignment]


@dataclass
class TraceContext:
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    trace_url: str | None = None
    tokens_used: int = 0
    enabled: bool = False


_langfuse_client: Any | None = None


def is_observability_enabled() -> bool:
    return bool(
        os.getenv("LANGFUSE_PUBLIC_KEY")
        and os.getenv("LANGFUSE_SECRET_KEY")
        and Langfuse is not None
    )


def get_langfuse_client() -> Any | None:
    global _langfuse_client
    if not is_observability_enabled():
        return None
    if _langfuse_client is None:
        _langfuse_client = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
    return _langfuse_client


def build_trace_url(trace_id: str) -> str | None:
    if not is_observability_enabled():
        return None
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com").rstrip("/")
    return f"{host}/trace/{trace_id}"


@contextmanager
def trace_pipeline(name: str = "healing_pipeline") -> Generator[TraceContext, None, None]:
    ctx = TraceContext(enabled=is_observability_enabled())
    client = get_langfuse_client()
    trace = None
    if client is not None:
        trace = client.trace(id=ctx.trace_id, name=name)
        ctx.trace_url = build_trace_url(ctx.trace_id)
    try:
        yield ctx
    finally:
        if client is not None:
            client.flush()


@contextmanager
def span_generation(
    ctx: TraceContext,
    *,
    name: str,
    model: str,
    input_data: dict[str, Any],
) -> Generator[dict[str, Any], None, None]:
    """Create a Langfuse generation span and collect usage metadata."""
    metadata: dict[str, Any] = {"tokens_used": 0}
    client = get_langfuse_client()
    generation = None
    if client is not None and ctx.enabled:
        generation = client.generation(
            trace_id=ctx.trace_id,
            name=name,
            model=model,
            input=input_data,
        )
    try:
        yield metadata
    finally:
        if generation is not None:
            generation.end(
                output=metadata.get("output"),
                usage=metadata.get("usage"),
            )
            usage = metadata.get("usage") or {}
            total_tokens = int(usage.get("total_tokens") or usage.get("total") or 0)
            ctx.tokens_used += total_tokens
