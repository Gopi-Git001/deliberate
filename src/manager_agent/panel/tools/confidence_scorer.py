"""Calibrate an agent's confidence in its position from evidence, not just self-report."""

from __future__ import annotations

import json

from langchain_core.tools import tool


def score_confidence(
    self_confidence: float,
    citation_count: int,
    avg_source_score: float,
    peer_agreement: float = 0.5,
) -> dict:
    """Blend self-rating with evidence quality and peer agreement → 0-1 score + label."""
    self_confidence = min(max(self_confidence, 0.0), 1.0)
    evidence = min(citation_count, 3) / 3
    score = (
        0.4 * self_confidence
        + 0.25 * evidence
        + 0.2 * min(max(avg_source_score, 0.0), 1.0)
        + 0.15 * min(max(peer_agreement, 0.0), 1.0)
    )
    if citation_count == 0:
        score = min(score, 0.35)  # uncited positions are always low-confidence
    score = round(score, 2)
    label = "low" if score < 0.4 else "medium" if score < 0.7 else "high"
    rationale = (
        f"self={self_confidence:.2f}, citations={citation_count}, "
        f"source_quality={avg_source_score:.2f}, peer_agreement={peer_agreement:.2f}"
        + ("; capped: no citations" if citation_count == 0 else "")
    )
    return {"score": score, "label": label, "rationale": rationale}


@tool
def confidence_scorer(
    self_confidence: float,
    citation_count: int,
    avg_source_score: float = 0.5,
    peer_agreement: float = 0.5,
) -> str:
    """Rate certainty of your position (0-1 + low/medium/high) from your self-rating, number of citations, average source score (from source_ranker), and share of peers who agree."""
    return json.dumps(
        score_confidence(self_confidence, citation_count, avg_source_score, peer_agreement)
    )
