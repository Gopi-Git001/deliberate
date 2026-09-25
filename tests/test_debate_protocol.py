"""Round 1+ debate protocol: digest broadcast, engagement validators, engagement-gated consensus."""

from __future__ import annotations

import re

import pytest
from panel_fake import DebateScript, PanelFakeModel

from manager_agent.panel.config import get_panel_settings
from manager_agent.panel.graph import _inputs, panel_app, stream_panel
from manager_agent.panel.schemas import DebateTurn
from manager_agent.panel.validators import (
    NO_PERSUASION,
    PEERS_NOT_ENGAGED,
    RESTATED_RESEARCH,
    TOO_FEW_PEERS,
    canonical_agent,
    check_turn,
    similarity,
)
from manager_agent.schemas import DebateRules, PanelBrief

IDS = [f"panel_agent_{i:02d}" for i in range(10)]


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
        topic="Topic T", goal="Is X true?", sub_questions=["What is X?", "Evidence for X?"],
        research_angles=[], panel_size=10, hop=1,
        debate_rules=DebateRules(max_rounds=5, consensus_criteria="8/10", early_stop="no new args"),
    )
    return PanelBrief(**{**base, **kw})


def yes_unless_shifted(aid, rnd, shifted, prompt):
    return "No, X is false." if shifted else "Yes, X is true."


def fresh_urls(aid, r):
    return [f"https://arxiv.org/abs/{aid}-{r}"]


def turn(**kw) -> DebateTurn:
    base = dict(
        stance="Yes.", argument="panel_agent_01 overstates the trial; panel_agent_02 is right on cost.",
        addressed_agents=["panel_agent_01", "panel_agent_02"],
        agreements=["panel_agent_02: cost source is solid"], disagreements=["panel_agent_01: trial too small"],
        position_decision="hold", stance_delta="held: no stronger evidence",
        persuasion_target="panel_agent_01", persuasion_appeal="panel_agent_01 should accept the larger trial.",
        self_confidence=0.7,
    )
    return DebateTurn(**{**base, **kw})


# --- validators ------------------------------------------------------------------------------


def test_similarity_flags_restatement_not_new_arguments():
    note = "Remote work raised call-centre output 13% in the Ctrip trial, but knowledge work differs."
    assert similarity(note, note) == 1.0
    assert similarity(note, "Remote work raised call-centre output by 13% in the Ctrip trial; knowledge work differs.") >= 0.6
    assert similarity(note, "panel_agent_04 ignores attrition; the Nature hybrid RCT answers a different question.") < 0.3


def test_canonical_agent_refs():
    assert canonical_agent("Panel 4", IDS) == "panel_agent_04"
    assert canonical_agent("panel_agent_07", IDS) == "panel_agent_07"
    assert canonical_agent("panel_agent_12", IDS) is None


def test_valid_turn_passes():
    check = check_turn(turn(), agent_id="panel_agent_00", panel_ids=IDS, research_note="Totally different note text here.")
    assert check.ok and check.addressed == ["panel_agent_01", "panel_agent_02"]


@pytest.mark.parametrize(
    "overrides, reason",
    [
        ({"addressed_agents": ["panel_agent_00", "panel_agent_01"]}, TOO_FEW_PEERS),  # self doesn't count
        ({"addressed_agents": ["panel_agent_01", "panel_agent_99"]}, TOO_FEW_PEERS),  # unknown id
        ({"addressed_agents": ["panel_agent_01", "panel_agent_05"]}, PEERS_NOT_ENGAGED),  # 05 never engaged
        ({"persuasion_target": "panel_agent_08"}, NO_PERSUASION),  # target not addressed
        ({"persuasion_appeal": "agree"}, NO_PERSUASION),  # no substantive appeal
    ],
)
def test_invalid_turns_rejected(overrides, reason):
    check = check_turn(turn(**overrides), agent_id="panel_agent_00", panel_ids=IDS)
    assert reason in check.reasons


def test_restated_research_rejected():
    note = "panel_agent_01 overstates the trial; panel_agent_02 is right on cost."
    check = check_turn(turn(), agent_id="panel_agent_00", panel_ids=IDS, research_note=note)
    assert RESTATED_RESEARCH in check.reasons


# --- protocol through the real panel graph ------------------------------------------------


def test_research_is_independent_and_digest_broadcast_before_round_1(panel_fake):
    script = panel_fake(DebateScript(stance=yes_unless_shifted))
    events = list(stream_panel(brief()))
    research = [c for c in script.calls if c["kind"] == "AgentTurn"]
    assert len(research) == 10
    for c in research:  # no peer ids, no digest during research
        others = set(re.findall(r"panel_agent_\d\d", c["text"])) - {c["agent_id"]}
        assert not others and "RESEARCH_DIGEST" not in c["text"]

    types = [e["type"] for e in events]
    digest = next(e for e in events if e["type"] == "research_digest")
    assert digest["count"] == 10 and types.index("research_digest") < types.index("round_start")

    round1 = [c for c in script.calls if c["kind"] == "DebateTurn" and c["round"] == 1]
    assert len(round1) == 10
    for c in round1:
        block = c["text"].split("RESEARCH_DIGEST")[1].split("PRIOR_ROUND_ARGUMENTS")[0]
        assert all(f"- {aid} [" in block for aid in IDS)  # every agent's note is in the digest


def test_round_2_responds_to_round_1_arguments(panel_fake):
    script = panel_fake(DebateScript(stance=yes_unless_shifted))
    list(stream_panel(brief()))
    c = next(c for c in script.calls if c["kind"] == "DebateTurn" and c["round"] == 2 and c["agent_id"] == "panel_agent_04")
    prior = c["text"].split("PRIOR_ROUND_ARGUMENTS (Round 1):")[1].split("PRIOR ROUND SUMMARY")[0]
    assert "RAWARG-panel_agent_01-r1" in prior  # a peer's Round 1 argument
    assert "RAWARG-panel_agent_04-r1" not in prior  # not its own
    assert "Respond to what peers argued in PRIOR_ROUND_ARGUMENTS (Round 1)" in c["text"]


def test_restated_turn_is_rejected_and_regenerated(panel_fake):
    script = panel_fake(DebateScript(stance=yes_unless_shifted, restate={"panel_agent_04": "once"}))
    events = list(stream_panel(brief()))
    rejected = [e for e in events if e["type"] == "turn_rejected"]
    assert len(rejected) == 1 and rejected[0]["agent_id"] == "panel_agent_04"
    assert RESTATED_RESEARCH in rejected[0]["reasons"]
    retry = [c for c in script.calls if c["kind"] == "DebateTurn" and c["agent_id"] == "panel_agent_04" and c["round"] == 1]
    assert len(retry) == 2 and "YOUR PREVIOUS DRAFT WAS REJECTED" in retry[1]["text"]
    accepted = next(e for e in events if e["type"] == "agent_turn" and e["agent_id"] == "panel_agent_04" and e["round"] == 1)
    assert accepted["attempts"] == 2 and not accepted["engagement_failed"]
    assert events[-1]["result"]["status"] == "consensus"


def test_persistent_restatement_blocks_consensus(panel_fake):
    panel_fake(DebateScript(stance=yes_unless_shifted, restate={"panel_agent_01": "always", "panel_agent_02": "always"}))
    events = list(stream_panel(brief()))
    result = events[-1]["result"]
    degraded = [e for e in events if e["type"] == "agent_turn" and e["round"] == 1 and e["engagement_failed"]]
    assert {e["agent_id"] for e in degraded} == {"panel_agent_01", "panel_agent_02"}
    gate = [e for e in events if e["type"] == "engagement_gate"]
    assert gate and "Round 1 restated research" in gate[0]["reasons"][0]
    # A 10/10 "agreement" without engagement is echo, not success.
    assert result["stop_reason"] == "max_rounds" and result["status"] == "deadlock"
    assert "Engagement gate failed" in result["dissent"]
    shifts = [e for e in events if e["type"] == "perspective_shift"]
    assert any(e["trigger"] == "invalid_consensus" for e in shifts)  # forced another shift


def test_agent_that_never_engages_blocks_consensus(panel_fake):
    panel_fake(DebateScript(stance=yes_unless_shifted, lazy={"panel_agent_06"}))
    result = list(stream_panel(brief()))[-1]["result"]
    assert result["status"] == "deadlock" and "never engaged 2+ peers: panel_agent_06" in result["dissent"]


def test_seven_of_ten_is_not_consensus(panel_fake):
    panel_fake(DebateScript(stance=lambda aid, r, s, p: "Yes." if int(aid[-2:]) < 7 else "No.", urls=fresh_urls))
    result = list(stream_panel(brief()))[-1]["result"]
    assert result["status"] == "deadlock" and result["stop_reason"] == "max_rounds"
    assert "[3/10]" in result["dissent"]  # minority documented


def test_no_new_arguments_stop_requires_engaged_round(panel_fake):
    split = lambda aid, r, s, p: "Yes." if int(aid[-2:]) % 2 == 0 else "No."  # noqa: E731
    panel_fake(DebateScript(stance=split, new_argument_count=0, lazy={"panel_agent_00", "panel_agent_01"}))
    result = list(stream_panel(brief()))[-1]["result"]
    assert result["stop_reason"] == "max_rounds"  # stale rounds, but engagement failed → keep debating


def test_engagement_tracked_per_agent_per_round(panel_fake):
    panel_fake(DebateScript(stance=yes_unless_shifted))
    state = panel_app.invoke(_inputs(brief()), config={"recursion_limit": 60})
    debate = [o for o in state["agent_outputs"] if o["round"] >= 1]
    assert len(debate) == 10 * state["round_index"]
    for o in debate:
        assert len(o["addressed_agents"]) >= 2 and o["agent_id"] not in o["addressed_agents"]
        assert o["agreements"] and o["disagreements"] and o["evidence_cited"]
        assert o["position_decision"] in {"hold", "revise", "abandon"} and o["stance_delta"]
        assert isinstance(o["position_changed"], bool)
    shifted = [o for o in debate if o["shifted"]]
    assert {o["agent_id"] for o in shifted} == {"panel_agent_03", "panel_agent_05"}
    assert all(o["position_changed"] for o in shifted)

    summary = state["panel_summaries"][1]  # shift round
    for part in ("Positions:", "Engagement: 10/10", "Moved: panel_agent_03 (revise)", "Dissent: [2/10]", "Exchanges:"):
        assert part in summary, part
