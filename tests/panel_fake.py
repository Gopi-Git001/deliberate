"""Deterministic, thread-safe fake GPT for the panel (agents run in parallel)."""

from __future__ import annotations

import re
import threading
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict

AGENT_RE = re.compile(r"Panel Worker (panel_agent_\d\d)")
ROUND_RE = re.compile(r"ROUND (\d+) of at most")
TURN_RE = re.compile(r"^(panel_agent_\d\d)(?: \(devil's advocate\))?: stance: (.*?) \|", re.M)


@dataclass
class DebateScript:
    """How fake agents behave. stance(agent_id, round, shifted, prompt) -> str."""

    stance: Callable[[str, int, bool, str], str]
    urls: Callable[[str, int], list[str]] = lambda aid, r: ["https://arxiv.org/abs/2401.00001"]
    new_argument_count: int = 3
    research_tool_call: bool = False
    raw_marker: str = "RAWARG"  # appears in every agent argument, never in summaries
    # Debate-turn misbehaviour, keyed by agent id:
    restate: dict[str, str] = field(default_factory=dict)  # "once" | "always": copy the research note
    lazy: set[str] = field(default_factory=set)  # address only one peer (fails engagement)
    calls: list[dict[str, Any]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


def _text(messages: list[BaseMessage]) -> str:
    return "\n".join(str(m.content) for m in messages)


class PanelFakeModel(BaseChatModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    script: Any
    bound: tuple[str, ...] = ()

    @property
    def _llm_type(self) -> str:
        return "panel-fake"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "PanelFakeModel":
        names = tuple(getattr(t, "name", None) or getattr(t, "__name__", str(t)) for t in tools)
        return PanelFakeModel(script=self.script, bound=names)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        msg = self._respond(list(messages))
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def _respond(self, messages: list[BaseMessage]) -> AIMessage:
        s: DebateScript = self.script
        text = _text(messages)
        m = AGENT_RE.search(text)
        agent_id = m.group(1) if m else "panel"
        rm = ROUND_RE.search(text)
        rnd = int(rm.group(1)) if rm else 0
        shifted = "PERSPECTIVE SHIFT" in text
        kind = "DebateTurn" if "DebateTurn" in self.bound else "AgentTurn" if "AgentTurn" in self.bound else (
            "RoundDigest" if "RoundDigest" in self.bound else (
                "ConsensusStatement" if "ConsensusStatement" in self.bound else (
                    "tools" if self.bound else "plain")))
        with s.lock:
            s.calls.append({"kind": kind, "agent_id": agent_id, "round": rnd, "text": text})

        if kind == "tools":
            already = any(isinstance(x, ToolMessage) for x in messages)
            if s.research_tool_call and rnd == 0 and not already:
                return _call("citation", {"title": "Paper", "url": "https://arxiv.org/abs/1?utm_source=x"})
            return AIMessage(content=f"notes from {agent_id}")
        if kind == "AgentTurn":
            stance = s.stance(agent_id, rnd, shifted, text)
            return _call("AgentTurn", {
                "stance": stance,
                "argument": f"{s.raw_marker}-{agent_id}-r{rnd}: reasoning for {stance}",
                "citations": [{"title": f"Source {u[-5:]}", "url": u, "quote": "q"} for u in s.urls(agent_id, rnd)],
                "critiques": [],
                "new_points": [f"point {agent_id} r{rnd}"],
                "self_confidence": 0.8,
            })
        if kind == "DebateTurn":
            return _debate_turn(s, agent_id, rnd, shifted, text)
        if kind == "RoundDigest":
            turns = TURN_RE.findall(text)
            groups: dict[str, list[str]] = {}
            for aid, stance in turns:
                groups.setdefault(stance, []).append(aid)
            counts = Counter({k: len(v) for k, v in groups.items()})
            return _call("RoundDigest", {
                "summary": "Agents debated; top: " + (counts.most_common(1)[0][0] if counts else "-"),
                "clusters": [{"answer": k, "agent_ids": v} for k, v in groups.items()],
                "disagreements": [] if len(groups) < 2 else ["split on the answer"],
                "new_argument_count": s.new_argument_count,
            })
        if kind == "ConsensusStatement":
            win = re.search(r"WINNING POSITION \(\d+/\d+ agents\): (.*)", text)
            return _call("ConsensusStatement", {
                "consensus": f"Panel conclusion: {win.group(1) if win else '?'}",
                "dissent": "",
            })
        return AIMessage(content="shift brief: argue the opposite")


def _call(name: str, args: dict) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{name}"}])


DEBATE_TEMPLATES = [
    "{p0} relies on a small sample while {p1} has the stronger trial; on balance {stance}",
    "Answering last round, {p0} conceded the timing point and {p1} still overstates effect sizes, so {stance}",
    "After the rebuttal from {p0} and the new source from {p1}, the remaining gap narrows: {stance}",
]


def _debate_turn(s: DebateScript, agent_id: str, rnd: int, shifted: bool, text: str) -> AIMessage:
    stance = s.stance(agent_id, rnd, shifted, text)
    n = int(agent_id[-2:])
    p0, p1 = (f"panel_agent_{(n + rnd + k) % 10:02d}" for k in (1, 2))
    retry = "YOUR PREVIOUS DRAFT WAS REJECTED" in text
    mode = s.restate.get(agent_id)
    if rnd == 1 and mode and (mode == "always" or not retry):
        argument = f"{s.raw_marker}-{agent_id}-r0: reasoning for {stance}"  # verbatim research note
    else:
        template = DEBATE_TEMPLATES[(rnd - 1) % len(DEBATE_TEMPLATES)]
        argument = f"{s.raw_marker}-{agent_id}-r{rnd}: " + template.format(p0=p0, p1=p1, stance=stance)
    addressed = [p0] if agent_id in s.lazy else [p0, p1]
    return _call("DebateTurn", {
        "stance": stance,
        "argument": argument,
        "addressed_agents": addressed,
        "agreements": [f"{p0}: their source supports part of the case"],
        "disagreements": [f"{p1}: their claim overreaches the evidence"],
        "position_decision": "revise" if shifted else "hold",
        "stance_delta": "held: the larger trial still dominates" if not shifted else "revised: arguing the other side",
        "persuasion_target": p0,
        "persuasion_appeal": f"{p0} should accept that the larger trial outweighs the small-sample study.",
        "citations": [{"title": f"Source {u[-5:]}", "url": u, "quote": "q"} for u in s.urls(agent_id, rnd)],
        "new_points": [f"point {agent_id} r{rnd}"],
        "self_confidence": 0.8,
    })
