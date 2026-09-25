"""Structured outputs for panel agents and the round summarizer."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    title: str
    url: str = Field(default="", description="Source URL; empty only for local documents.")
    quote: str = Field(default="", description="Short supporting quote or span.")


class AgentTurn(BaseModel):
    """One agent's position for a round (research round 0 or a debate round)."""

    stance: str = Field(
        description="Your answer to the question in ONE sentence. Reuse a peer's wording "
        "exactly if you agree with it."
    )
    argument: str = Field(description="Your reasoning, under 150 words.")
    citations: list[Citation] = Field(
        default_factory=list, description="Sources behind substantive claims."
    )
    critiques: list[str] = Field(
        default_factory=list,
        description="Challenges to specific peers, e.g. 'panel_agent_03: uncited claim ...'.",
    )
    new_points: list[str] = Field(
        default_factory=list,
        description="Arguments or evidence you add that were NOT in the prior round summary.",
    )
    self_confidence: float = Field(ge=0.0, le=1.0, description="Your certainty, 0-1.")


class DebateTurn(BaseModel):
    """One agent's turn in debate Round 1+: must engage peers, not restate research."""

    stance: str = Field(
        description="Your answer to the question in ONE sentence (your claim). Reuse a peer's "
        "wording exactly if you now agree with it."
    )
    argument: str = Field(
        description="Your NEW argument this round, under 180 words, responding to specific peers' "
        "claims and sources. Never paste or lightly paraphrase your research note."
    )
    addressed_agents: list[str] = Field(
        description="Ids of at least two OTHER agents whose specific claims/sources you engage, "
        "e.g. ['panel_agent_04', 'panel_agent_07']."
    )
    agreements: list[str] = Field(
        default_factory=list,
        description="What you accept from named peers, e.g. 'panel_agent_04: their trial source "
        "supports X, and I accept it because ...'.",
    )
    disagreements: list[str] = Field(
        default_factory=list,
        description="What you contest, e.g. 'panel_agent_07: their claim that X ignores Y (source)'.",
    )
    position_decision: Literal["hold", "revise", "abandon"] = Field(
        description="Whether you HOLD, REVISE, or ABANDON your prior position."
    )
    stance_delta: str = Field(description="One line: why you held/revised/abandoned, with the evidence.")
    persuasion_target: str = Field(description="Id of one addressed agent you are trying to convince.")
    persuasion_appeal: str = Field(description="What that agent should accept and why, with evidence.")
    citations: list[Citation] = Field(
        default_factory=list, description="Sources behind load-bearing claims."
    )
    new_points: list[str] = Field(
        default_factory=list,
        description="Arguments or evidence you add that were NOT in the prior round.",
    )
    self_confidence: float = Field(ge=0.0, le=1.0, description="Your certainty, 0-1.")


class Cluster(BaseModel):
    answer: str = Field(description="The shared stance, one sentence.")
    agent_ids: list[str]


class RoundDigest(BaseModel):
    """Round summarizer output (LLM)."""

    summary: str = Field(description="Manager-facing summary of the round, under 120 words.")
    clusters: list[Cluster] = Field(
        description="Group agents whose stances give the same answer. Every agent in exactly one cluster."
    )
    disagreements: list[str] = Field(default_factory=list)
    new_argument_count: int = Field(
        ge=0,
        description="Materially new claims/evidence this round vs the prior round summary.",
    )


class ConsensusStatement(BaseModel):
    consensus: str = Field(
        description="The surviving conclusion as one clear answer, under 150 words, citing sources inline."
    )
    dissent: str = Field(default="", description="One-sentence note on remaining dissent, if any.")
