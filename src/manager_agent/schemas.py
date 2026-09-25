"""Structured contracts: the manager's plan, the panel handoff, and the final answer."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["low", "medium", "high"]


# --- Planning -----------------------------------------------------------------


class DebateRules(BaseModel):
    max_rounds: int = Field(description="Hard cap on panel debate rounds.")
    consensus_criteria: str = Field(description="What counts as consensus.")
    early_stop: str = Field(description="When the panel may stop before max_rounds.")


class ResearchPlan(BaseModel):
    """The manager's plan for a topic."""

    goal: str = Field(description="One-sentence restatement of what the user needs.")
    sub_questions: list[str] = Field(description="3-6 concrete sub-questions to answer.")
    research_angles: list[str] = Field(
        description="Distinct angles/sources the panel should cover."
    )
    debate_rules: DebateRules
    verification_steps: list[str] = Field(
        description="How the manager will verify the final consensus."
    )


# --- Manager <-> panel handoff (summaries only, never transcripts) ------------


class PanelBrief(BaseModel):
    """What the manager hands to the panel."""

    topic: str
    goal: str
    sub_questions: list[str]
    research_angles: list[str]
    debate_rules: DebateRules
    panel_size: int
    hop: int = Field(description="1-based manager -> panel handoff counter.")
    directive: str = Field(
        default="", description="Manager intervention instructions, if any."
    )
    constraints: str = ""
    prior_summaries: list[str] = Field(
        default_factory=list,
        description="Round summaries from the previous hop (set when intervening).",
    )


PanelStatus = Literal["consensus", "deadlock", "stub"]


class PanelResult(BaseModel):
    """What the panel hands back. Deliberately has no transcript field."""

    round_summaries: list[str]
    consensus: str = ""
    status: PanelStatus
    rounds_run: int
    confidence: float | None = None
    dissent: str = ""
    stop_reason: str = ""


class DriftCheck(BaseModel):
    """Manager's review of a panel consensus against the brief."""

    on_track: bool = Field(description="True if the consensus answers the brief.")
    issue: str = Field(default="", description="What is wrong, if anything.")
    directive: str = Field(
        default="", description="Instruction to the panel for one more bounded round."
    )


# --- Final answer ---------------------------------------------------------------


class Source(BaseModel):
    title: str
    url: str = ""


class AnswerDraft(BaseModel):
    """The LLM-authored part of the final answer."""

    answer: str = Field(description="The user-facing answer, clear and complete.")
    key_points: list[str] = Field(description="3-7 key takeaways.")
    sources: list[Source] = Field(
        default_factory=list,
        description="Sources actually seen in tool results. Never invent URLs.",
    )
    confidence: Confidence
    confidence_notes: str = Field(description="Why this confidence level.")
    open_questions: list[str] = Field(default_factory=list)


class Intervention(BaseModel):
    hop: int
    reason: str
    directive: str


class PanelReport(BaseModel):
    status: PanelStatus | Literal["not_run"]
    hops: int
    rounds: int
    confidence: float | None = None
    stop_reason: str = ""
    dissent: str = ""
    interventions: list[Intervention] = Field(default_factory=list)


class FinalAnswer(AnswerDraft):
    """Structured result returned to the user."""

    topic: str
    plan: ResearchPlan | None = None
    panel: PanelReport
    verification: str
    tool_calls: int
