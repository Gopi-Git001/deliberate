"""Debate-turn validators: no restated research, real engagement with ≥2 peers, a persuasion attempt."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from manager_agent.panel.schemas import DebateTurn

_WORD = re.compile(r"[a-z0-9]+")
_AGENT_REF = re.compile(r"(?:panel[_\s-]*agent[_\s-]*|panel\s*)?0*(\d{1,2})$", re.I)

RESTATED_RESEARCH = "restated_research"
RESTATED_PRIOR = "restated_prior_turn"
TOO_FEW_PEERS = "fewer_than_2_peers_addressed"
PEERS_NOT_ENGAGED = "addressed_peers_not_engaged"
NO_PERSUASION = "no_persuasion_attempt"

REASON_TEXT = {
    RESTATED_RESEARCH: "your argument restates your research note — write a NEW argument that responds to peers",
    RESTATED_PRIOR: "your argument repeats your previous round — respond to what peers argued since",
    TOO_FEW_PEERS: "addressed_agents must name at least two OTHER agents by id (e.g. panel_agent_04)",
    PEERS_NOT_ENGAGED: "engage a specific claim or source from each addressed agent in agreements/disagreements, naming them",
    NO_PERSUASION: "set persuasion_target to one of your addressed agents and explain in persuasion_appeal what they should accept and why",
}


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def similarity(a: str, b: str) -> float:
    """0–1 overlap: max of 3-word-shingle containment and word-set Jaccard.

    High for verbatim or lightly reworded text; low for a genuinely new argument.
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    sa, sb = set(ta), set(tb)
    jaccard = len(sa & sb) / len(sa | sb)
    if len(ta) < 3 or len(tb) < 3:
        return jaccard
    sh_a = {tuple(ta[i : i + 3]) for i in range(len(ta) - 2)}
    sh_b = {tuple(tb[i : i + 3]) for i in range(len(tb) - 2)}
    containment = len(sh_a & sh_b) / min(len(sh_a), len(sh_b))
    return round(max(containment, jaccard), 3)


def canonical_agent(ref: str, panel_ids: list[str]) -> str | None:
    """Map 'panel_agent_04' / 'Panel 04' / '4' → 'panel_agent_04' if it exists."""
    ref = (ref or "").strip()
    if ref in panel_ids:
        return ref
    m = _AGENT_REF.search(ref)
    if not m:
        return None
    candidate = f"panel_agent_{int(m.group(1)):02d}"
    return candidate if candidate in panel_ids else None


def _mentions(text: str, agent_id: str) -> bool:
    num = agent_id.rsplit("_", 1)[-1]
    return bool(re.search(rf"\b(?:{re.escape(agent_id)}|panel\s*{num}|panel\s*agent\s*{num})\b", text, re.I))


@dataclass
class TurnCheck:
    reasons: list[str] = field(default_factory=list)
    addressed: list[str] = field(default_factory=list)  # valid, de-duplicated, not self
    engaged: list[str] = field(default_factory=list)  # addressed AND actually engaged in the text
    persuasion_target: str | None = None
    research_similarity: float = 0.0
    prior_similarity: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.reasons


def check_turn(
    turn: DebateTurn,
    *,
    agent_id: str,
    panel_ids: list[str],
    research_note: str = "",
    prior_turn: str = "",
    threshold: float = 0.6,
) -> TurnCheck:
    result = TurnCheck()

    # 1. Similarity vs the agent's own research note and previous debate turn.
    if research_note:
        result.research_similarity = similarity(turn.argument, research_note)
        if result.research_similarity >= threshold:
            result.reasons.append(RESTATED_RESEARCH)
    if prior_turn:
        result.prior_similarity = similarity(turn.argument, prior_turn)
        if result.prior_similarity >= threshold:
            result.reasons.append(RESTATED_PRIOR)

    # 2. Engagement: ≥2 real peers (not self), each engaged by name in the turn's text.
    others = [a for a in panel_ids if a != agent_id]
    addressed = []
    for ref in turn.addressed_agents:
        aid = canonical_agent(ref, others)
        if aid and aid not in addressed:
            addressed.append(aid)
    result.addressed = addressed
    engagement_text = " ".join([*turn.agreements, *turn.disagreements, turn.argument, turn.persuasion_appeal])
    result.engaged = [a for a in addressed if _mentions(engagement_text, a)]
    if len(addressed) < 2:
        result.reasons.append(TOO_FEW_PEERS)
    elif len(result.engaged) < 2:
        result.reasons.append(PEERS_NOT_ENGAGED)

    # 3. Persuasion: a named, addressed peer and a substantive appeal.
    target = canonical_agent(turn.persuasion_target, others)
    result.persuasion_target = target
    if not target or target not in addressed or len(turn.persuasion_appeal.strip()) < 20:
        result.reasons.append(NO_PERSUASION)
    return result


def feedback(reasons: list[str]) -> str:
    return "\n".join(f"- {REASON_TEXT.get(r, r)}" for r in reasons)
