"""Demo brain: a scripted stand-in for GPT so the full graph can run without an API key.

Enabled per run via `configurable={"demo": True}` (see runtime.py). The REAL manager
and panel graphs execute; only the model responses are scripted. The script makes
hop 1 deadlock (so the manager intervenes) and hop 2 converge after a devil's-advocate
round. All content and sources are labelled as demo — nothing here is real evidence.
"""

from __future__ import annotations

import random
import re
import time
import zlib
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from manager_agent.runtime import check_cancelled, run_option

YES = "Yes, but only with safeguards and phased adoption."
NO = "No, the current evidence does not justify it yet."
DEPENDS = "It depends: context decides, not a blanket answer."

AGENT_RE = re.compile(r"Panel Worker (panel_agent_\d\d)")
ROUND_RE = re.compile(r"ROUND (\d+) of at most")
TURN_RE = re.compile(r"^(panel_agent_\d\d)(?: \(devil's advocate\))?: stance: (.*?) \|", re.M)
INTERVENTION = "MANAGER INTERVENTION — re-anchor"


def _find(pattern: str, text: str, default: str = "") -> str:
    m = re.search(pattern, text)
    return m.group(1).strip() if m else default


def _call(name: str, args: dict[str, Any]) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"demo_{name}"}])


def _pause(key: str, low: float, high: float) -> None:
    """Simulated thinking time; cancellable. Scaled by configurable demo_delay."""
    scale = float(run_option("demo_delay", 1.0))
    total = random.Random(zlib.crc32(key.encode())).uniform(low, high) * scale
    end = time.monotonic() + total
    while time.monotonic() < end:
        check_cancelled()
        time.sleep(min(0.1, max(0.0, end - time.monotonic())))


class DemoChatModel(BaseChatModel):
    bound: tuple[str, ...] = ()

    @property
    def _llm_type(self) -> str:
        return "demo"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "DemoChatModel":
        names = tuple(getattr(t, "name", None) or getattr(t, "__name__", str(t)) for t in tools)
        return DemoChatModel(bound=names)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._respond(list(messages)))])

    # --- routing ---------------------------------------------------------------------

    def _respond(self, messages: list[BaseMessage]) -> AIMessage:
        text = "\n".join(str(m.content) for m in messages)
        b = set(self.bound)
        for schema in ("ResearchPlan", "DriftCheck", "AnswerDraft", "AgentTurn", "DebateTurn", "RoundDigest", "ConsensusStatement"):
            if schema in b:
                return getattr(self, f"_{schema}")(text)
        if "planner" in b:  # manager tool loop
            _pause("manager-agent" + str(len(messages)), 0.6, 1.2)
            if not any(isinstance(m, ToolMessage) for m in messages):
                return _call("planner", {"topic": _find(r"TOPIC: (.*)", text, "the topic")})
            return AIMessage(content="[demo] Research notes: plan drafted; delegating the evidence debate to the panel.")
        if "citation" in b:  # panel agent tool loop
            return AIMessage(content="[demo] Notes gathered.")
        if "devil's-advocate" in text:  # perspective_shifter tool
            return AIMessage(content="[demo] Argue the opposite: the majority underweights costs and uncertainty.")
        return AIMessage(content="[demo] Scripted tool output.")  # planner / summarizer / fact_checker

    # --- manager ---------------------------------------------------------------------

    def _ResearchPlan(self, text: str) -> AIMessage:
        _pause("plan", 0.8, 1.4)
        topic = _find(r"TOPIC: (.*)", text, "the topic").rstrip("?.! ")
        return _call("ResearchPlan", {
            "goal": f"Give a well-evidenced answer to: {topic}",
            "sub_questions": [
                f"What does the strongest evidence say about: {topic}?",
                "What are the main risks and failure modes?",
                "Under what conditions would the answer change?",
            ],
            "research_angles": ["empirical studies", "practitioner experience", "risk analysis"],
            "debate_rules": {
                "max_rounds": 3,
                "consensus_criteria": "at least 6 of 10 agents back one answer",
                "early_stop": "no new arguments or sources in a round",
            },
            "verification_steps": ["check the consensus answers the goal", "check citations support claims"],
        })

    def _DriftCheck(self, text: str) -> AIMessage:
        _pause("drift", 0.6, 1.0)
        return _call("DriftCheck", {"on_track": True})

    def _AnswerDraft(self, text: str) -> AIMessage:
        _pause("answer", 1.0, 1.6)
        consensus = _find(r"PANEL CONSENSUS:\n(.*)", text, "No panel consensus.")
        return _call("AnswerDraft", {
            "answer": (
                f"{consensus}\n\nThe panel initially split evenly; after the manager re-anchored the "
                "debate on concrete evidence, a clear majority held its position through a "
                "devil's-advocate round. [demo content — run without demo mode for a real answer]"
            ),
            "key_points": [
                "Adopt in phases, with measurable checkpoints.",
                "Safeguards are the condition, not an afterthought.",
                "A minority view on insufficient evidence remains and is worth monitoring.",
            ],
            "sources": [{"title": "Demo source (not real evidence)", "url": "https://example.org/demo"}],
            "confidence": "medium",
            "confidence_notes": "Demo mode: scripted responses, no real research.",
            "open_questions": ["What would a real evidence base show?"],
        })

    # --- panel -----------------------------------------------------------------------

    def _AgentTurn(self, text: str) -> AIMessage:
        agent_id = _find(r"Panel Worker (panel_agent_\d\d)", text, "panel_agent_00")
        rnd = int(_find(r"ROUND (\d+) of at most", text, "0"))
        n = int(agent_id[-2:])
        shifted = "PERSPECTIVE SHIFT" in text
        continuing = INTERVENTION in text
        _pause(f"{agent_id}-{rnd}-{continuing}", 0.8, 3.0)

        if shifted:
            stance = NO if continuing else DEPENDS
        elif continuing:
            stance = YES
        else:
            stance = YES if n % 2 == 0 else NO
        focus = _find(r"YOUR RESEARCH FOCUS: (.*)", text, "the question")
        if stance == YES:
            argument = (
                f"On '{focus}': the benefits are real but conditional. Phased rollout with clear "
                "checkpoints captures most of the upside while containing downside risk."
            )
        else:
            argument = (
                f"On '{focus}': the available studies are small and inconsistent. Committing now "
                "risks locking in a decision the evidence cannot yet support."
            )
        if shifted:
            argument = "Arguing the opposite side as devil's advocate. " + argument
        if continuing:
            argument += " Re-anchored on the manager's directive: weighing only concrete evidence."
        cite_n = (n % 3) + 1
        return _call("AgentTurn", {
            "stance": stance,
            "argument": argument,
            "citations": [
                {"title": f"Demo source {chr(65 + (n + i) % 6)}", "url": f"https://example.org/demo/{(n + i) % 6}",
                 "quote": "Illustrative quote (demo)."}
                for i in range(cite_n)
            ] if n != 7 else [],  # one agent stays uncited so the UI shows that state
            "critiques": [f"panel_agent_{(n + 1) % 10:02d}: claim needs a stronger source."] if rnd else [],
            "new_points": [f"{agent_id}: re-anchored evidence point, round {rnd}"] if continuing
            else ([f"Point from {agent_id} in round {rnd}"] if rnd <= 1 else []),
            "self_confidence": round(0.55 + (n % 4) * 0.1, 2),
        })

    def _DebateTurn(self, text: str) -> AIMessage:
        """Round 1+: engage two named peers, rebut one, try to persuade the other — never restate."""
        agent_id = _find(r"Panel Worker (panel_agent_\d\d)", text, "panel_agent_00")
        rnd = int(_find(r"ROUND (\d+) of at most", text, "1"))
        n = int(agent_id[-2:])
        shifted = "PERSPECTIVE SHIFT" in text
        continuing = INTERVENTION in text
        _pause(f"{agent_id}-{rnd}-{continuing}-debate", 0.8, 3.0)

        if shifted:
            stance = NO if continuing else DEPENDS
        elif continuing:
            stance = YES
        else:
            stance = YES if n % 2 == 0 else NO
        ally, rival = (f"panel_agent_{(n + rnd + k) % 10:02d}" for k in (1, 2))
        ally_label, rival_label = (f"Panel {a[-2:]}" for a in (ally, rival))
        opening = [
            f"{rival_label}'s headline figure comes from a single pilot, while {ally_label} points to a longer study.",
            f"Since last round, {ally_label} has narrowed the disagreement, but {rival_label} still treats early results as settled.",
            f"{rival_label}'s rebuttal leans on anecdote; {ally_label}'s follow-up source is the stronger evidence.",
        ][(rnd - 1) % 3]
        if shifted:
            opening = f"As devil's advocate against the majority: {opening}"
        decision = "revise" if shifted or (continuing and n % 2 and rnd == 1) else "hold"
        cite_n = (n % 3) + 1
        return _call("DebateTurn", {
            "stance": stance,
            "argument": (
                f"{opening} Weighing both, my position is: {stance}"
                + (" Re-anchored on the manager's directive: concrete evidence only." if continuing else "")
            ),
            "addressed_agents": [ally, rival],
            "agreements": [f"{ally}: their longer-horizon source is the better guide (Demo source {chr(65 + n % 6)})."],
            "disagreements": [f"{rival}: their pilot result does not generalise beyond one site."],
            "position_decision": decision,
            "stance_delta": (
                "revised: arguing the other side as instructed" if shifted
                else "revised after the re-anchored evidence review" if decision == "revise"
                else "held: no peer produced stronger contrary evidence"
            ),
            "persuasion_target": rival,
            "persuasion_appeal": f"{rival_label} should accept that one pilot cannot outweigh the multi-site evidence.",
            "citations": [
                {"title": f"Demo source {chr(65 + (n + i) % 6)}", "url": f"https://example.org/demo/{(n + i) % 6}",
                 "quote": "Illustrative quote (demo)."}
                for i in range(cite_n)
            ] if n != 7 else [],
            "new_points": [f"{agent_id}: re-anchored evidence point, round {rnd}"] if continuing
            else ([f"Point from {agent_id} in round {rnd}"] if rnd <= 1 else []),
            "self_confidence": round(0.55 + (n % 4) * 0.1, 2),
        })

    def _RoundDigest(self, text: str) -> AIMessage:
        _pause("digest" + text[-40:], 0.6, 1.0)
        groups: dict[str, list[str]] = {}
        for aid, stance in TURN_RE.findall(text):
            groups.setdefault(stance, []).append(aid)
        ranked = sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True)
        parts = [f"{len(ids)} agents: {stance}" for stance, ids in ranked]
        rnd = int(_find(r"ROUND (\d+) TURNS", text, "1"))
        return _call("RoundDigest", {
            "summary": "[demo] " + "; ".join(p.rstrip(".") for p in parts) + ".",
            "clusters": [{"answer": s, "agent_ids": ids} for s, ids in ranked],
            "disagreements": ["Whether current evidence is strong enough"] if len(groups) > 1 else [],
            # Hop 1 runs dry after round 1; the re-anchored hop keeps finding new points.
            "new_argument_count": 3 if rnd == 1 else (2 if "re-anchored" in text else 0),
        })

    def _ConsensusStatement(self, text: str) -> AIMessage:
        _pause("settle", 0.8, 1.2)
        win = _find(r"WINNING POSITION \(\d+/\d+ agents\): (.*)", text, YES)
        no_majority = "No majority was reached" in text
        return _call("ConsensusStatement", {
            "consensus": ("No majority. Plurality view: " if no_majority else "") + win + " [demo]",
            "dissent": "" if not no_majority else "Half the panel holds the opposite view.",
        })


def demo_llm() -> DemoChatModel:
    return DemoChatModel()
