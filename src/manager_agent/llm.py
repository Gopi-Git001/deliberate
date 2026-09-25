"""Single place that builds the manager's GPT client."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from manager_agent.config import get_settings
from manager_agent.runtime import check_cancelled, demo_enabled


class MissingAPIKeyError(RuntimeError):
    """Raised when the LLM is invoked without OPENAI_API_KEY."""


def has_openai_key() -> bool:
    return demo_enabled() or bool(get_settings().openai_api_key)


def get_llm() -> BaseChatModel:
    """Return the manager brain. Fails fast if OPENAI_API_KEY is missing."""
    check_cancelled()
    if demo_enabled():
        from manager_agent.demo import demo_llm

        return demo_llm()
    settings = get_settings()
    if not settings.openai_api_key:
        raise MissingAPIKeyError(
            "OPENAI_API_KEY is missing. Copy .env.example to .env and set your key."
        )
    return ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key)
