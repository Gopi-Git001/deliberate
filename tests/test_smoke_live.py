"""Live smoke test (real GPT calls, costs money). Opt in: RUN_LIVE=1 and OPENAI_API_KEY set.

    RUN_LIVE=1 python -m pytest tests/test_smoke_live.py -s
"""

from __future__ import annotations

import os

import pytest
from dotenv import dotenv_values

from manager_agent.config import PROJECT_ROOT, get_settings
from manager_agent.panel.config import get_panel_settings

# Captured at import, before the autouse fixture blanks keys for offline tests.
_ENV = {**dotenv_values(PROJECT_ROOT / ".env"), **os.environ}
LIVE = os.environ.get("RUN_LIVE") == "1" and bool(_ENV.get("OPENAI_API_KEY"))

pytestmark = pytest.mark.skipif(not LIVE, reason="set RUN_LIVE=1 and OPENAI_API_KEY to run")


@pytest.fixture
def live_env(monkeypatch):
    for key in ("OPENAI_API_KEY", "OPENAI_MODEL", "PANEL_MODEL", "TAVILY_API_KEY"):
        if _ENV.get(key):
            monkeypatch.setenv(key, _ENV[key])
    # Keep the smoke run cheap: 3 rounds, 1 research tool step, no debate tool steps.
    monkeypatch.setenv("PANEL_MAX_ROUNDS", "3")
    monkeypatch.setenv("PANEL_RESEARCH_TOOL_STEPS", "1")
    monkeypatch.setenv("PANEL_DEBATE_TOOL_STEPS", "0")
    get_settings.cache_clear()
    get_panel_settings.cache_clear()
    yield
    get_settings.cache_clear()
    get_panel_settings.cache_clear()


def test_live_panel_smoke(live_env):
    from manager_agent.panel import stream_panel
    from manager_agent.schemas import DebateRules, PanelBrief

    brief = PanelBrief(
        topic="Remote work and productivity",
        goal="Does fully remote work increase knowledge-worker productivity?",
        sub_questions=["What do controlled studies find?", "What do firm-level data show?"],
        research_angles=[],
        debate_rules=DebateRules(max_rounds=3, consensus_criteria="majority", early_stop="no new args"),
        panel_size=10,
        hop=1,
    )
    events = list(stream_panel(brief))
    result = events[-1]["result"]
    raw_chars = sum(len(e.get("argument", "")) for e in events if e["type"] == "agent_turn")

    assert result["rounds_run"] >= 2
    assert result["stop_reason"] in {"consensus", "max_rounds", "no_new_arguments"}
    assert result["consensus"]
    assert sum(len(s) for s in result["round_summaries"]) < raw_chars
    print("\n".join(result["round_summaries"]), "\n\nCONSENSUS:", result["consensus"])


def test_live_manager_with_panel_smoke(live_env):
    from manager_agent.main import run_manager

    result = run_manager("Does fully remote work increase knowledge-worker productivity?")
    assert result.answer and result.panel.hops >= 1 and result.panel.status != "stub"
    print(result.model_dump_json(indent=2))
