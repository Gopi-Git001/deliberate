"""Simple Chroma-backed memory. Requires OPENAI_API_KEY for embeddings when live."""

from __future__ import annotations

from langchain_core.tools import tool

from manager_agent.config import get_settings


@tool
def memory_store(text: str, metadata_json: str = "{}") -> str:
    """Store a memory snippet in the vector database."""
    settings = get_settings()
    if not settings.openai_api_key:
        return (
            "[placeholder] Set OPENAI_API_KEY to enable embeddings/memory. "
            f"Would store {len(text)} chars."
        )
    return (
        "[placeholder] Wire Chroma + OpenAI embeddings in memory.py. "
        f"persist_dir={settings.chroma_persist_dir}"
    )


@tool
def memory_query(query: str, k: int = 5) -> str:
    """Retrieve top-k memories relevant to a query."""
    settings = get_settings()
    if not settings.openai_api_key:
        return f"[placeholder] Memory query disabled. Would search: {query!r} (k={k})"
    return "[placeholder] Wire Chroma retrieval in memory.py."
