"""Academic search via Semantic Scholar and arXiv (no key required for basic use)."""

from __future__ import annotations

import httpx
from langchain_core.tools import tool

from manager_agent.config import get_settings


def _semantic_scholar(query: str, max_results: int) -> list[str]:
    headers = {}
    api_key = get_settings().semantic_scholar_api_key
    if api_key:
        headers["x-api-key"] = api_key
    params = {
        "query": query,
        "limit": max_results,
        "fields": "title,year,authors,url,abstract,citationCount",
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params=params,
            headers=headers,
        )
    if resp.status_code == 429:
        return ["Semantic Scholar: rate limited (429) — retry later or set SEMANTIC_SCHOLAR_API_KEY."]
    resp.raise_for_status()
    chunks = []
    for paper in resp.json().get("data") or []:
        authors = ", ".join(a.get("name", "") for a in (paper.get("authors") or [])[:3])
        abstract = (paper.get("abstract") or "")[:300]
        chunks.append(
            f"[S2] {paper.get('title')} ({paper.get('year')}, "
            f"{paper.get('citationCount', 0)} citations) — {authors}\n"
            f"  {paper.get('url')}\n  {abstract}"
        )
    return chunks


def _arxiv(query: str, max_results: int) -> list[str]:
    import arxiv

    client = arxiv.Client(num_retries=1)
    search = arxiv.Search(query=query, max_results=max_results)
    return [
        f"[arXiv] {r.title} ({r.published.year}) — {r.entry_id}\n  {r.summary[:300]}"
        for r in client.results(search)
    ]


@tool
def academic_search(query: str, source: str = "both", max_results: int = 5) -> str:
    """Search Semantic Scholar and/or arXiv for papers matching a query.

    source: 'semantic_scholar' | 'arxiv' | 'both'
    """
    source = (source or "both").lower()
    max_results = max(1, min(max_results, 10))
    chunks: list[str] = []

    if source in {"semantic_scholar", "both"}:
        try:
            chunks.extend(_semantic_scholar(query, max_results))
        except Exception as exc:  # noqa: BLE001 — surface tool errors to the agent
            chunks.append(f"Semantic Scholar error: {exc}")

    if source in {"arxiv", "both"}:
        try:
            chunks.extend(_arxiv(query, max_results))
        except Exception as exc:  # noqa: BLE001
            chunks.append(f"arXiv error: {exc}")

    return "\n\n".join(chunks) if chunks else "No academic results."
