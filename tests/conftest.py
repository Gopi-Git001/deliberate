"""Test fixtures: isolated settings and a scripted fake GPT."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from manager_agent.config import get_settings  # noqa: E402


class ScriptedChatModel(BaseChatModel):
    """Returns pre-scripted AIMessages in order and records every prompt."""

    script: list[AIMessage]
    calls: list[list[BaseMessage]] = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.calls.append(list(messages))
        if not self.script:
            raise AssertionError("ScriptedChatModel ran out of scripted responses")
        return ChatResult(generations=[ChatGeneration(message=self.script.pop(0))])


def tool_call(name: str, args: dict, call_id: str = "call_1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


PLAN_ARGS = {
    "goal": "Explain X",
    "sub_questions": ["What is X?", "Why does X matter?"],
    "research_angles": ["academic", "industry"],
    "debate_rules": {
        "max_rounds": 9,
        "consensus_criteria": "7/10 agree",
        "early_stop": "unanimous after round 1",
    },
    "verification_steps": ["fact-check key claims"],
}

ANSWER_ARGS = {
    "answer": "X is a thing.",
    "key_points": ["X exists", "X matters"],
    "sources": [{"title": "Sample doc", "url": ""}],
    "confidence": "medium",
    "confidence_notes": "Single local source.",
    "open_questions": [],
}


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    """No real keys, no network-backed tools, documents under tmp_path."""
    for var in ("OPENAI_API_KEY", "TAVILY_API_KEY", "BROWSER_API_KEY", "E2B_API_KEY"):
        monkeypatch.setenv(var, "")
    monkeypatch.setenv("DOCUMENT_ROOT", str(tmp_path))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


@pytest.fixture
def fake_llm(monkeypatch):
    """Install a scripted fake as the manager brain; returns a setter."""
    import manager_agent.nodes.manager as nodes

    def install(*script: AIMessage) -> ScriptedChatModel:
        model = ScriptedChatModel(script=list(script), calls=[])
        monkeypatch.setattr(nodes, "get_llm", lambda: model)
        return model

    return install
