"""Tool-call trace: every panel tool call is logged live, before its result reaches the agent."""

from __future__ import annotations

import pytest
from panel_fake import DebateScript, PanelFakeModel

from manager_agent.panel.clones import make_panel
from manager_agent.panel.config import get_panel_settings
from manager_agent.panel.graph import stream_panel
from manager_agent.panel.trace import ToolTracer, _current
from manager_agent.schemas import DebateRules, PanelBrief

@pytest.fixture(autouse=True)
def clear_panel_settings():
    get_panel_settings.cache_clear()
    yield
    get_panel_settings.cache_clear()


@pytest.fixture
def fake(monkeypatch):
    import manager_agent.panel.llm as panel_llm

    script = DebateScript(stance=lambda *a: "Yes, X is true.", research_tool_call=True)
    monkeypatch.setattr(panel_llm, "get_panel_llm", lambda: PanelFakeModel(script=script))
    return script


class Recorder:
    """Trace stream that remembers how many LLM calls had happened at each write."""

    def __init__(self, script: DebateScript) -> None:
        self.script, self.writes = script, []

    def write(self, text: str) -> None:
        if text.strip():
            self.writes.append((len(self.script.calls), text))

    def flush(self) -> None:
        pass


def test_tool_call_traced_before_result_reaches_agent(fake):
    rec = Recorder(fake)
    tracer = ToolTracer(stream=rec)
    token = _current.set(tracer)
    try:
        agent = make_panel(10)[4]
        config = {"metadata": {"agent.id": agent.agent_id, "agent.role": "research", "round.index": 0}}
        agent.take_turn("RESEARCH ROUND: go", 3, config)
    finally:
        _current.reset(token)

    call_writes = [(n, t) for n, t in rec.writes if t.startswith("[trace #")]
    assert len(call_writes) == 1
    llm_calls_before, text = call_writes[0]
    assert "panel_agent_04" in text and "research r0" in text
    assert "tool:     citation" in text
    assert '"url": "https://arxiv.org/abs/1?utm_source=x"' in text  # exact args, before normalization
    assert '"url": "https://arxiv.org/abs/1"' in text  # raw tool result (normalized citation JSON)
    # Logged after the tool-calling LLM step, before the LLM step that consumes the result.
    assert llm_calls_before == 1 and len(fake.calls) > llm_calls_before
    assert '"domain": "arxiv.org"' in fake.calls[llm_calls_before]["text"]  # next LLM call sees the result

    stats = tracer.stats["panel_agent_04"]
    assert (stats.tool_calls, stats.responses, stats.responses_with_tools) == (1, 1, 1)
    assert not stats.no_tool_responses


def test_response_without_tool_call_is_flagged():
    tracer = ToolTracer(enabled=False)
    tracer.response(agent_id="panel_agent_01", role="debate", round_index=1, attempt=1, tool_calls=0, max_tool_steps=1)
    tracer.response(agent_id="panel_agent_01", role="debate", round_index=1, attempt=2, tool_calls=0, max_tool_steps=0)
    summary = tracer.summary()
    assert "⚠ FLAGGED" in summary
    assert "model chose not to call any tool" in summary
    assert "tool steps disabled for this call (max_tool_steps=0)" in summary


def test_full_run_streams_trace_live_and_prints_summary(fake, capsys):
    brief = PanelBrief(
        topic="T", goal="Is X true?", sub_questions=["Is X true?"], research_angles=[], panel_size=10, hop=1,
        debate_rules=DebateRules(max_rounds=2, consensus_criteria="8/10", early_stop="none"),
    )
    events = list(stream_panel(brief))
    err = capsys.readouterr().err

    assert events[-1]["type"] == "panel_result"
    assert err.count("tool:     citation") == 10  # one research call per agent
    for i in range(10):
        assert f"panel_agent_{i:02d}  research r0 attempt 1: response formed after 1 tool call(s)" in err
    assert "⚠ NO TOOL CALL" in err  # fake debate turns never call tools
    summary = err[err.index("TOOL-CALL TRACE SUMMARY"):]
    assert "panel_agent_00" in summary and "responded WITHOUT a tool call" in summary
    assert err.index("[trace #1]") < err.index("TOOL-CALL TRACE SUMMARY")


def test_trace_can_be_disabled(fake, capsys, monkeypatch):
    monkeypatch.setenv("PANEL_TOOL_TRACE", "false")
    brief = PanelBrief(
        topic="T", goal="Is X true?", sub_questions=["Is X true?"], research_angles=[], panel_size=10, hop=1,
        debate_rules=DebateRules(max_rounds=1, consensus_criteria="8/10", early_stop="none"),
    )
    list(stream_panel(brief))
    assert "TOOL-CALL TRACE" not in capsys.readouterr().err


def test_returned_error_text_counts_as_tool_error():
    tracer = ToolTracer(enabled=False)
    quota = "web_search error: This request exceeds your plan's set usage limit."
    for _ in range(2):
        tracer.tool_call(
            agent_id="panel_agent_00", role="research", round_index=0, attempt=1, step=1, tool="web_search",
            call_id="c", args={"query": "q"}, result=quota, started_at="t", duration_ms=1, error=False,
            passed_chars=len(quota),
        )
    tracer.response(agent_id="panel_agent_00", role="research", round_index=0, attempt=1, tool_calls=2, max_tool_steps=5)
    summary = tracer.summary()
    assert tracer.stats["panel_agent_00"].tool_errors == 2
    assert "2 × web_search: web_search error: This request exceeds" in summary
    assert "Every agent response was preceded" in summary
    assert "No panel agent responses were recorded" not in summary
