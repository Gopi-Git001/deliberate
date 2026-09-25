"""Produce a structured plan for the manager before delegation."""

from __future__ import annotations

from langchain_core.tools import tool

from manager_agent.llm import get_llm, has_openai_key


@tool
def planner(topic: str, constraints: str = "") -> str:
    """Create a step-by-step plan: research angles, debate rules, success criteria."""
    if not has_openai_key():
        return (
            "[placeholder plan]\n"
            f"1. Clarify topic: {topic}\n"
            "2. Assign panel research angles\n"
            "3. Cap debate rounds; early-stop on consensus\n"
            "4. Summarize each round for manager review\n"
            "5. Verify and deliver final answer\n"
            f"constraints={constraints!r}"
        )
    prompt = (
        "You are the manager agent planner. Produce a concise numbered plan covering: "
        "goal, research angles for a 10-agent panel, debate round cap + early-stop, "
        "what to summarize each round, verification steps, and delivery format.\n\n"
        f"TOPIC: {topic}\nCONSTRAINTS: {constraints or 'none'}"
    )
    return str(get_llm().invoke(prompt).content)
