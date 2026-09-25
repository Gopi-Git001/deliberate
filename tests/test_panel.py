"""Offline tests for the 10-agent panel and its manager integration."""

from __future__ import annotations

import pytest
from conftest import ANSWER_ARGS, PLAN_ARGS, tool_call
from langchain_core.messages import AIMessage
from panel_fake import DebateScript, PanelFakeModel

from manager_agent.config import get_settings
from manager_agent.graph import build_manager_graph
from manager_agent.llm import MissingAPIKeyError
from manager_agent.main import stream_manager
from manager_agent.panel import run_panel, stream_panel
from manager_agent.panel.clones import make_panel
from manager_agent.panel.config import get_panel_settings
from manager_agent.panel.tools import PANEL_TOOLS
from manager_agent.schemas import DebateRules, FinalAnswer, PanelBrief


@pytest.fixture(autouse=True)
def clear_panel_settings():
    get_panel_settings.cache_clear()
    yield
    get_panel_settings.cache_clear()


@pytest.fixture
def panel_fake(monkeypatch):
    import manager_agent.panel.llm as panel_llm

    def install(script: DebateScript) -> DebateScript:
        monkeypatch.setattr(panel_llm, "get_panel_llm", lambda: PanelFakeModel(script=script))
        return script

    return install


def brief(**kw) -> PanelBrief:
    base = dict(
        topic="Topic T",
        goal="Is X true?",
        sub_questions=["What is X?", "Evidence for X?", "Evidence against X?"],
        research_angles=["a"],
        debate_rules=DebateRules(max_rounds=5, consensus_criteria="majority", early_stop="no new args"),
        panel_size=10,
        hop=1,
    )
    return PanelBrief(**{**base, **kw})


def yes_unless_shifted(aid, rnd, shifted, prompt):
    return "No, X is false." if shifted else "Yes, X is true."


def split(aid, rnd, shifted, prompt):
    return "Yes, X is true." if int(aid[-2:]) % 2 == 0 else "No, X is false."


# --- clones / tools ----------------------------------------------------------------


def test_ten_identical_clones():
    agents = make_panel(10)
    assert [a.agent_id for a in agents] == [f"panel_agent_{i:02d}" for i in range(10)]
    assert all(a.tools is agents[0].tools for a in agents)
    templates = {a.system_prompt.replace(a.agent_id, "ID").replace(f"({a.number}/", "(N/") for a in agents}
    assert len(templates) == 1


def test_panel_tools_registered_without_memory():
    names = {t.name for t in PANEL_TOOLS}
    assert names == {
        "web_search", "citation", "document_reader", "code_runner",
        "source_ranker", "summarizer", "confidence_scorer", "perspective_shifter",
    }
    assert not any("memory" in n for n in names)


def test_run_panel_fails_fast_without_key():
    with pytest.raises(MissingAPIKeyError):
        run_panel(brief())


# --- stop rules -------------------------------------------------------------------------


def test_consensus_after_perspective_shift(panel_fake):
    script = panel_fake(DebateScript(stance=yes_unless_shifted))
    events = list(stream_panel(brief()))
    result = events[-1]["result"]

    # Round 1 unanimous but unchallenged; round 2 = devil's advocates; round 3 settles.
    assert result["stop_reason"] == "consensus" and result["status"] == "consensus"
    assert result["rounds_run"] == 3 and len(result["round_summaries"]) == 3
    assert result["consensus"] == "Panel conclusion: Yes, X is true."
    assert 0 < result["confidence"] <= 1

    shifts = [e for e in events if e["type"] == "perspective_shift"]
    assert len(shifts) == 1 and shifts[0]["round"] == 2 and shifts[0]["agents"] == ["panel_agent_03", "panel_agent_05"]
    assert "Devil's advocates" in result["round_summaries"][1]

    # Each clone researched once and spoke every round.
    turns = [c for c in script.calls if c["kind"] in ("AgentTurn", "DebateTurn")]
    assert len(turns) == 10 * 4
    assert {c["agent_id"] for c in turns} == {f"panel_agent_{i:02d}" for i in range(10)}


def test_no_new_arguments_stop(panel_fake):
    panel_fake(DebateScript(stance=split, new_argument_count=0))
    result = run_panel(brief())
    assert result.stop_reason == "no_new_arguments"
    assert result.rounds_run == 2
    assert result.status == "deadlock"  # 5/5 is not a majority


def test_max_rounds_stop(monkeypatch, panel_fake):
    monkeypatch.setenv("PANEL_MAX_ROUNDS", "3")
    panel_fake(DebateScript(stance=split, urls=lambda aid, r: [f"https://arxiv.org/abs/{aid}-{r}"]))
    result = run_panel(brief())
    assert result.stop_reason == "max_rounds" and result.rounds_run == 3
    assert result.status == "deadlock"
    assert result.consensus  # the surviving (plurality) conclusion is still returned


def test_manager_round_cap_wins(panel_fake):
    panel_fake(DebateScript(stance=split, urls=lambda aid, r: [f"https://x.org/{aid}-{r}"]))
    result = run_panel(brief(debate_rules=DebateRules(max_rounds=2, consensus_criteria="m", early_stop="e")))
    assert result.rounds_run == 2 and result.stop_reason == "max_rounds"


# --- summaries & memory -------------------------------------------------------------


def test_summaries_are_short_and_carry_no_transcript(panel_fake):
    script = panel_fake(DebateScript(stance=yes_unless_shifted))
    result = run_panel(brief())
    cap = get_panel_settings().panel_summary_max_chars
    raw = sum(len(c["text"]) for c in script.calls if c["kind"] in ("AgentTurn", "DebateTurn"))
    assert all(len(s) <= cap for s in result.round_summaries)
    assert sum(len(s) for s in result.round_summaries) < raw / 10
    assert not any(script.raw_marker in s for s in result.round_summaries)


def test_research_tool_loop_executes_tools(panel_fake):
    script = panel_fake(DebateScript(stance=yes_unless_shifted, research_tool_call=True))
    run_panel(brief())
    structured = [c for c in script.calls if c["kind"] == "AgentTurn" and c["round"] == 0]
    # The normalized citation tool output was fed back before the final position.
    assert all("cite-" in c["text"] and "utm_source" not in c["text"].split("cite-")[1] for c in structured)


def test_agents_see_their_own_notes_only(panel_fake):
    script = panel_fake(DebateScript(stance=yes_unless_shifted))
    run_panel(brief())
    r1 = next(c for c in script.calls if c["kind"] == "DebateTurn" and c["round"] == 1 and c["agent_id"] == "panel_agent_03")
    notes = r1["text"].split("YOUR SHORT-TERM NOTES (this debate only):")[1].split("RESEARCH_DIGEST")[0]
    lines = [ln for ln in notes.strip().splitlines() if ln.strip()]
    assert len(lines) == 1 and lines[0].startswith("- R0: Yes, X is true.")


# --- intervention --------------------------------------------------------------------


def test_intervention_reanchors_without_new_research(panel_fake):
    script = panel_fake(DebateScript(stance=yes_unless_shifted))
    result = run_panel(
        brief(hop=2, directive="Re-anchor on cost evidence only.", prior_summaries=["Round 3/3: split."])
    )
    turns = [c for c in script.calls if c["kind"] in ("AgentTurn", "DebateTurn")]
    assert not any(c["round"] == 0 for c in turns)  # skipped research
    assert all("MANAGER INTERVENTION — re-anchor" in c["text"] and "cost evidence only" in c["text"] for c in turns)
    assert all("Round 3/3: split." in c["text"] for c in turns if c["round"] == 1)
    assert result.status == "consensus"


# --- manager integration -------------------------------------------------------------


def _manager_fake(monkeypatch, *script: AIMessage):
    from conftest import ScriptedChatModel
    import manager_agent.nodes.manager as nodes

    model = ScriptedChatModel(script=list(script), calls=[])
    monkeypatch.setattr(nodes, "get_llm", lambda: model)
    return model


def test_manager_to_panel_end_to_end(monkeypatch, panel_fake):
    panel_script = panel_fake(DebateScript(stance=yes_unless_shifted))
    manager = _manager_fake(
        monkeypatch,
        tool_call("ResearchPlan", PLAN_ARGS),
        AIMessage(content="Manager notes."),
        tool_call("DriftCheck", {"on_track": True}),
        tool_call("AnswerDraft", ANSWER_ARGS),
    )
    state = build_manager_graph().invoke({"topic": "Is X true?"}, config={"recursion_limit": 60})
    result = FinalAnswer.model_validate(state["result"])

    assert result.panel.status == "consensus" and result.panel.stop_reason == "consensus"
    assert result.panel.hops == 1 and result.panel.rounds == 3
    assert result.panel.confidence is not None
    # Every agent got the topic plus an assigned sub-question.
    first = [c for c in panel_script.calls if c["kind"] == "AgentTurn" and c["round"] == 0]
    assert all("TOPIC: Is X true?" in c["text"] and "YOUR RESEARCH FOCUS: " in c["text"] for c in first)
    # Summary-only boundary: no raw agent argument ever reaches a manager prompt.
    manager_text = "\n".join(str(m.content) for call in manager.calls for m in call)
    assert "Panel conclusion: Yes, X is true." in manager_text
    assert panel_script.raw_marker not in manager_text


def test_manager_intervention_end_to_end(monkeypatch, panel_fake):
    def stance(aid, rnd, shifted, prompt):
        if "MANAGER INTERVENTION — re-anchor" in prompt:
            return yes_unless_shifted(aid, rnd, shifted, prompt)
        return split(aid, rnd, shifted, prompt)

    panel_fake(DebateScript(stance=stance, new_argument_count=0))
    _manager_fake(
        monkeypatch,
        tool_call("ResearchPlan", PLAN_ARGS),
        AIMessage(content="Manager notes."),
        # hop 1 deadlocks → manager intervenes without an LLM call; hop 2 → drift check
        tool_call("DriftCheck", {"on_track": True}),
        tool_call("AnswerDraft", ANSWER_ARGS),
    )
    state = build_manager_graph().invoke({"topic": "Is X true?"}, config={"recursion_limit": 60})
    result = FinalAnswer.model_validate(state["result"])
    assert result.panel.hops == 2 and len(result.panel.interventions) == 1
    assert result.panel.status == "consensus"
    # hop 1: split, stops on no-new-arguments at round 2; hop 2: 8/10 hold through the
    # devil's-advocate round, which adds nothing new → stops at round 2 as consensus.
    assert result.panel.rounds == 2 + 2 and result.panel.stop_reason == "no_new_arguments"


def test_stream_manager_surfaces_debate_events(monkeypatch, panel_fake):
    panel_fake(DebateScript(stance=yes_unless_shifted))
    _manager_fake(
        monkeypatch,
        tool_call("ResearchPlan", PLAN_ARGS),
        AIMessage(content="Manager notes."),
        tool_call("DriftCheck", {"on_track": True}),
        tool_call("AnswerDraft", ANSWER_ARGS),
    )
    events = list(stream_manager("Is X true?"))
    types = [e["type"] for e in events]
    assert types[-1] == "final_answer"
    for t in ("panel_start", "agent_turn", "perspective_shift", "round_summary", "stop", "consensus"):
        assert t in types
    assert types.index("panel_start") < types.index("consensus") < types.index("final_answer")
    assert all(e["source"] == "panel" for e in events if e["type"] == "agent_turn")
    # No raw panel state updates leak through the manager stream.
    assert {e["type"] for e in events} <= {
        "manager_step", "panel_start", "agent_turn", "perspective_shift",
        "round_start", "round_summary", "stop", "consensus", "final_answer",
        "research_digest", "turn_rejected", "engagement_gate",
    }
