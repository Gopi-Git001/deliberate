"""Offline tests for the manager graph (no API keys, no network)."""

from __future__ import annotations

from langchain_core.messages import AIMessage
from conftest import ANSWER_ARGS, PLAN_ARGS, tool_call

from manager_agent.config import get_settings
from manager_agent.graph import build_manager_graph
from manager_agent.main import main
from manager_agent.panel import run_panel_stub
from manager_agent.schemas import FinalAnswer, PanelBrief, PanelResult
from manager_agent.tools import MANAGER_TOOLS
from manager_agent.tools.api_connector import api_connector
from manager_agent.tools.document_reader import document_reader


def run(app, topic="What is X?"):
    state = app.invoke({"topic": topic}, config={"recursion_limit": 60})
    return state, FinalAnswer.model_validate(state["result"])


def test_all_tools_registered():
    names = {t.name for t in MANAGER_TOOLS}
    assert names == {
        "web_search", "browser", "code_interpreter", "document_reader",
        "memory_store", "memory_query", "academic_search", "data_analysis",
        "api_connector", "summarizer", "fact_checker", "planner",
    }


def test_graph_shape():
    graph = build_manager_graph().get_graph()
    edges = {(e.source, e.target) for e in graph.edges}
    assert {
        ("__start__", "intake"), ("intake", "plan"), ("plan", "agent"),
        ("agent", "tools"), ("tools", "agent"), ("agent", "delegate"),
        ("delegate", "review"), ("review", "delegate"), ("review", "synthesize"),
        ("synthesize", "__end__"),
    } <= edges


def test_end_to_end_with_stub_panel(fake_llm, isolated_settings):
    (isolated_settings / "notes.md").write_text("LangGraph supports checkpoints.")
    llm = fake_llm(
        tool_call("ResearchPlan", PLAN_ARGS),
        tool_call("document_reader", {"path": "notes.md"}),
        AIMessage(content="Notes: X is a thing per notes.md"),
        tool_call("AnswerDraft", ANSWER_ARGS),
    )
    state, result = run(build_manager_graph(panel_runner=run_panel_stub))

    assert result.answer == state["final_answer"] == "X is a thing."
    assert result.plan.debate_rules.max_rounds == get_settings().max_debate_rounds  # clamped
    assert result.panel.status == "stub" and result.panel.hops == 1
    assert result.tool_calls == 1
    assert len(state["panel_summaries"]) == 1 and "[stub]" in state["panel_summaries"][0]
    # Synthesis saw the tool evidence and research notes, not just the plan.
    synth_prompt = str(llm.calls[-1][-1].content)
    assert "LangGraph supports checkpoints." in synth_prompt
    assert "Notes: X is a thing" in synth_prompt


def test_tool_loop_is_capped(fake_llm, monkeypatch):
    monkeypatch.setenv("MANAGER_MAX_TOOL_STEPS", "2")
    get_settings.cache_clear()
    fake_llm(
        tool_call("ResearchPlan", PLAN_ARGS),
        tool_call("planner", {"topic": "X"}, "c1"),
        tool_call("planner", {"topic": "X"}, "c2"),
        tool_call("planner", {"topic": "X"}, "c3"),  # over the cap → not executed
        tool_call("AnswerDraft", ANSWER_ARGS),
    )
    state, result = run(build_manager_graph(panel_runner=run_panel_stub))
    tool_results = [m for m in state["messages"] if m.type == "tool"]
    assert len(tool_results) == 2
    assert result.answer


def test_manager_intervenes_on_deadlock_then_accepts(fake_llm):
    briefs: list[PanelBrief] = []

    def panel(brief: PanelBrief) -> PanelResult:
        briefs.append(brief)
        if brief.hop == 1:
            return PanelResult(round_summaries=["R1: split 5/5"], status="deadlock", rounds_run=3)
        return PanelResult(
            round_summaries=["R4: converged"], consensus="X is a thing.",
            status="consensus", rounds_run=1,
        )

    fake_llm(
        tool_call("ResearchPlan", PLAN_ARGS),
        AIMessage(content="Notes."),
        tool_call("DriftCheck", {"on_track": True}),
        tool_call("AnswerDraft", ANSWER_ARGS),
    )
    state, result = run(build_manager_graph(panel_runner=panel))

    assert [b.hop for b in briefs] == [1, 2]
    assert briefs[0].directive == "" and briefs[1].directive  # directive only after drift
    assert result.panel.status == "consensus"
    assert result.panel.hops == 2 and result.panel.rounds == 4
    assert len(result.panel.interventions) == 1
    assert "on track" in result.verification
    assert state["panel_summaries"] == ["R1: split 5/5", "R4: converged"]


def test_healthy_panel_gets_no_intervention(fake_llm):
    def panel(brief):
        return PanelResult(round_summaries=["ok"], consensus="X.", status="consensus", rounds_run=2)

    fake_llm(
        tool_call("ResearchPlan", PLAN_ARGS),
        AIMessage(content="Notes."),
        tool_call("DriftCheck", {"on_track": True}),
        tool_call("AnswerDraft", ANSWER_ARGS),
    )
    _, result = run(build_manager_graph(panel_runner=panel))
    assert result.panel.hops == 1 and result.panel.interventions == []


def test_panel_hops_are_capped(fake_llm):
    def panel(brief):
        return PanelResult(round_summaries=["off"], consensus="Y.", status="consensus", rounds_run=1)

    fake_llm(
        tool_call("ResearchPlan", PLAN_ARGS),
        AIMessage(content="Notes."),
        tool_call("DriftCheck", {"on_track": False, "issue": "about Y", "directive": "Refocus A"}),
        tool_call("DriftCheck", {"on_track": False, "issue": "still Y", "directive": "Refocus B"}),
        tool_call("AnswerDraft", ANSWER_ARGS),
    )
    _, result = run(build_manager_graph(panel_runner=panel))
    assert result.panel.hops == get_settings().max_panel_hops == 2
    assert len(result.panel.interventions) == 1
    assert "hop limit" in result.verification


def test_panel_output_is_truncated_to_summaries(fake_llm):
    def panel(brief):
        return PanelResult(round_summaries=["t" * 50_000], status="stub", rounds_run=1)

    fake_llm(
        tool_call("ResearchPlan", PLAN_ARGS),
        AIMessage(content="Notes."),
        tool_call("AnswerDraft", ANSWER_ARGS),
    )
    state, _ = run(build_manager_graph(panel_runner=panel))
    assert len(state["panel_summaries"][0]) == get_settings().panel_summary_max_chars


def test_cli_fails_fast_without_key(capsys):
    assert main(["some topic"]) == 1
    assert "OPENAI_API_KEY is missing" in capsys.readouterr().err


def test_document_reader_cannot_escape_root_or_read_env(isolated_settings):
    (isolated_settings / ".env").write_text("SECRET=1")
    assert "refused" in document_reader.invoke({"path": ".env"})
    assert "refused" in document_reader.invoke({"path": "../outside.txt"})


def test_api_connector_refuses_unlisted_env_vars():
    out = api_connector.invoke(
        {"method": "GET", "url": "https://example.com", "auth_env_var": "OPENAI_API_KEY"}
    )
    assert "not in API_CONNECTOR_ALLOWED_ENV_VARS" in out
