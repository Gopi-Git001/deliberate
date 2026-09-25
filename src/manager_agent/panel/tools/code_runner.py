"""Run short Python snippets in an E2B cloud sandbox. Never executes locally."""

from __future__ import annotations

from langchain_core.tools import tool

from manager_agent.config import get_settings

MAX_OUTPUT_CHARS = 3000


@tool
def code_runner(code: str, timeout_s: int = 30) -> str:
    """Run a short Python snippet in a sandbox (E2B) for checks or light analysis; returns stdout/stderr/results."""
    api_key = get_settings().e2b_api_key
    if not api_key:
        return (
            "[placeholder] code_runner needs E2B_API_KEY (and `pip install "
            f"e2b-code-interpreter`). Would run {len(code)} chars of Python."
        )
    try:
        from e2b_code_interpreter import Sandbox
    except ImportError:
        return "[placeholder] Install e2b-code-interpreter to enable code_runner."
    try:
        timeout_s = max(1, min(timeout_s, 60))
        with Sandbox.create(api_key=api_key, timeout=timeout_s + 30) as sandbox:
            execution = sandbox.run_code(code, timeout=timeout_s)
        parts = []
        if execution.logs.stdout:
            parts.append("stdout:\n" + "".join(execution.logs.stdout))
        if execution.logs.stderr:
            parts.append("stderr:\n" + "".join(execution.logs.stderr))
        if execution.results:
            parts.append("results:\n" + "\n".join(str(r.text) for r in execution.results if r.text))
        if execution.error:
            parts.append(f"error: {execution.error.name}: {execution.error.value}")
        return ("\n".join(parts) or "(no output)")[:MAX_OUTPUT_CHARS]
    except Exception as exc:  # noqa: BLE001 — surface tool errors to the agent
        return f"code_runner error: {exc}"
