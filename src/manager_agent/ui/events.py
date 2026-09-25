"""UI event contract (backend → browser over SSE) and the translator from graph events.

Every event carries `type`, `run_id`, `seq` (SSE id) and `ts`. The frontend mirror of
these models lives in web/src/lib/types.ts — keep them in sync.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel

AgentStatus = Literal["idle", "thinking", "speaking", "done", "error"]
Role = Literal["manager", "panel", "system"]
MessageKind = Literal["plan", "research", "handoff", "review", "turn", "shift", "stop", "note"]

MANAGER_ID = "manager"
STOP_TEXT = {
    "consensus": "consensus reached",
    "max_rounds": "round limit reached",
    "no_new_arguments": "no new arguments",
    "intervention_abort": "aborted by manager",
}


class Citation(BaseModel):
    title: str
    url: str = ""


class RunStarted(BaseModel):
    type: Literal["run_started"] = "run_started"
    topic: str
    constraints: str = ""
    demo: bool = False
    agents: list[str]


class AgentMessage(BaseModel):
    type: Literal["agent_message"] = "agent_message"
    agent_id: str
    agent_label: str
    role: Role
    kind: MessageKind
    content: str
    round_index: int | None = None
    hop: int | None = None
    # Panel turns only
    stance: str | None = None
    citations: list[Citation] = []
    confidence: float | None = None
    shifted: bool = False
    uncited: bool = False
    # Debate rounds only (engagement tracking)
    addressed_agents: list[str] = []
    position_decision: str = ""
    stance_delta: str = ""
    persuasion_target: str = ""
    persuasion_appeal: str = ""
    engagement_failed: bool = False


class ManagerIntervention(BaseModel):
    type: Literal["manager_intervention"] = "manager_intervention"
    content: str  # the directive sent to the panel
    reason: str
    round_index: int | None = None
    hop: int


class RoundStarted(BaseModel):
    type: Literal["round_started"] = "round_started"
    round_index: int  # 0 = research
    hop: int
    label: str


class Cluster(BaseModel):
    answer: str
    agent_ids: list[str]
    share: float
    confidence: float


class RoundSummary(BaseModel):
    type: Literal["round_summary"] = "round_summary"
    round_index: int
    hop: int
    summary: str  # exactly what the manager receives
    clusters: list[Cluster] = []
    novelty: float | None = None


class Consensus(BaseModel):
    type: Literal["consensus"] = "consensus"
    consensus: str
    status: str
    confidence: float | None = None
    stop_reason: str | None = None
    dissent: str = ""
    hop: int


class FinalAnswer(BaseModel):
    type: Literal["final_answer"] = "final_answer"
    content: str
    result: dict[str, Any]  # full structured FinalAnswer


class Status(BaseModel):
    type: Literal["status"] = "status"
    agent_id: str
    status: AgentStatus


class Error(BaseModel):
    type: Literal["error"] = "error"
    message: str


class RunFinished(BaseModel):
    type: Literal["run_finished"] = "run_finished"
    reason: Literal["completed", "cancelled", "error"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def agent_label(agent_id: str) -> str:
    if agent_id == MANAGER_ID:
        return "Manager"
    return f"Panel {agent_id.rsplit('_', 1)[-1]}" if agent_id.startswith("panel_agent_") else agent_id


def panel_ids(size: int) -> list[str]:
    return [f"panel_agent_{i:02d}" for i in range(size)]


class Translator:
    """Turns `stream_manager` events into UI events. Stateful: tracks hop, round, statuses."""

    def __init__(self, panel_size: int = 10) -> None:
        self.agents = panel_ids(panel_size)
        self.hop = 0
        self.round = 0
        self.plan_rules: dict[str, Any] = {}

    # helpers ---------------------------------------------------------------------------

    def _manager(self, kind: MessageKind, content: str) -> AgentMessage:
        return AgentMessage(
            agent_id=MANAGER_ID, agent_label="Manager", role="manager", kind=kind,
            content=content, round_index=self.round if self.hop else None, hop=self.hop or None,
        )

    def _system(self, kind: MessageKind, content: str) -> AgentMessage:
        return AgentMessage(
            agent_id="system", agent_label="System", role="system", kind=kind,
            content=content, round_index=self.round, hop=self.hop or None,
        )

    def _all_panel(self, status: AgentStatus) -> list[Status]:
        return [Status(agent_id=a, status=status) for a in self.agents]

    # translation -----------------------------------------------------------------------

    def translate(self, ev: dict[str, Any]) -> list[BaseModel]:
        kind = ev.get("type")
        handler = getattr(self, f"_on_{kind}", None)
        return handler(ev) if handler else []

    def _on_manager_step(self, ev: dict[str, Any]) -> list[BaseModel]:
        node = ev.get("node")
        out: list[BaseModel] = []
        if node == "intake":
            out.append(Status(agent_id=MANAGER_ID, status="thinking"))
        elif node == "plan" and ev.get("plan"):
            plan = ev["plan"]
            rules = plan.get("debate_rules") or {}
            subs = "\n".join(f"• {q}" for q in plan.get("sub_questions") or [])
            out.append(self._manager("plan", (
                f"Goal: {plan.get('goal', '')}\n\nSub-questions:\n{subs}\n\n"
                f"Debate rules: up to {rules.get('max_rounds', '?')} rounds · "
                f"consensus: {rules.get('consensus_criteria', '')} · early stop: {rules.get('early_stop', '')}"
            )))
        elif node == "agent":
            tools = ev.get("tool_calls") or []
            out.append(self._manager("research", (
                f"Researching with {', '.join(tools)}." if tools
                else "Research complete. Preparing the panel brief."
            )))
        elif node == "delegate":
            out.append(Status(agent_id=MANAGER_ID, status="thinking"))
            out.append(self._manager("review", "Panel handed back its round summaries and conclusion. Reviewing against the brief."))
        elif node == "review":
            if ev.get("decision") == "intervene":
                out.append(ManagerIntervention(
                    content=ev.get("directive") or "", reason=ev.get("verification") or "",
                    round_index=self.round, hop=self.hop,
                ))
            else:
                out.append(self._manager("review", ev.get("verification") or "Consensus accepted."))
        elif node == "synthesize":
            out.append(Status(agent_id=MANAGER_ID, status="speaking"))
        return out

    def _on_panel_start(self, ev: dict[str, Any]) -> list[BaseModel]:
        self.hop = ev.get("hop", self.hop + 1)
        self.round = 0
        self.agents = ev.get("agents") or self.agents
        continuing = bool(ev.get("intervention"))
        text = (
            f"Re-running the panel with my directive (hop {self.hop}). Agents continue from the last summaries."
            if continuing
            else f"Delegating to the {len(self.agents)}-agent panel: {ev.get('question', '')}"
        )
        out: list[BaseModel] = [self._manager("handoff", text), Status(agent_id=MANAGER_ID, status="idle")]
        if not continuing:
            out.append(RoundStarted(round_index=0, hop=self.hop, label="Research"))
        out.extend(self._all_panel("thinking"))
        return out

    def _on_round_start(self, ev: dict[str, Any]) -> list[BaseModel]:
        self.round = ev["round"]
        label = f"Round {self.round}" + (f" · Hop {self.hop}" if self.hop > 1 else "")
        return [RoundStarted(round_index=self.round, hop=self.hop, label=label), *self._all_panel("thinking")]

    def _on_agent_turn(self, ev: dict[str, Any]) -> list[BaseModel]:
        aid = ev["agent_id"]
        return [
            Status(agent_id=aid, status="speaking"),
            AgentMessage(
                agent_id=aid, agent_label=agent_label(aid), role="panel", kind="turn",
                content=ev.get("argument", ""), round_index=ev.get("round"), hop=self.hop,
                stance=ev.get("stance"), citations=[Citation(**c) for c in ev.get("citations") or []],
                confidence=ev.get("confidence"), shifted=bool(ev.get("shifted")), uncited=bool(ev.get("uncited")),
                addressed_agents=ev.get("addressed_agents") or [],
                position_decision=ev.get("position_decision") or "",
                stance_delta=ev.get("stance_delta") or "",
                persuasion_target=ev.get("persuasion_target") or "",
                persuasion_appeal=ev.get("persuasion_appeal") or "",
                engagement_failed=bool(ev.get("engagement_failed")),
            ),
            Status(agent_id=aid, status="done"),
        ]

    def _on_perspective_shift(self, ev: dict[str, Any]) -> list[BaseModel]:
        names = " and ".join(agent_label(a) for a in ev.get("agents") or [])
        why = "echo chamber detected" if ev.get("trigger") == "echo" else "scheduled"
        return [self._system("shift", f"Perspective shift ({why}): {names} will argue against “{ev.get('opposing', '')}”.")]

    def _on_research_digest(self, ev: dict[str, Any]) -> list[BaseModel]:
        return [self._system("note", f"Research digest of all {ev.get('count', 0)} independent notes broadcast to every agent before Round 1.")]

    def _on_turn_rejected(self, ev: dict[str, Any]) -> list[BaseModel]:
        reasons = ", ".join(r.replace("_", " ") for r in ev.get("reasons") or [])
        return [self._system("note", f"{agent_label(ev['agent_id'])}'s Round {ev.get('round')} draft rejected ({reasons}); regenerating.")]

    def _on_engagement_gate(self, ev: dict[str, Any]) -> list[BaseModel]:
        reasons = "; ".join(ev.get("reasons") or [])
        return [self._system("stop", f"Majority reached in round {ev.get('round')} but the engagement gate failed ({reasons}). Not accepted as consensus; debate continues.")]

    def _on_round_summary(self, ev: dict[str, Any]) -> list[BaseModel]:
        clusters = [
            Cluster(answer=c["answer"], agent_ids=c["agent_ids"], share=c.get("share", 0), confidence=c.get("confidence", 0))
            for c in ev.get("clusters") or []
        ]
        return [RoundSummary(round_index=ev["round"], hop=self.hop, summary=ev["summary"], clusters=clusters, novelty=ev.get("novelty"))]

    def _on_stop(self, ev: dict[str, Any]) -> list[BaseModel]:
        reason = STOP_TEXT.get(ev.get("stop_reason", ""), ev.get("stop_reason", ""))
        return [self._system("stop", f"Debate stopped after round {ev.get('round')}: {reason}.")]

    def _on_consensus(self, ev: dict[str, Any]) -> list[BaseModel]:
        return [
            Consensus(
                consensus=ev.get("consensus", ""), status=ev.get("status", ""), confidence=ev.get("confidence"),
                stop_reason=ev.get("stop_reason"), dissent=ev.get("dissent") or "", hop=self.hop,
            ),
            *self._all_panel("done"),
        ]

    def _on_final_answer(self, ev: dict[str, Any]) -> list[BaseModel]:
        result = ev.get("result") or {}
        return [
            FinalAnswer(content=result.get("answer", ""), result=result),
            Status(agent_id=MANAGER_ID, status="done"),
            *self._all_panel("done"),
        ]
