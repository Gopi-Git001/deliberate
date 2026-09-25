"""Web search via Tavily. Requires TAVILY_API_KEY."""

from __future__ import annotations

from langchain_core.tools import tool

from manager_agent.config import get_settings


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """Search the public web for recent information on a query."""
    settings = get_settings()
    if not settings.tavily_api_key:
        return (
            "[placeholder] Set TAVILY_API_KEY to enable Tavily search. "
            f"Would search: {query!r} (max_results={max_results})"
        )
    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=settings.tavily_api_key)
        result = client.search(query=query, max_results=max_results)
        rows = result.get("results") or []
        if not rows:
            return "No results."
        lines = []
        for r in rows:
            lines.append(
                f"- {r.get('title', 'untitled')}: {r.get('url', '')}\n  {r.get('content', '')[:400]}"
            )
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001 — surface tool errors to the agent
        return f"web_search error: {exc}"
