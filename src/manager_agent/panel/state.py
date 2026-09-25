"""PanelState — short-term memory for ONE debate. Nothing persists across debates."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

StopReason = Literal["consensus", "max_rounds", "no_new_arguments", "intervention_abort"]


def merge_notes(left: dict[str, list[str]], right: dict[str, list[str]]) -> dict[str, list[str]]:
    """Reducer: append each agent's new notes to its short-term notebook."""
    merged = {k: list(v) for k, v in (left or {}).items()}
    for agent_id, notes in (right or {}).items():
        merged.setdefault(agent_id, []).extend(notes)
    return merged


class PanelState(TypedDict, total=False):
    # From the manager
    topic: str
    sub_question: str                     # shared debate question
    focus_questions: list[str]            # manager's sub-questions, assigned round-robin
    agent_focus: dict[str, str]           # agent_id -> assigned sub-question (research focus)
    constraints: str
    intervention: str                     # manager drift correction (re-anchors next rounds)
    prior_summaries: list[str]            # summaries from the previous hop, if continuing
    panel_size: int
    max_rounds: int
    shift_round: int                      # 0 = no scheduled perspective shift
    hop: int

    # Short-term memory (this debate only; never sent to the manager)
    agent_outputs: Annotated[list[dict[str, Any]], operator.add]
    notes: Annotated[dict[str, list[str]], merge_notes]
    research_digest: str                  # every agent's research note, broadcast before Round 1
    shift_briefs: dict[str, str]          # agent_id -> perspective_shifter output, this round
    engagement: dict[str, Any]            # latest engagement-gate result {passed, reasons, ...}
    invalid_consensus: bool               # majority formed without engagement → force a shift
    shifted_rounds: list[int]
    seen_urls: list[str]
    clusters: list[dict[str, Any]]

    # Round bookkeeping
    round_index: int
    last_novelty: float                   # 0-1; drives the no-new-arguments stop

    # Manager-facing
    panel_summaries: list[str]
    prior_summary: str
    consensus: str
    confidence: float
    dissent: str
    status: Literal["consensus", "deadlock"]
    stop_reason: StopReason
