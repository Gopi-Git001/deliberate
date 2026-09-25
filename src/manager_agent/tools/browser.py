"""Browser placeholder. Wire to Browserbase / Playwright / similar."""

from __future__ import annotations

from langchain_core.tools import tool

from manager_agent.config import get_settings


@tool("browser")
def browser_navigate(url: str, instruction: str = "Extract main content") -> str:
    """Open a URL in a browser session and extract content per instruction."""
    settings = get_settings()
    if not settings.browser_api_key:
        return (
            "[placeholder] Browser not configured (set BROWSER_API_KEY or integrate "
            f"Playwright). Would open {url!r} with instruction: {instruction!r}. "
            "Use web_search result snippets instead."
        )
    return f"[placeholder] Browser backend not wired yet for {url!r}."
