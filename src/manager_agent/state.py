"""LangGraph state for the manager agent."""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ManagerState(TypedDict, total=False):
    """Shared graph state.

    - messages: manager research loop (user topic, GPT turns, tool results)
    - topic / constraints: what the user asked for
    - plan: ResearchPlan as a dict
    - panel_summaries: per-round summaries from the panel (never full transcripts)
    - consensus: the panel's joint answer
    - panel_status: consensus | deadlock | stub (from the last handoff)
    - panel_hops: manager -> panel handoffs so far (capped)
    - directive: pending manager intervention for the next panel hop
    - interventions: log of manager interventions
    - review_decision: accept | intervene (routes after review)
    - verification: manager's review notes
    - final_answer: user-facing answer text
    - result: FinalAnswer as a dict (structured output)
    - phase: coarse workflow stage
    - round_index: total debate rounds run
    - tool_scratch: optional structured tool outputs
    """

    messages: Annotated[list[BaseMessage], add_messages]
    topic: str
    constraints: str
    plan: dict[str, Any]
    panel_summaries: list[str]
    consensus: str
    panel_status: str
    panel_confidence: float | None
    panel_stop_reason: str
    panel_dissent: str
    panel_hops: int
    directive: str
    interventions: list[dict[str, Any]]
    review_decision: Literal["accept", "intervene"]
    verification: str
    final_answer: str
    result: dict[str, Any]
    phase: Literal[
        "intake",
        "planning",
        "researching",
        "delegating",
        "reviewing",
        "intervening",
        "synthesizing",
        "done",
    ]
    round_index: int
    tool_scratch: dict[str, Any]
