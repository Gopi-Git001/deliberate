"""Compile the panel debate subgraph and expose the manager-facing runner.

START → panel_intake ─┬─(fan-out ×10, independent)→ research_agent → broadcast_digest ─┐
                      └─(intervention continuation)──────────────────────────────────┴→ debate_round
debate_round ─(fan-out ×10)→ debate_agent (validated: ≥2 peers, persuasion, no restatement)
    → summarize_round → check_stop (8/10 + engagement gate)
check_stop ─┬→ debate_round            (continue)
            └→ settle_consensus → END  (consensus | max_rounds | no_new_arguments)
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from langgraph.graph import END, START, StateGraph

from manager_agent.panel import llm as panel_llm
from manager_agent.panel.config import get_panel_settings
from manager_agent.panel.nodes import (
    broadcast_digest,
    check_stop,
    debate_agent,
    debate_round,
    dispatch_debate,
    panel_intake,
    research_agent,
    route_after_check,
    route_after_intake,
    settle_consensus,
    summarize_round,
)
from manager_agent.panel.state import PanelState
from manager_agent.schemas import PanelBrief, PanelResult


def build_panel_graph():
    graph = StateGraph(PanelState)
    graph.add_node("panel_intake", panel_intake)
    graph.add_node("research_agent", research_agent)
    graph.add_node("broadcast_digest", broadcast_digest)
    graph.add_node("debate_round", debate_round)
    graph.add_node("debate_agent", debate_agent)
    graph.add_node("summarize_round", summarize_round)
    graph.add_node("check_stop", check_stop)
    graph.add_node("settle_consensus", settle_consensus)

    graph.add_edge(START, "panel_intake")
    graph.add_conditional_edges("panel_intake", route_after_intake, ["research_agent", "debate_round"])
    graph.add_edge("research_agent", "broadcast_digest")
    graph.add_edge("broadcast_digest", "debate_round")
    graph.add_conditional_edges("debate_round", dispatch_debate, ["debate_agent"])
    graph.add_edge("debate_agent", "summarize_round")
    graph.add_edge("summarize_round", "check_stop")
    graph.add_conditional_edges(
        "check_stop", route_after_check, ["debate_round", "settle_consensus"]
    )
    graph.add_edge("settle_consensus", END)
    return graph.compile()


panel_app = build_panel_graph()


def _inputs(brief: PanelBrief) -> dict[str, Any]:
    return {
        "topic": brief.topic,
        "sub_question": brief.goal,
        "focus_questions": brief.sub_questions,
        "constraints": brief.constraints,
        "intervention": brief.directive,
        "prior_summaries": brief.prior_summaries,
        "panel_size": brief.panel_size,
        "max_rounds": brief.debate_rules.max_rounds,
        "hop": brief.hop,
    }


def _run_config() -> dict[str, Any]:
    settings = get_panel_settings()
    return {
        "max_concurrency": settings.panel_max_concurrency,
        # ~5 supersteps per round + intake/research/settle.
        "recursion_limit": 6 * settings.panel_max_rounds + 10,
    }


def _result(state: dict[str, Any]) -> PanelResult:
    """Map panel state to the manager contract — summaries + conclusion only."""
    return PanelResult(
        round_summaries=state.get("panel_summaries") or [],
        consensus=state.get("consensus") or "",
        status=state.get("status") or "deadlock",
        rounds_run=state.get("round_index", 0),
        confidence=state.get("confidence"),
        dissent=state.get("dissent") or "",
        stop_reason=state.get("stop_reason") or "",
    )


def run_panel(brief: PanelBrief) -> PanelResult:
    """PanelRunner for the manager. Debate events stream to any enclosing stream."""
    panel_llm.get_panel_llm()  # fail fast on a missing key before any fan-out
    return _result(panel_app.invoke(_inputs(brief), config=_run_config()))


def stream_panel(brief: PanelBrief) -> Iterator[dict[str, Any]]:
    """Run the panel solo, yielding debate events; the last event is `panel_result`."""
    panel_llm.get_panel_llm()
    final: dict[str, Any] = {}
    for mode, chunk in panel_app.stream(
        _inputs(brief), config=_run_config(), stream_mode=["custom", "values"]
    ):
        if mode == "custom":
            yield chunk
        else:
            final = chunk
    yield {"type": "panel_result", "result": _result(final).model_dump()}
