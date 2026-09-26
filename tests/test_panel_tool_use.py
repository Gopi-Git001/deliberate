"""Panel agents actually use their tools: required-tool reminders, tool availability,
source_ranker on raw search output, and the agent's own tool results feeding the turn record."""

from __future__ import annotations

import json

import pytest
from conftest import ScriptedChatModel, tool_call
from langchain_core.messages import AIMessage

from manager_agent.panel.clones import make_panel
from manager_agent.panel.config import get_panel_settings
from manager_agent.panel.nodes import _record
from manager_agent.panel.schemas import AgentTurn, Citation
from manager_agent.panel.tools import available_panel_tools
from manager_agent.panel.tools.source_ranker import parse_sources, source_ranker
from manager_agent.panel.trace import ToolTracer, _current

SEARCH_OUTPUT = (
    "- Hybrid Working From Home Improves Retention: https://www.nature.com/articles/s41586-024-07500-2\n"
    "  RCT at Trip.com with 1,612 employees; quits fell by a third.\n"
    "- 30+ hybrid work statistics: https://www.worktime.com/blog/stats\n"
    "  Blog roundup of hybrid work numbers."
)
TURN = {"stance": "Yes.", "argument": "Because.", "self_confidence": 0.7}
CONFIG = {"metadata": {"agent.role": "research", "round.index": 0}}


@pytest.fixture(autouse=True)
def clear_panel_settings():
    get_panel_settings.cache_clear()
    yield
    get_panel_settings.cache_clear()


@pytest.fixture
def scripted(monkeypatch):
    import manager_agent.panel.llm as panel_llm

    def install(*script: AIMessage) -> ScriptedChatModel:
        model = ScriptedChatModel(script=list(script), calls=[])
        monkeypatch.setattr(panel_llm, "get_panel_llm", lambda: model)
        return model

    return install


@pytest.fixture
def tracer():
    t = ToolTracer(enabled=False)
    token = _current.set(t)
    yield t
    _current.reset(token)


def _texts(messages) -> str:
    return "\n".join(str(m.content) for m in messages)


def test_source_ranker_accepts_raw_web_search_output():
    sources = parse_sources(SEARCH_OUTPUT)
    assert [s["url"] for s in sources] == [
        "https://www.nature.com/articles/s41586-024-07500-2",
        "https://www.worktime.com/blog/stats",
    ]
    assert "Trip.com" in sources[0]["snippet"]
    ranked = json.loads(source_ranker.invoke({"sources": SEARCH_OUTPUT, "query": "hybrid retention"}))
    assert ranked[0]["url"].startswith("https://www.nature.com") and ranked[0]["score"] > ranked[1]["score"]


def test_source_ranker_still_accepts_json_and_rejects_garbage():
    one = json.dumps([{"title": "Paper", "url": "https://arxiv.org/abs/1"}])
    assert json.loads(source_ranker.invoke({"sources": one}))[0]["credibility"] == 0.9
    assert source_ranker.invoke({"sources": "nothing here"}).startswith("source_ranker error")


def test_unusable_tools_are_not_offered(isolated_settings, monkeypatch):
    names = {t.name for t in available_panel_tools()}
    assert "code_runner" not in names and "document_reader" not in names  # no E2B key, empty DOCUMENT_ROOT

    (isolated_settings / "report.md").write_text("# Offshore wind costs", encoding="utf-8")
    monkeypatch.setenv("E2B_API_KEY", "e2b-test")
    from manager_agent.config import get_settings

    get_settings.cache_clear()
    names = {t.name for t in available_panel_tools()}
    assert {"code_runner", "document_reader"} <= names
    assert "report.md" in make_panel(10)[0].system_prompt  # agents are told which documents exist


def test_agent_reminded_when_it_stops_before_required_tools(scripted, tracer):
    model = scripted(
        tool_call("web_search", {"query": "x"}),
        AIMessage(content="done"),  # stops early → reminded
        tool_call("citation", {"title": "Paper", "url": "https://arxiv.org/abs/1"}),
        AIMessage(content="done"),  # still missing source_ranker → only one reminder, then answer
        tool_call("AgentTurn", TURN),
    )
    make_panel(10)[0].take_turn(
        "go", 5, CONFIG, required_tools=("web_search", "source_ranker", "citation", "code_runner")
    )
    assert "you must still call: source_ranker, citation" in _texts(model.calls[2])  # code_runner not offered
    stats = tracer.stats["panel_agent_00"]
    assert stats.reminders == 1
    assert stats.skipped_required == [("research", 0, 1, ["source_ranker"])]
    assert "research r0 attempt 1 — skipped source_ranker" in tracer.summary()


def test_last_step_reminder_makes_room_for_vetting_tools(scripted, tracer):
    model = scripted(
        tool_call("web_search", {"query": "x"}),
        tool_call("source_ranker", {"sources": SEARCH_OUTPUT}),
        tool_call("AgentTurn", TURN),
    )
    usage: list[dict] = []
    make_panel(10)[0].take_turn("go", 2, CONFIG, required_tools=("web_search", "source_ranker"), usage=usage)
    assert "LAST tool step" in _texts(model.calls[1]) and "source_ranker" in _texts(model.calls[1])
    assert [u["tool"] for u in usage] == ["web_search", "source_ranker"]
    assert not tracer.stats["panel_agent_00"].skipped_required


def test_record_uses_agents_own_tool_results():
    ranked = [{"title": "Blog", "url": "https://www.worktime.com/blog/stats", "score": 0.99}]
    usage = [
        {"tool": "web_search", "args": {}, "result": SEARCH_OUTPUT, "error": False},
        {"tool": "source_ranker", "args": {}, "result": json.dumps(ranked), "error": False},
        {"tool": "confidence_scorer", "args": {}, "result": json.dumps({"score": 0.66, "label": "medium"}), "error": False},
    ]
    turn = AgentTurn(**TURN, citations=[Citation(title="Blog", url="https://www.worktime.com/blog/stats")])
    rec = _record("panel_agent_00", 0, turn, "hybrid", shifted=False, usage=usage)
    assert rec["avg_source_score"] == 0.99  # the agent's ranking, not the heuristic 0.5-ish
    assert rec["agent_ranked_sources"] == 1
    assert rec["agent_confidence"] == 0.66
    assert rec["tools_used"] == {"web_search": 1, "source_ranker": 1, "confidence_scorer": 1}


def test_source_ranker_accepts_snippet_on_url_line():
    # Shape agents produced in a live run when re-pasting search results.
    text = (
        "- Renewable power generation costs in 2025: https://www.irena.org/Publications/2026/Jul/Costs  "
        "In 2025 solar PV remained USD 44/MWh.\n"
        "- CHP at Wastewater Plants: https://betterbuildingssolutioncenter.energy.gov/chp.pdf ; $60,000 annual savings"
    )
    sources = parse_sources(text)
    assert [s["url"] for s in sources] == [
        "https://www.irena.org/Publications/2026/Jul/Costs",
        "https://betterbuildingssolutioncenter.energy.gov/chp.pdf",
    ]
    assert sources[0]["snippet"].startswith("In 2025 solar PV")
