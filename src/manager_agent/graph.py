"""Compile the manager LangGraph state machine.

START → intake → plan → agent ⇄ tools → delegate → review ─┬→ synthesize → END
                                           ▲                │
                                           └── intervene ───┘  (capped by MAX_PANEL_HOPS)
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from manager_agent.nodes.manager import (
    agent_node,
    intake_node,
    make_delegate_node,
    plan_node,
    review_node,
    route_after_review,
    should_continue,
    synthesize_node,
    tool_node,
)
from manager_agent.panel import PanelRunner, run_panel
from manager_agent.state import ManagerState


def build_manager_graph(panel_runner: PanelRunner = run_panel):
    """Build the manager graph. Pass run_panel_stub for a no-LLM panel."""
    graph = StateGraph(ManagerState)
    graph.add_node("intake", intake_node)
    graph.add_node("plan", plan_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_node("delegate", make_delegate_node(panel_runner))
    graph.add_node("review", review_node)
    graph.add_node("synthesize", synthesize_node)

    graph.add_edge(START, "intake")
    graph.add_edge("intake", "plan")
    graph.add_edge("plan", "agent")
    graph.add_conditional_edges(
        "agent", should_continue, {"tools": "tools", "delegate": "delegate"}
    )
    graph.add_edge("tools", "agent")
    graph.add_edge("delegate", "review")
    graph.add_conditional_edges(
        "review", route_after_review, {"delegate": "delegate", "synthesize": "synthesize"}
    )
    graph.add_edge("synthesize", END)

    return graph.compile()


# Convenience singleton (e.g. for `langgraph dev`)
manager_app = build_manager_graph()
