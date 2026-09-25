"""Compress an agent turn or a round into a manager-safe summary (panel model)."""

from __future__ import annotations

from langchain_core.tools import tool

from manager_agent.panel import llm as panel_llm


@tool
def summarizer(text: str, focus: str = "claims, citations, disagreements") -> str:
    """Compress text into a short summary (under 120 words) focused on the given aspects."""
    if not panel_llm.has_panel_key():
        return f"[placeholder summary | focus={focus}]\n{text[:400]}"
    prompt = (
        f"Summarize for a debate manager. Focus on: {focus}. Under 120 words. "
        f"Keep source names.\n\nTEXT:\n{text[:12000]}"
    )
    return str(panel_llm.get_panel_llm().invoke(prompt).content)
