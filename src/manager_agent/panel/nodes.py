"""Debate-cycle nodes: intake → independent research fan-out → research digest broadcast →
rounds (engaged debate → summarize → stop?) → settle."""

from __future__ import annotations

import json
import logging
import re
import math
from collections import Counter
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from langgraph.types import Send

from manager_agent.panel import llm as panel_llm
from manager_agent.panel.clones import agent_id_for, make_panel
from manager_agent.panel.config import get_panel_settings
from manager_agent.panel.schemas import AgentTurn, ConsensusStatement, DebateTurn, RoundDigest
from manager_agent.panel.state import PanelState
from manager_agent.panel.tools.citation import make_citation, normalize_url
from manager_agent.panel.tools.confidence_scorer import score_confidence
from manager_agent.panel.tools.perspective_shifter import shift_brief
from manager_agent.panel.tools.source_ranker import rank_sources
from manager_agent.panel.validators import RESTATED_RESEARCH, TurnCheck, canonical_agent, check_turn, feedback

log = logging.getLogger("manager_agent.panel")


def _emit(event: dict[str, Any]) -> None:
    """Stream a debate event (LangGraph custom stream). No-op outside a stream."""
    try:
        get_stream_writer()(event)
    except Exception:  # noqa: BLE001 — never let streaming break the debate
        pass


def _config(agent_id: str, role: str, round_index: int) -> RunnableConfig:
    return {
        "run_name": f"panel.{role}",
        "tags": [f"agent:{agent_id}", f"role:{role}"],
        "metadata": {"agent.id": agent_id, "agent.role": role, "round.index": round_index},
    }


def _context(state: PanelState, agent_id: str) -> str:
    lines = [
        f"TOPIC: {state['topic']}",
        f"DEBATE QUESTION: {state['sub_question']}",
        f"YOUR RESEARCH FOCUS: {state['agent_focus'].get(agent_id) or state['sub_question']}",
        f"CONSTRAINTS: {state.get('constraints') or 'none'}",
    ]
    if state.get("intervention"):
        lines.insert(
            0,
            "MANAGER INTERVENTION — re-anchor the debate to this; it replaces the previous "
            f"agenda:\n{state['intervention']}\n",
        )
    return "\n".join(lines)


def _record(
    agent_id: str,
    round_index: int,
    turn: AgentTurn | DebateTurn,
    question: str,
    shifted: bool,
    check: TurnCheck | None = None,
    attempts: int = 1,
    usage: list[dict] | None = None,
) -> dict:
    """Normalize a turn: clean citations, score sources, calibrate confidence, track engagement.

    Where the agent ranked a source itself (source_ranker), its score is used for that citation.
    """
    usage = usage or []
    cites = [make_citation(c.title, c.url, c.quote) for c in turn.citations]
    agent_scores = _agent_source_scores(usage)
    ranked = [agent_scores.get(r["url"], r["score"]) if r["url"] else r["score"] for r in rank_sources(cites, question)]
    avg_source = sum(ranked) / len(ranked) if ranked else 0.0
    conf = score_confidence(turn.self_confidence, len(cites), avg_source)
    rec = {
        "agent_id": agent_id,
        "round": round_index,
        "stance": turn.stance.strip(),
        "argument": turn.argument.strip(),
        "citations": cites,
        "new_points": turn.new_points,
        "self_confidence": turn.self_confidence,
        "avg_source_score": round(avg_source, 2),
        "confidence": conf["score"],
        "uncited": not cites,
        "shifted": shifted,
        # Engagement tracking (empty for research turns).
        "addressed_agents": [],
        "engaged_agents": [],
        "agreements": [],
        "disagreements": getattr(turn, "critiques", []),
        "evidence_cited": [c["url"] or c["title"] for c in cites],
        "position_decision": "",
        "position_changed": False,
        "stance_delta": "",
        "persuasion_target": "",
        "persuasion_appeal": "",
        "engagement_failed": False,
        "validation_failures": [],
        "attempts": attempts,
        "tools_used": dict(Counter(u["tool"] for u in usage)),
        "agent_ranked_sources": sum(1 for c in cites if c["url"] in agent_scores),
        "agent_confidence": _agent_confidence(usage),
    }
    if isinstance(turn, DebateTurn) and check is not None:
        rec.update(
            addressed_agents=check.addressed,
            engaged_agents=check.engaged,
            agreements=turn.agreements,
            disagreements=turn.disagreements,
            position_decision=turn.position_decision,
            position_changed=turn.position_decision != "hold",
            stance_delta=turn.stance_delta.strip(),
            persuasion_target=check.persuasion_target or "",
            persuasion_appeal=turn.persuasion_appeal.strip(),
            engagement_failed=not check.ok,
            validation_failures=check.reasons,
            research_similarity=check.research_similarity,
        )
    return rec


def _tool_json(usage: list[dict], tool: str) -> list:
    """Parsed JSON results of one tool's successful calls, in call order."""
    out = []
    for u in usage:
        if u["tool"] == tool and not u["error"]:
            try:
                out.append(json.loads(u["result"]))
            except (ValueError, TypeError):
                pass
    return out


def _agent_source_scores(usage: list[dict]) -> dict[str, float]:
    """url -> score from every source_ranker call the agent made (latest wins)."""
    scores = {}
    for ranked in _tool_json(usage, "source_ranker"):
        for r in ranked if isinstance(ranked, list) else []:
            if isinstance(r, dict) and r.get("url") and "score" in r:
                scores[normalize_url(r["url"])] = float(r["score"])
    return scores


def _agent_confidence(usage: list[dict]) -> float | None:
    """The agent's last confidence_scorer score, if it called the tool."""
    scored = [r["score"] for r in _tool_json(usage, "confidence_scorer") if isinstance(r, dict) and "score" in r]
    return scored[-1] if scored else None


def _note(rec: dict) -> str:
    sources = ", ".join(c["domain"] or c["title"] for c in rec["citations"][:3]) or "no sources"
    tag = " (devil's advocate)" if rec["shifted"] else ""
    return f"R{rec['round']}{tag}: {rec['stance']} [{sources}; conf {rec['confidence']}]"


def _agent_event(rec: dict) -> dict:
    return {
        "type": "agent_turn",
        "agent_id": rec["agent_id"],
        "round": rec["round"],
        "stance": rec["stance"],
        "argument": rec["argument"][:400],
        "citations": [{"title": c["title"], "url": c["url"]} for c in rec["citations"][:5]],
        "confidence": rec["confidence"],
        "shifted": rec["shifted"],
        "uncited": rec["uncited"],
        "addressed_agents": rec["addressed_agents"],
        "agreements": rec["agreements"][:3],
        "disagreements": rec["disagreements"][:3],
        "position_decision": rec["position_decision"],
        "position_changed": rec["position_changed"],
        "stance_delta": rec["stance_delta"][:240],
        "persuasion_target": rec["persuasion_target"],
        "persuasion_appeal": rec["persuasion_appeal"][:240],
        "engagement_failed": rec["engagement_failed"],
        "validation_failures": rec["validation_failures"],
        "attempts": rec["attempts"],
        "tools_used": rec["tools_used"],
    }


def _latest(outputs: list[dict]) -> list[dict]:
    if not outputs:
        return []
    last = max(o["round"] for o in outputs)
    return sorted((o for o in outputs if o["round"] == last), key=lambda o: o["agent_id"])


# --- intake / research -------------------------------------------------------------


def panel_intake(state: PanelState) -> dict:
    settings = get_panel_settings()
    size = state.get("panel_size") or settings.panel_size
    max_rounds = max(1, min(state.get("max_rounds") or settings.panel_max_rounds, settings.panel_max_rounds))
    shift_round = settings.panel_perspective_shift_round
    # Keep the shift inside the debate and leave a round to answer it.
    shift_round = min(shift_round, max_rounds - 1) if max_rounds > 1 and shift_round > 0 else 0

    focus = [q for q in state.get("focus_questions", []) if q.strip()] or [state["sub_question"]]
    agent_focus = {agent_id_for(i): focus[i % len(focus)] for i in range(size)}
    prior = state.get("prior_summaries") or []

    _emit(
        {
            "type": "panel_start",
            "hop": state.get("hop", 1),
            "question": state["sub_question"],
            "agents": list(agent_focus),
            "max_rounds": max_rounds,
            "shift_round": shift_round,
            "intervention": state.get("intervention") or "",
        }
    )
    # Fresh short-term memory for this debate.
    return {
        "panel_size": size,
        "max_rounds": max_rounds,
        "shift_round": shift_round,
        "agent_focus": agent_focus,
        "round_index": 0,
        "notes": {},
        "shift_briefs": {},
        "shifted_rounds": [],
        "seen_urls": [],
        "clusters": [],
        "panel_summaries": [],
        "prior_summary": prior[-1] if prior else "",
        "last_novelty": 1.0,
    }


def route_after_intake(state: PanelState):
    # Continuing after a manager intervention: skip fresh research, debate immediately.
    if state.get("intervention") and state.get("prior_summaries"):
        return "debate_round"
    return [
        Send("research_agent", {**state, "agent_id": aid}) for aid in state["agent_focus"]
    ]


# Tools each turn type must call before answering (only those the agent actually has count).
RESEARCH_REQUIRED_TOOLS = ("web_search", "source_ranker", "citation", "confidence_scorer")
DEBATE_REQUIRED_TOOLS = ("web_search", "source_ranker", "perspective_shifter", "confidence_scorer")

RESEARCH_WORKFLOW = """RESEARCH ROUND — gather and vet evidence for your focus, then give your initial position on
the DEBATE QUESTION with citations. Work in steps:
1. web_search (2-3 targeted queries{documents}).
2. source_ranker on the search output (paste it as-is, with the DEBATE QUESTION as query); summarizer
   if a result or document is long.
3. citation for each source you will rely on; confidence_scorer with your self-rating, citation count
   and the average source_ranker score of those sources.
You MUST call web_search, source_ranker, citation and confidence_scorer before answering."""

DEBATE_WORKFLOW = """TOOLS THIS ROUND — verify before you argue:
1. web_search to check the specific peer claims/sources you will contest or accept, and
   perspective_shifter on the strongest position opposing yours (steelman it before deciding).
2. source_ranker on your new search output (paste it as-is).
3. confidence_scorer with your self-rating, citation count, average source score and the share of
   peers who agree with you; use its score as self_confidence.
You MUST call web_search, source_ranker, perspective_shifter and confidence_scorer before answering."""


def research_agent(payload: dict) -> dict:
    settings = get_panel_settings()
    agent_id = payload["agent_id"]
    agent = make_panel(payload["panel_size"])[int(agent_id.rsplit("_", 1)[1])]
    has_docs = any(t.name == "document_reader" for t in agent.tools)
    task = f"{_context(payload, agent_id)}\n\n" + RESEARCH_WORKFLOW.format(
        documents="; document_reader for relevant local documents" if has_docs else ""
    )
    usage: list[dict] = []
    turn = agent.take_turn(
        task,
        settings.panel_research_tool_steps,
        _config(agent_id, "research", 0),
        required_tools=RESEARCH_REQUIRED_TOOLS,
        usage=usage,
    )
    rec = _record(agent_id, 0, turn, payload["sub_question"], shifted=False, usage=usage)
    _emit(_agent_event(rec))
    return {"agent_outputs": [rec], "notes": {agent_id: [_note(rec)]}}


# --- research digest (broadcast before Round 1) -------------------------------------------


def build_research_digest(outputs: list[dict]) -> str:
    """Every agent's research note in short form: id, core claim, key citations, confidence."""
    notes = sorted((o for o in outputs if o["round"] == 0), key=lambda o: o["agent_id"])
    lines = []
    for o in notes:
        flag = ", UNCITED" if o["uncited"] else ""
        lines.append(
            f"- {o['agent_id']} [conf {o['confidence']}{flag}]: {o['stance']} | "
            f"{o['argument'][:320]} | sources: {_sources(o, 3)}"
        )
    return "\n".join(lines)


def broadcast_digest(state: PanelState) -> dict:
    """Runs once all research notes have landed; research itself never saw peers."""
    outputs = state.get("agent_outputs") or []
    ids = sorted({o["agent_id"] for o in outputs if o["round"] == 0})
    _emit({"type": "research_digest", "agents": ids, "count": len(ids)})
    return {"research_digest": build_research_digest(outputs)}


# --- debate round -----------------------------------------------------------------------


def _majority_stance(state: PanelState) -> tuple[str, list[str]]:
    """Largest cluster from the last summary, else the most common latest stance."""
    if state.get("clusters"):
        top = state["clusters"][0]
        return top["answer"], list(top["agent_ids"])
    latest = _latest(state.get("agent_outputs") or [])
    if not latest:
        return "", []
    stance, _ = Counter(o["stance"] for o in latest).most_common(1)[0]
    return stance, [o["agent_id"] for o in latest if o["stance"] == stance]


def _shift_agents(state: PanelState) -> list[str]:
    panel_ids = list(state["agent_focus"])
    refs = get_panel_settings().panel_shift_agent_ids.split(",")
    return list(dict.fromkeys(a for a in (canonical_agent(r, panel_ids) for r in refs) if a))


def debate_round(state: PanelState) -> dict:
    """Open round r; perspective shift on its scheduled round, on echo, or after an invalid consensus."""
    r = state.get("round_index", 0) + 1
    shifted_rounds = list(state.get("shifted_rounds") or [])
    clusters = state.get("clusters") or []
    echo = bool(clusters) and len(clusters) == 1 and not shifted_rounds
    invalid = bool(state.get("invalid_consensus"))
    scheduled = state.get("shift_round", 0) == r and not shifted_rounds

    shift_briefs: dict[str, str] = {}
    majority, _ = _majority_stance(state)
    chosen = _shift_agents(state)
    if (scheduled or echo or invalid) and majority and chosen:
        brief = shift_brief(state["sub_question"], majority)
        shift_briefs = {aid: brief for aid in chosen}
        shifted_rounds.append(r)
        trigger = "scheduled" if scheduled else "invalid_consensus" if invalid else "echo"
        _emit({"type": "perspective_shift", "round": r, "agents": chosen, "opposing": majority, "trigger": trigger})
    _emit({"type": "round_start", "round": r, "max_rounds": state["max_rounds"]})
    return {
        "round_index": r,
        "shift_briefs": shift_briefs,
        "shifted_rounds": shifted_rounds,
        "invalid_consensus": False,
    }


def dispatch_debate(state: PanelState) -> list[Send]:
    return [Send("debate_agent", {**state, "agent_id": aid}) for aid in state["agent_focus"]]


def _own(outputs: list[dict], agent_id: str, round_index: int) -> dict | None:
    return next((o for o in outputs if o["agent_id"] == agent_id and o["round"] == round_index), None)


def _sources(o: dict, k: int = 2) -> str:
    return "; ".join(f"{c['title']} <{c['url']}>" if c["url"] else c["title"] for c in o["citations"][:k]) or "none"


def _prior_round_arguments(state: PanelState, r: int, agent_id: str) -> str:
    if r <= 1:
        return "(none — this is Round 1: respond to specific claims and sources in the RESEARCH_DIGEST)"
    turns = sorted(
        (o for o in state.get("agent_outputs") or [] if o["round"] == r - 1 and o["agent_id"] != agent_id),
        key=lambda o: o["agent_id"],
    )
    if not turns:
        return "(none in this hop — see the prior round summary)"
    lines = []
    for o in turns:
        flags = [f"conf {o['confidence']}", o["position_decision"] or "research"]
        if o["uncited"]:
            flags.append("UNCITED")
        if o["shifted"]:
            flags.append("devil's advocate")
        block = [f"- {o['agent_id']} [{', '.join(flags)}]: {o['stance']}", f"  argument: {o['argument'][:600]}"]
        if o["agreements"]:
            block.append(f"  accepts: {' | '.join(o['agreements'][:2])}")
        if o["disagreements"]:
            block.append(f"  disputes: {' | '.join(o['disagreements'][:2])}")
        if o["persuasion_target"]:
            block.append(f"  trying to convince {o['persuasion_target']}: {o['persuasion_appeal'][:200]}")
        block.append(f"  sources: {_sources(o)}")
        lines.append("\n".join(block))
    return "\n".join(lines)


DEBATE_CONTRACT = """Your reply MUST:
1. Name at least two OTHER agents in addressed_agents (ids like panel_agent_04) and engage a specific claim or source from each — quote or paraphrase it, and say which agent and which source you are answering — in agreements / disagreements.{round2}
2. Set position_decision to hold, revise, or abandon your prior position, and justify it with evidence in stance_delta.
3. Explicitly try to persuade at least one named agent: set persuasion_target to one of your addressed agents and say in persuasion_appeal what they should accept and why.
4. Keep citations on load-bearing claims.
5. Write a NEW argument. Do NOT paste or lightly paraphrase your research note or your previous turn — restatements are rejected and regenerated.
Put only genuinely new arguments/evidence in new_points. If you now agree with a peer's stance, reuse its wording exactly in stance."""


def _debate_task(payload: dict, agent_id: str, r: int, research: dict | None, prior: dict | None, shift: str | None) -> str:
    size = payload["panel_size"]
    number = int(agent_id.rsplit("_", 1)[1])
    notes = "\n".join(f"- {n}" for n in (payload.get("notes") or {}).get(agent_id, [])) or "(none)"
    digest = payload.get("research_digest") or (
        "(no research notes in this hop — the panel continues after a manager intervention; "
        "see the PRIOR ROUND SUMMARY)"
    )
    parts = [
        _context(payload, agent_id),
        f"\nYou are Panel {number:02d} ({agent_id}), member {number + 1}/{size}, in Round {r} "
        f"(ROUND {r} of at most {payload['max_rounds']}).",
        "You already wrote a private research note. Do NOT paste or lightly paraphrase that note.",
    ]
    if research:
        parts.append(
            "YOUR RESEARCH NOTE (reference only — do not repeat it):\n"
            f"{research['stance']} — {research['argument'][:400]}"
        )
    if prior:
        parts.append(f"YOUR POSITION AT THE END OF ROUND {r - 1} ({prior['position_decision']}): {prior['stance']}")
    background = "; background only" if r > 1 else ""
    parts += [
        f"YOUR SHORT-TERM NOTES (this debate only):\n{notes}",
        f"RESEARCH_DIGEST (every agent's research claim + key sources{background}):\n{digest}",
        f"PRIOR_ROUND_ARGUMENTS (Round {r - 1}):\n{_prior_round_arguments(payload, r, agent_id)}",
        f"PRIOR ROUND SUMMARY:\n{payload.get('prior_summary') or '(none)'}",
    ]
    if shift:
        parts.append(
            "PERSPECTIVE SHIFT — this round you MUST argue the OPPOSITE of the majority, in good faith "
            f"and with evidence:\n{shift}\nYour stance must state the opposite answer. You must still meet "
            "every requirement below while arguing this side."
        )
    round2 = (
        f" Respond to what peers argued in PRIOR_ROUND_ARGUMENTS (Round {r - 1}), not to the original "
        "question alone; use the digest only as background."
        if r > 1 else ""
    )
    parts.append(DEBATE_WORKFLOW)
    parts.append(DEBATE_CONTRACT.format(round2=round2))
    return "\n\n".join(parts)


def debate_agent(payload: dict) -> dict:
    settings = get_panel_settings()
    agent_id = payload["agent_id"]
    r = payload["round_index"]
    agent = make_panel(payload["panel_size"])[int(agent_id.rsplit("_", 1)[1])]
    outputs = payload.get("agent_outputs") or []
    research = _own(outputs, agent_id, 0)
    prior = _own(outputs, agent_id, r - 1) if r > 1 else None
    shift = payload.get("shift_briefs", {}).get(agent_id)
    task = _debate_task(payload, agent_id, r, research, prior, shift)

    attempts, rejection = 0, ""
    usage: list[dict] = []
    while True:
        attempts += 1
        prompt = task if not rejection else (
            f"{task}\n\nYOUR PREVIOUS DRAFT WAS REJECTED:\n{rejection}\nRewrite the whole turn to fix these problems."
        )
        # A rejected draft is a rewrite: short tool budget, no required tools.
        first = attempts == 1
        steps = settings.panel_debate_tool_steps if first else settings.panel_retry_tool_steps
        attempt_usage: list[dict] = []
        turn: DebateTurn = agent.take_turn(
            prompt,
            steps,
            _config(agent_id, "debate", r),
            schema=DebateTurn,
            attempt=attempts,
            required_tools=DEBATE_REQUIRED_TOOLS if first else (),
            usage=attempt_usage,
        )
        usage += attempt_usage
        check = check_turn(
            turn,
            agent_id=agent_id,
            panel_ids=list(payload["agent_focus"]),
            research_note=research["argument"] if research else "",
            prior_turn=prior["argument"] if prior else "",
            threshold=settings.panel_restatement_threshold,
        )
        if check.ok or attempts > settings.panel_turn_retries:
            break  # accepted, or accepted as degraded (engagement_failed=True)
        _emit({"type": "turn_rejected", "agent_id": agent_id, "round": r, "reasons": check.reasons, "attempt": attempts})
        rejection = feedback(check.reasons)

    rec = _record(agent_id, r, turn, payload["sub_question"], bool(shift), check, attempts, usage)
    _emit(_agent_event(rec))
    return {"agent_outputs": [rec], "notes": {agent_id: [_note(rec)]}}


# --- summarize / stop / settle ---------------------------------------------------------


def _clean_clusters(digest: RoundDigest, turns: list[dict]) -> list[dict]:
    """Make clusters a partition of the agents; add confidence; sort largest first."""
    by_id = {t["agent_id"]: t for t in turns}
    seen: set[str] = set()
    clusters: list[dict] = []
    for c in digest.clusters:
        ids = [a for a in dict.fromkeys(c.agent_ids) if a in by_id and a not in seen]
        if ids:
            seen.update(ids)
            clusters.append({"answer": c.answer, "agent_ids": ids})
    for aid, t in by_id.items():
        if aid not in seen:
            clusters.append({"answer": t["stance"], "agent_ids": [aid]})
    n = len(turns)
    for c in clusters:
        share = len(c["agent_ids"]) / n
        scores = [
            score_confidence(
                by_id[a]["self_confidence"], len(by_id[a]["citations"]), by_id[a]["avg_source_score"], share
            )["score"]
            for a in c["agent_ids"]
        ]
        c["share"] = round(share, 2)
        c["confidence"] = round(sum(scores) / len(scores), 2)
    return sorted(clusters, key=lambda c: (len(c["agent_ids"]), c["confidence"]), reverse=True)


def _round_engagement(turns: list[dict]) -> dict:
    failed = {t["agent_id"]: t["validation_failures"] for t in turns if t["engagement_failed"]}
    return {"engaged": len(turns) - len(failed), "total": len(turns), "failed": failed, "ok": len(failed) < 2}


def _dissent_text(clusters: list[dict], n: int) -> str:
    minority = clusters[1:]
    if not minority:
        return "none"
    return "; ".join(
        f"[{len(c['agent_ids'])}/{n}] {c['answer'].rstrip('.')} ({', '.join(c['agent_ids'])})" for c in minority
    )


def engagement_gate(state: PanelState, top: dict) -> dict:
    """Consensus only counts if the agreeing agents actually debated each other."""
    outputs = [o for o in state.get("agent_outputs") or [] if o["round"] >= 1]
    reasons = []
    silent = [
        a for a in top["agent_ids"]
        if not any(o["agent_id"] == a and len(o["engaged_agents"]) >= 2 for o in outputs)
    ]
    if silent:
        reasons.append(f"never engaged 2+ peers: {', '.join(silent)}")
    restated = sorted(
        o["agent_id"] for o in outputs if o["round"] == 1 and RESTATED_RESEARCH in o["validation_failures"]
    )
    if len(restated) >= 2:
        reasons.append(f"Round 1 restated research after retries: {', '.join(restated)}")
    clusters = state.get("clusters") or []
    if len(clusters) > 1 and "Dissent:" not in (state.get("prior_summary") or ""):
        reasons.append("minority view not documented")
    return {"passed": not reasons, "reasons": reasons}


def summarize_round(state: PanelState) -> dict:
    settings = get_panel_settings()
    r = state["round_index"]
    turns = sorted((o for o in state["agent_outputs"] if o["round"] == r), key=lambda o: o["agent_id"])
    advocate = " (devil's advocate)"
    listing = "\n".join(
        f"{t['agent_id']}{advocate if t['shifted'] else ''}: stance: {t['stance']} | "
        f"decision: {t['position_decision']} | addressed: {', '.join(t['addressed_agents']) or 'none'} | "
        f"citations: {len(t['citations'])} | new_points: {'; '.join(t['new_points']) or 'none'}"
        for t in turns
    )
    digest: RoundDigest = (
        panel_llm.get_panel_llm()
        .with_structured_output(RoundDigest, method="function_calling")
        .invoke(
            "Summarize this debate round for the manager and group agents by answer. "
            "Keep the summary under 80 words.\n"
            f"QUESTION: {state['sub_question']}\n"
            f"PRIOR ROUND SUMMARY: {state.get('prior_summary') or '(none)'}\n\n"
            f"ROUND {r} TURNS:\n{listing}",
            config=_config("panel", "summarizer", r),
        )
    )
    clusters = _clean_clusters(digest, turns)
    engagement = _round_engagement(turns)

    # Novelty: share of never-seen URLs, or LLM-judged new arguments per agent.
    seen = set(state.get("seen_urls") or [])
    urls = {c["url"] for t in turns for c in t["citations"] if c["url"]}
    url_novelty = len(urls - seen) / len(urls) if urls else 0.0
    arg_novelty = min(1.0, digest.new_argument_count / max(1, len(turns)))
    novelty = round(max(url_novelty, arg_novelty), 2)

    n = len(turns)
    positions = "; ".join(
        f"[{len(c['agent_ids'])}/{n}, conf {c['confidence']}] {c['answer'].rstrip('.')}" for c in clusters[:3]
    )
    moved = [f"{t['agent_id']} ({t['position_decision']})" for t in turns if t["position_changed"]]
    exchanges = [
        f"{t['agent_id']}: {(t['disagreements'] or t['agreements'])[0][:110]}"
        for t in turns if t["disagreements"] or t["agreements"]
    ][:3]
    failed = "; ".join(f"{a} ({', '.join(rs)})" for a, rs in engagement["failed"].items())
    top_cites = sorted({(c["title"], c["domain"]) for t in turns for c in t["citations"]}, key=lambda x: x[0])[:4]
    shifted = [t["agent_id"] for t in turns if t["shifted"]]
    uncited = [t["agent_id"] for t in turns if t["uncited"]]
    # The model sometimes writes its own "Round 2/3:" prefix; keep only ours.
    digest_text = re.sub(r"^\s*Round\s+\d+(?:\s*/\s*\d+)?\s*[:.-]\s*", "", digest.summary, flags=re.I)[:400]
    gate_word = "ok" if engagement["ok"] else "FAILED"
    summary = (
        f"Round {r}/{state['max_rounds']}: Positions: {positions}."
        f" Engagement: {engagement['engaged']}/{n} turns engaged 2+ peers ({gate_word})"
        + (f"; failed: {failed}" if failed else "")
        + f". Moved: {', '.join(moved) or 'none'}."
        + f" Dissent: {_dissent_text(clusters, n)}."
        + f" {digest_text}"
        + (f" Exchanges: {' | '.join(exchanges)}." if exchanges else "")
        + (f" Key citations: {'; '.join(f'{t} ({d})' if d else t for t, d in top_cites)}." if top_cites else "")
        + (f" Devil's advocates: {', '.join(shifted)}." if shifted else "")
        + (f" Uncited: {', '.join(uncited)}." if uncited else "")
        + f" Novelty {novelty}."
    )[: settings.panel_summary_max_chars]

    _emit({
        "type": "round_summary", "round": r, "summary": summary, "clusters": clusters,
        "novelty": novelty, "engagement": engagement, "moved": moved,
    })
    return {
        "clusters": clusters,
        "panel_summaries": [*state.get("panel_summaries", []), summary],
        "prior_summary": summary,
        "seen_urls": sorted(seen | urls),
        "last_novelty": novelty,
        "engagement": engagement,
    }


def check_stop(state: PanelState) -> dict:
    settings = get_panel_settings()
    r = state["round_index"]
    n = state["panel_size"]
    top = state["clusters"][0] if state.get("clusters") else {"agent_ids": []}
    majority = len(top["agent_ids"]) >= math.ceil(settings.panel_consensus_threshold * n)
    shifted = state.get("shifted_rounds") or []
    # Consensus only counts once the majority has survived a devil's-advocate round.
    challenged = not state.get("shift_round") or (shifted and r > shifted[0])
    round_ok = (state.get("engagement") or {}).get("ok", True)
    gate = engagement_gate(state, top) if majority else {"passed": False, "reasons": ["no majority"]}

    reason, invalid = None, False
    if majority and challenged:
        if gate["passed"]:
            reason = "consensus"
        else:  # agreement without debate = echo; keep going and force a shift
            invalid = True
            _emit({"type": "engagement_gate", "round": r, "passed": False, "reasons": gate["reasons"]})
    if not reason:
        if r >= state["max_rounds"]:
            reason = "max_rounds"
        elif r >= 2 and round_ok and state.get("last_novelty", 1.0) < settings.panel_no_new_args_threshold:
            reason = "no_new_arguments"
    engagement = {**(state.get("engagement") or {}), "gate_passed": gate["passed"], "gate_reasons": gate["reasons"]}
    if reason:
        log.info("panel stop", extra={"round.index": r, "stop_reason": reason})
        _emit({"type": "stop", "round": r, "stop_reason": reason})
    return {"stop_reason": reason, "invalid_consensus": invalid and not reason, "engagement": engagement}


def route_after_check(state: PanelState) -> Literal["debate_round", "settle_consensus"]:
    return "settle_consensus" if state.get("stop_reason") else "debate_round"


def settle_consensus(state: PanelState) -> dict:
    settings = get_panel_settings()
    n = state["panel_size"]
    clusters = state.get("clusters") or []
    if not clusters:  # nothing debated (should not happen) — report honestly
        return {"consensus": "", "confidence": 0.0, "dissent": "", "status": "deadlock"}
    top = clusters[0]
    majority = len(top["agent_ids"]) >= math.ceil(settings.panel_consensus_threshold * n)
    gate = engagement_gate(state, top)
    status = "consensus" if majority and gate["passed"] else "deadlock"
    latest = {o["agent_id"]: o for o in _latest(state["agent_outputs"])}
    support = "\n".join(
        f"- {aid}: {latest[aid]['argument'][:400]} | sources: "
        + "; ".join(c["formatted"] for c in latest[aid]["citations"][:3])
        for aid in top["agent_ids"]
        if aid in latest
    )
    others = "\n".join(f"- [{len(c['agent_ids'])}/{n}] {c['answer']}" for c in clusters[1:]) or "(none)"
    if not majority:
        caveat = f"No {settings.panel_consensus_threshold:.0%} majority was reached: say so explicitly.\n"
    elif not gate["passed"]:
        caveat = "A majority formed WITHOUT real engagement between agents: say the agreement is unverified.\n"
    else:
        caveat = ""
    statement: ConsensusStatement = (
        panel_llm.get_panel_llm()
        .with_structured_output(ConsensusStatement, method="function_calling")
        .invoke(
            f"Write the panel's surviving conclusion for the manager.\nQUESTION: {state['sub_question']}\n"
            f"WINNING POSITION ({len(top['agent_ids'])}/{n} agents): {top['answer']}\n"
            f"SUPPORTING ARGUMENTS:\n{support}\n\nDISSENTING POSITIONS:\n{others}\n"
            + caveat
            + "Cite only sources listed above. Document the dissent; do not overwrite it.",
            config=_config("panel", "settle", state["round_index"]),
        )
    )
    # Minority must be documented, never dropped by a vote.
    dissent = statement.dissent.strip()
    if clusters[1:] and dissent.lower().rstrip(".") in {"", "none", "n/a"}:
        dissent = f"Minority: {_dissent_text(clusters, n)}."
    if majority and not gate["passed"]:
        dissent = f"Engagement gate failed ({'; '.join(gate['reasons'])}). {dissent}".strip()
    share = len(top["agent_ids"]) / n
    confidence = round(top["confidence"] * (0.5 + 0.5 * share), 2)
    _emit(
        {
            "type": "consensus",
            "status": status,
            "consensus": statement.consensus,
            "confidence": confidence,
            "dissent": dissent,
            "stop_reason": state.get("stop_reason"),
            "rounds": state["round_index"],
            "engagement_passed": gate["passed"],
            "engagement_reasons": gate["reasons"],
        }
    )
    return {"consensus": statement.consensus, "confidence": confidence, "dissent": dissent, "status": status}
