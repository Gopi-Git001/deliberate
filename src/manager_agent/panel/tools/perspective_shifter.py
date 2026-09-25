"""Force an agent to argue the opposite side of the current majority (anti-echo-chamber)."""

from __future__ import annotations

from langchain_core.tools import tool

from manager_agent.panel import llm as panel_llm


def shift_brief(question: str, position_to_oppose: str) -> str:
    if not panel_llm.has_panel_key():
        return (
            "[placeholder shift] Argue AGAINST this position in good faith: "
            f"{position_to_oppose!r} (question: {question!r}). Find the strongest "
            "counter-evidence and state the opposite answer."
        )
    prompt = (
        "You write devil's-advocate briefs for a debate panel.\n"
        f"QUESTION: {question}\nMAJORITY POSITION TO OPPOSE: {position_to_oppose}\n\n"
        "Write, in under 120 words: (1) the opposite thesis as one sentence, "
        "(2) the three strongest arguments for it, (3) what evidence to search for. "
        "Argue in good faith — no strawmen, no fabricated facts."
    )
    return str(panel_llm.get_panel_llm().invoke(prompt).content)


@tool
def perspective_shifter(question: str, position_to_oppose: str) -> str:
    """Produce a brief for arguing the OPPOSITE of a position (the current majority), with the strongest counter-arguments and evidence to seek."""
    return shift_brief(question, position_to_oppose)
