"""The panel's GPT client (shared by all 10 clones)."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from manager_agent.llm import MissingAPIKeyError
from manager_agent.panel.config import get_panel_settings
from manager_agent.runtime import check_cancelled, demo_enabled


def has_panel_key() -> bool:
    return demo_enabled() or bool(get_panel_settings().openai_api_key)


def get_panel_llm() -> BaseChatModel:
    """Return the panel brain. Fails fast if OPENAI_API_KEY is missing."""
    check_cancelled()
    if demo_enabled():
        from manager_agent.demo import demo_llm

        return demo_llm()
    settings = get_panel_settings()
    if not settings.openai_api_key:
        raise MissingAPIKeyError(
            "OPENAI_API_KEY is missing — the panel cannot run. "
            "Copy .env.example to .env and set your key."
        )
    return ChatOpenAI(model=settings.model, api_key=settings.openai_api_key)
