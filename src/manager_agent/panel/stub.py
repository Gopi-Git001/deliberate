"""No-op panel runner: no agents, no LLM calls. For offline tests and cheap manager runs."""

from __future__ import annotations

from manager_agent.schemas import PanelBrief, PanelResult


def run_panel_stub(brief: PanelBrief) -> PanelResult:
    """Placeholder for the 10-agent panel. Runs one no-op round."""
    agent_ids = [f"panel_agent_{i:02d}" for i in range(brief.panel_size)]
    summary = (
        f"[stub] Hop {brief.hop}, round 1/{brief.debate_rules.max_rounds}: "
        f"{len(agent_ids)} identical panel agents ({agent_ids[0]}..{agent_ids[-1]}) "
        f"received {len(brief.sub_questions)} sub-questions and "
        f"{len(brief.research_angles)} research angles. "
        "Stub panel — no debate ran, no consensus produced."
    )
    if brief.directive:
        summary += f" Manager directive received: {brief.directive}"
    return PanelResult(round_summaries=[summary], consensus="", status="stub", rounds_run=1)
