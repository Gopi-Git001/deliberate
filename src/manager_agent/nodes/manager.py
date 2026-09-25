"""Manager nodes: intake → plan → research loop → delegate → review → synthesize."""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import ToolNode

from manager_agent import prompts
from manager_agent.config import get_settings
from manager_agent.llm import get_llm
from manager_agent.panel import PanelRunner
from manager_agent.schemas import (
    AnswerDraft,
    DebateRules,
    DriftCheck,
    FinalAnswer,
    Intervention,
    PanelBrief,
    PanelReport,
    ResearchPlan,
)
from manager_agent.runtime import check_cancelled
from manager_agent.state import ManagerState
from manager_agent.tools import MANAGER_TOOLS

EVIDENCE_PER_TOOL_CHARS = 1500
EVIDENCE_TOTAL_CHARS = 12000


def _config(state: ManagerState, role: str) -> RunnableConfig:
    """Tag every manager LLM span for observability."""
    return {
        "run_name": f"manager.{role}",
        "tags": ["agent:manager", f"role:{role}"],
        "metadata": {
            "agent.name": "manager",
            "agent.role": role,
            "round.index": state.get("round_index", 0),
        },
    }


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {x}" for x in items) or "(none)"


def _plan(state: ManagerState) -> ResearchPlan | None:
    return ResearchPlan.model_validate(state["plan"]) if state.get("plan") else None


def _tool_steps(messages: list) -> int:
    return sum(1 for m in messages if isinstance(m, AIMessage) and m.tool_calls)


# --- intake / plan ----------------------------------------------------------------


def intake_node(state: ManagerState) -> dict:
    topic = (state.get("topic") or "").strip()
    messages = state.get("messages") or []
    if not topic:
        for m in reversed(messages):
            if isinstance(m, HumanMessage):
                topic = str(m.content).strip()
                break
    if not topic:
        raise ValueError("A non-empty topic is required.")
    update: dict[str, Any] = {
        "topic": topic,
        "constraints": state.get("constraints") or "",
        "plan": {},
        "panel_summaries": [],
        "consensus": "",
        "panel_status": "not_run",
        "panel_confidence": None,
        "panel_stop_reason": "",
        "panel_dissent": "",
        "panel_hops": 0,
        "directive": "",
        "interventions": [],
        "verification": "",
        "final_answer": "",
        "result": {},
        "phase": "planning",
        "round_index": 0,
        "tool_scratch": state.get("tool_scratch") or {},
    }
    if not messages:
        update["messages"] = [HumanMessage(content=topic)]
    return update


def plan_node(state: ManagerState) -> dict:
    settings = get_settings()
    llm = get_llm().with_structured_output(ResearchPlan, method="function_calling")
    plan: ResearchPlan = llm.invoke(
        [
            SystemMessage(content=prompts.SYSTEM),
            HumanMessage(
                content=prompts.PLAN.format(
                    topic=state["topic"],
                    constraints=state.get("constraints") or "none",
                    max_rounds=settings.max_debate_rounds,
                )
            ),
        ],
        config=_config(state, "planner"),
    )
    # Enforce the hard cap regardless of what the model proposed.
    plan.debate_rules.max_rounds = max(
        1, min(plan.debate_rules.max_rounds, settings.max_debate_rounds)
    )
    kickoff = prompts.RESEARCH_KICKOFF.format(
        goal=plan.goal, sub_questions=_bullets(plan.sub_questions)
    )
    return {
        "plan": plan.model_dump(),
        "messages": [HumanMessage(content=kickoff)],
        "phase": "researching",
    }


# --- research loop --------------------------------------------------------------------


def agent_node(state: ManagerState) -> dict:
    """ReAct-style manager step with tools bound."""
    llm = get_llm().bind_tools(MANAGER_TOOLS)
    response = llm.invoke(
        [SystemMessage(content=prompts.SYSTEM), *state["messages"]],
        config=_config(state, "researcher"),
    )
    return {"messages": [response]}


def should_continue(state: ManagerState) -> Literal["tools", "delegate"]:
    messages = state.get("messages") or []
    last = messages[-1] if messages else None
    wants_tools = isinstance(last, AIMessage) and bool(last.tool_calls)
    if wants_tools and _tool_steps(messages) <= get_settings().manager_max_tool_steps:
        return "tools"
    return "delegate"


_tool_node = ToolNode(MANAGER_TOOLS)


def tool_node(state: ManagerState, config: RunnableConfig) -> dict:
    check_cancelled()
    return _tool_node.invoke(state, config)


# --- panel delegation / supervision -----------------------------------------------


def make_delegate_node(panel_runner: PanelRunner):
    def delegate_node(state: ManagerState) -> dict:
        settings = get_settings()
        plan = _plan(state)
        hop = state.get("panel_hops", 0) + 1
        directive = state.get("directive") or ""
        brief = PanelBrief(
            topic=state["topic"],
            goal=plan.goal if plan else state["topic"],
            sub_questions=plan.sub_questions if plan else [],
            research_angles=plan.research_angles if plan else [],
            debate_rules=plan.debate_rules
            if plan
            else DebateRules(
                max_rounds=settings.max_debate_rounds,
                consensus_criteria="majority agreement on a joint answer",
                early_stop="stop when positions converge",
            ),
            panel_size=settings.panel_size,
            hop=hop,
            directive=directive,
            constraints=state.get("constraints") or "",
            # On intervention the panel continues from its latest summaries.
            prior_summaries=(state.get("panel_summaries") or [])[-3:] if directive else [],
        )
        result = panel_runner(brief)
        # Summaries only — and bounded, so a runner cannot smuggle transcripts up.
        cap = settings.panel_summary_max_chars
        summaries = [s[:cap] for s in result.round_summaries]
        return {
            "panel_summaries": [*state.get("panel_summaries", []), *summaries],
            "consensus": result.consensus[: cap * 2],
            "panel_status": result.status,
            "panel_confidence": result.confidence,
            "panel_stop_reason": result.stop_reason,
            "panel_dissent": result.dissent[:cap],
            "panel_hops": hop,
            "round_index": state.get("round_index", 0) + result.rounds_run,
            "directive": "",
            "phase": "reviewing",
        }

    return delegate_node


def review_node(state: ManagerState) -> dict:
    """Stay quiet unless the panel drifted, deadlocked, or broke process."""
    settings = get_settings()
    status = state.get("panel_status")
    hops = state.get("panel_hops", 0)
    interventions = list(state.get("interventions") or [])
    can_intervene = hops < settings.max_panel_hops

    def accept(note: str) -> dict:
        return {"review_decision": "accept", "verification": note, "phase": "synthesizing"}

    if status == "stub":
        return accept(
            "Panel is a stub (not implemented): no consensus to review. "
            "Answer rests on the manager's solo research."
        )

    if status == "deadlock" or not state.get("consensus"):
        reason = "Panel deadlocked / produced no consensus."
        directive = (
            "Resolve the open disagreements from your round summaries. Each agent "
            "states its single strongest piece of evidence; converge on one joint "
            "answer that notes any residual disagreement explicitly."
        )
    else:
        plan = _plan(state)
        check: DriftCheck = (
            get_llm()
            .with_structured_output(DriftCheck, method="function_calling")
            .invoke(
                prompts.DRIFT_CHECK.format(
                    goal=plan.goal if plan else state["topic"],
                    constraints=state.get("constraints") or "none",
                    summaries="\n\n".join(state.get("panel_summaries") or []),
                    consensus=state["consensus"],
                ),
                config=_config(state, "reviewer"),
            )
        )
        if check.on_track:
            return accept("Consensus reviewed against the brief: on track.")
        reason = f"Drift: {check.issue or 'consensus does not answer the brief'}"
        directive = check.directive or "Refocus on the goal and sub-questions."

    # Loop guard: never repeat an identical handoff.
    if interventions and interventions[-1]["directive"] == directive:
        return accept(f"{reason} Same intervention already tried; stopping.")
    if not can_intervene:
        return accept(f"{reason} Panel hop limit ({settings.max_panel_hops}) reached.")

    interventions.append(Intervention(hop=hops, reason=reason, directive=directive).model_dump())
    return {
        "review_decision": "intervene",
        "verification": reason,
        "directive": directive,
        "interventions": interventions,
        "phase": "intervening",
    }


def route_after_review(state: ManagerState) -> Literal["delegate", "synthesize"]:
    return "delegate" if state.get("review_decision") == "intervene" else "synthesize"


# --- synthesize -----------------------------------------------------------------------


def _research_notes(messages: list) -> str:
    for m in reversed(messages):
        if isinstance(m, AIMessage) and not m.tool_calls and str(m.content).strip():
            return str(m.content)
    return "(no research notes — tool budget exhausted before the manager wrote notes)"


def _tool_evidence(messages: list) -> str:
    chunks, total = [], 0
    for m in messages:
        if not isinstance(m, ToolMessage):
            continue
        chunk = f"[{m.name}] {str(m.content)[:EVIDENCE_PER_TOOL_CHARS]}"
        if total + len(chunk) > EVIDENCE_TOTAL_CHARS:
            break
        chunks.append(chunk)
        total += len(chunk)
    return "\n\n".join(chunks) or "(no tool results)"


def _consensus_block(state: ManagerState) -> str:
    if not state.get("consensus"):
        return "(none)"
    meta = [f"status: {state.get('panel_status')}"]
    if state.get("panel_confidence") is not None:
        meta.append(f"panel confidence: {state['panel_confidence']}")
    if state.get("panel_stop_reason"):
        meta.append(f"stopped on: {state['panel_stop_reason']}")
    block = f"{state['consensus']}\n({'; '.join(meta)})"
    if state.get("panel_dissent"):
        block += f"\nDissent: {state['panel_dissent']}"
    return block


def synthesize_node(state: ManagerState) -> dict:
    plan = _plan(state)
    messages = state.get("messages") or []
    prompt = prompts.SYNTHESIZE.format(
        topic=state["topic"],
        constraints=state.get("constraints") or "none",
        goal=plan.goal if plan else state["topic"],
        sub_questions=_bullets(plan.sub_questions if plan else []),
        notes=_research_notes(messages),
        evidence=_tool_evidence(messages),
        summaries="\n\n".join(state.get("panel_summaries") or []) or "(none)",
        consensus=_consensus_block(state),
        verification=state.get("verification") or "(none)",
    )
    draft: AnswerDraft = (
        get_llm()
        .with_structured_output(AnswerDraft, method="function_calling")
        .invoke(
            [SystemMessage(content=prompts.SYSTEM), HumanMessage(content=prompt)],
            config=_config(state, "synthesizer"),
        )
    )
    final = FinalAnswer(
        **draft.model_dump(),
        topic=state["topic"],
        plan=plan,
        panel=PanelReport(
            status=state.get("panel_status") or "not_run",
            hops=state.get("panel_hops", 0),
            rounds=state.get("round_index", 0),
            confidence=state.get("panel_confidence"),
            stop_reason=state.get("panel_stop_reason") or "",
            dissent=state.get("panel_dissent") or "",
            interventions=[Intervention(**i) for i in state.get("interventions") or []],
        ),
        verification=state.get("verification") or "",
        tool_calls=sum(
            len(m.tool_calls) for m in messages if isinstance(m, AIMessage) and m.tool_calls
        ),
    )
    return {"final_answer": final.answer, "result": final.model_dump(), "phase": "done"}
