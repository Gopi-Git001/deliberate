"""Summarize long text for handoffs (manager should prefer summaries over transcripts)."""

from __future__ import annotations

from langchain_core.tools import tool

from manager_agent.llm import get_llm, has_openai_key


@tool
def summarizer(text: str, focus: str = "key claims, evidence, open disagreements") -> str:
    """Compress text into a short summary for manager/panel handoffs."""
    if not has_openai_key():
        preview = text[:500]
        return f"[placeholder summary | focus={focus}]\n{preview}"
    prompt = (
        f"Summarize for an orchestrator agent. Focus on: {focus}. "
        f"Keep under 200 words.\n\nTEXT:\n{text[:12000]}"
    )
    return str(get_llm().invoke(prompt).content)
