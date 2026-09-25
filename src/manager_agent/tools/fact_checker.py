"""Fact-check claims against available evidence (LLM-assisted)."""

from __future__ import annotations

from langchain_core.tools import tool

from manager_agent.llm import get_llm, has_openai_key


@tool
def fact_checker(claim: str, evidence: str = "") -> str:
    """Assess whether a claim is supported, disputed, or unverifiable given evidence."""
    if not has_openai_key():
        return (
            f"[placeholder fact-check]\nclaim={claim!r}\n"
            f"evidence_chars={len(evidence)}. Set OPENAI_API_KEY for live checks."
        )
    prompt = (
        "You are a careful fact-checker. Judge the claim ONLY against the evidence "
        "given. Reply with: verdict (supported|disputed|unverifiable), confidence "
        "(low|medium|high), and a 2-sentence rationale.\n\n"
        f"CLAIM:\n{claim}\n\nEVIDENCE:\n{evidence[:8000] or '(none provided)'}"
    )
    return str(get_llm().invoke(prompt).content)
