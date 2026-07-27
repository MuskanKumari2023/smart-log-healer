from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from backend.cache import cache_entry_count, clear_cache
from backend.pipeline import run_healing_pipeline
from backend.settings import get_groq_api_key
from backend.tools import get_scenario_source, get_tool_window

ROOT = Path(__file__).resolve().parent
SCENARIOS_PATH = ROOT / "data" / "scenarios.json"


def groq_configured() -> bool:
    return bool(get_groq_api_key())


def load_scenarios() -> list[dict]:
    with SCENARIOS_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def render_unified_diff(original: str, updated: str, filename: str = "buggy.py") -> str:
    import difflib

    diff = difflib.unified_diff(
        original.splitlines(),
        updated.splitlines(),
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        lineterm="",
    )
    return "\n".join(diff) or "No changes detected."


def render_pipeline_stages(result) -> None:
    status_icon = {
        "success": "✅",
        "skipped": "⏭️",
        "failed": "❌",
        "warning": "⚠️",
    }
    for stage in result.stages:
        icon = status_icon.get(stage.status, "•")
        line = f"{icon} **{stage.label}**"
        if stage.detail:
            line += f" — {stage.detail}"
        st.markdown(line)


def main() -> None:
    st.set_page_config(page_title="Smart Log Healer", layout="wide")
    st.title("Smart Log Analyzer & Self-Healing Service")
    st.caption(
        "Automated backend utility: parse crashes, cluster signatures, generate patches, "
        "validate with pytest, and review with an LLM judge."
    )

    scenarios = load_scenarios()
    labels = [scenario["title"] for scenario in scenarios]

    if "input_mode" not in st.session_state:
        st.session_state.input_mode = "Preset scenario"
    if "custom_traces" not in st.session_state:
        st.session_state.custom_traces = {}

    with st.sidebar:
        st.header("Controls")
        selected_index = st.selectbox(
            "Choose a server crash scenario",
            range(len(labels)),
            format_func=lambda idx: labels[idx],
        )
        scenario = scenarios[selected_index]

        st.session_state.input_mode = st.radio(
            "Crash log source",
            ["Preset scenario", "Custom stack trace"],
            horizontal=True,
        )

        scenario_key = str(selected_index)
        if scenario_key not in st.session_state.custom_traces:
            st.session_state.custom_traces[scenario_key] = scenario["stack_trace"]

        if st.session_state.input_mode == "Custom stack trace":
            st.session_state.custom_traces[scenario_key] = st.text_area(
                "Stack trace",
                value=st.session_state.custom_traces[scenario_key],
                height=160,
            )

        active_trace = (
            scenario["stack_trace"]
            if st.session_state.input_mode == "Preset scenario"
            else st.session_state.custom_traces[scenario_key]
        )

        groq_ready = groq_configured()
        st.write("Groq API:", "configured" if groq_ready else "missing")
        st.write("Cached fixes:", cache_entry_count())
        if st.button("Clear fix cache"):
            clear_cache()
            st.rerun()

        run_clicked = st.button("Trigger Self-Healing Pipeline", type="primary")

    source_from_sandbox = get_scenario_source(scenario["id"])

    col_problem, col_solution = st.columns(2)

    with col_problem:
        st.subheader("Captured Server State")
        st.error("Runtime Exception Detected")
        st.code(active_trace, language="bash")
        st.subheader("Source Code Context")
        st.caption("Loaded from sandbox (same file AI patches)")
        st.code(source_from_sandbox, language="python")

    with col_solution:
        st.subheader("Automated Resolution")
        if not run_clicked:
            st.info("Select a scenario and trigger the pipeline to generate a patch.")
        elif not groq_ready and not scenario.get("cache_demo_variant"):
            st.warning(
                "Set GROQ_API_KEY via export or `.streamlit/secrets.toml` "
                "(backend and UI use the same resolver)."
            )
        else:
            with st.spinner("Analyzing traceback, checking cache, and validating patch safety..."):
                try:
                    result = run_healing_pipeline(scenario["id"], active_trace)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Pipeline failed: {exc}")
                    return

            st.subheader("Pipeline stages")
            render_pipeline_stages(result)

            with st.expander("Parsed trace & signature"):
                st.write(
                    f"**{result.parsed_trace.error_type}:** {result.parsed_trace.message}"
                )
                st.write(f"**File:** `{result.parsed_trace.file}` **Line:** {result.parsed_trace.line}")
                st.code(result.signature, language="text")

            if result.cache_hit and result.similarity_score is not None:
                st.markdown(
                    f"**Cache Hit {int(result.similarity_score * 100)}%** — skipped AI patch generation"
                )
            else:
                attempts = result.patch_attempts
                st.markdown(
                    f"**Patch generated via Groq** — {attempts} generation attempt(s)"
                )

            st.info(
                f"**Root Cause Analysis** ({result.patch.confidence} confidence): "
                f"{result.patch.explanation}"
            )
            st.code(
                get_tool_window(scenario["id"], result.parsed_trace.line),
                language="python",
            )
            st.subheader("Proposed Patch")
            st.code(result.patch.fixed_code, language="python")
            st.download_button(
                label="Download buggy.py patch",
                data=result.patch.fixed_code,
                file_name="buggy.py",
                mime="text/plain",
            )
            st.subheader("Unified Diff")
            st.code(
                render_unified_diff(result.original_code, result.patch.fixed_code),
                language="diff",
            )

            if result.test_result.passed:
                st.success("Pytest: PASSED")
            else:
                st.error("Pytest: FAILED")

            st.subheader("Pytest Terminal Output")
            st.code(result.test_result.terminal_output or "(no output)", language="bash")

            if result.judge_skipped:
                st.info("Judge: SKIPPED — cached fix was validated on a prior run.")
            elif result.judge_result is not None:
                if result.judge_result.approved:
                    st.success(
                        f"Judge: APPROVED — {result.judge_result.summary} "
                        f"(security {result.judge_result.security_score}/10)"
                    )
                else:
                    st.warning(
                        f"Judge: REJECTED — {result.judge_result.summary} "
                        f"(security {result.judge_result.security_score}/10)"
                    )
                if result.judge_result.issues:
                    st.write("Issues:", result.judge_result.issues)
            elif not result.test_result.passed:
                st.caption("Judge not run — pytest failed.")

            if result.langfuse_trace_url:
                st.link_button("View LLM Trace", result.langfuse_trace_url)

            st.caption(f"Tokens used this run: {result.tokens_used}")


if __name__ == "__main__":
    main()
