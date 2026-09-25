"""Score source credibility + relevance with transparent heuristics (no LLM)."""

from __future__ import annotations

import json
import re

from langchain_core.tools import tool

from manager_agent.panel.tools.citation import domain_of, normalize_url

_HIGH = (
    ".gov", ".edu", ".int", "arxiv.org", "nature.com", "science.org", "nih.gov",
    "who.int", "acm.org", "ieee.org", "springer.com", "sciencedirect.com",
    "semanticscholar.org", "oecd.org", "un.org", "nber.org", "thelancet.com",
    "nejm.org", "pnas.org", "cell.com", "wiley.com",
)
_MEDIUM_HIGH = (
    "reuters.com", "apnews.com", "bbc.co.uk", "bbc.com", "nytimes.com", "ft.com",
    "economist.com", "wsj.com", "theguardian.com", "bloomberg.com", "washingtonpost.com",
)
_LOW = (
    "medium.com", "substack.com", "blogspot.com", "wordpress.com", "reddit.com",
    "quora.com", "x.com", "twitter.com", "facebook.com", "tiktok.com", "youtube.com",
)


def _matches(domain: str, patterns: tuple[str, ...]) -> bool:
    """'.gov' matches any *.gov; 'nih.gov' matches nih.gov and its subdomains."""
    return any(
        domain.endswith(p) if p.startswith(".") else domain == p or domain.endswith("." + p)
        for p in patterns
    )


def credibility(url: str) -> tuple[float, str]:
    clean = normalize_url(url)
    if not clean:
        return 0.2, "no verifiable URL"
    domain = domain_of(clean)
    if _matches(domain, _HIGH):
        score, why = 0.9, "academic/official source"
    elif domain.endswith("wikipedia.org"):
        score, why = 0.6, "encyclopedia (secondary)"
    elif _matches(domain, _MEDIUM_HIGH):
        score, why = 0.75, "established news outlet"
    elif _matches(domain, _LOW):
        score, why = 0.35, "user-generated / blog / social"
    else:
        score, why = 0.5, "unknown domain"
    if clean.startswith("http://"):
        score -= 0.05
        why += ", not https"
    return round(score, 2), why


def _terms(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 3}


def rank_sources(sources: list[dict], query: str = "") -> list[dict]:
    q = _terms(query)
    ranked = []
    for s in sources:
        cred, why = credibility(s.get("url", ""))
        text = f"{s.get('title', '')} {s.get('snippet', '')} {s.get('quote', '')}"
        rel = len(q & _terms(text)) / len(q) if q else 0.5
        ranked.append(
            {
                "title": s.get("title", "untitled"),
                "url": normalize_url(s.get("url", "")),
                "credibility": cred,
                "relevance": round(rel, 2),
                "score": round(0.7 * cred + 0.3 * rel, 2),
                "why": why,
            }
        )
    return sorted(ranked, key=lambda r: r["score"], reverse=True)


@tool
def source_ranker(sources_json: str, query: str = "") -> str:
    """Rank sources by credibility and relevance.

    sources_json: JSON list of {"title", "url", "snippet"?}. Returns the list sorted
    by score (0-1) with credibility, relevance, and the reason.
    """
    try:
        sources = json.loads(sources_json)
        if not isinstance(sources, list):
            raise ValueError("expected a JSON list")
    except (ValueError, TypeError) as exc:
        return f"source_ranker error: sources_json must be a JSON list of objects ({exc})"
    return json.dumps(rank_sources([s for s in sources if isinstance(s, dict)], query), ensure_ascii=False)
