"""Sandboxed code execution placeholder (E2B or local restricted runner)."""

from __future__ import annotations

from langchain_core.tools import tool

from manager_agent.config import get_settings


@tool
def code_interpreter(code: str, language: str = "python") -> str:
    """Run short code snippets in a sandbox and return stdout/stderr."""
    settings = get_settings()
    if not settings.e2b_api_key:
        return (
            "[placeholder] Set E2B_API_KEY or wire a local sandbox. "
            f"Would run {language} ({len(code)} chars)."
        )
    return "[placeholder] Code interpreter backend not wired yet."
