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


_RESULT_LINE = re.compile(r"^\s*[-*]?\s*(.+?):\s+(https?://[^\s;,)\]]+)[;,)\]]?\s*(.*)$")


def parse_search_results(text: str) -> list[dict]:
    """Parse web_search output ('- Title: url' then indented snippet lines) into sources.

    Agents often re-paste it with the snippet on the URL line ('- Title: url  snippet'); accept that too.
    """
    sources: list[dict] = []
    for line in text.splitlines():
        m = _RESULT_LINE.match(line)
        if m:
            sources.append({"title": m.group(1).strip(), "url": m.group(2), "snippet": m.group(3).strip()})
        elif sources and line.startswith("  "):
            sources[-1]["snippet"] = f"{sources[-1]['snippet']} {line.strip()}".strip()
    return sources


def parse_sources(sources: str) -> list[dict]:
    """Accept a JSON list of {title, url, snippet?} or raw web_search output."""
    try:
        parsed = json.loads(sources)
    except (ValueError, TypeError):
        return parse_search_results(sources or "")
    if isinstance(parsed, dict):
        parsed = [parsed]
    return [s for s in parsed if isinstance(s, dict)] if isinstance(parsed, list) else []


@tool
def source_ranker(sources: str, query: str = "") -> str:
    """Rank sources by credibility and relevance.

    sources: the raw output of web_search (paste it as-is), or a JSON list of
    {"title", "url", "snippet"?}. Returns the sources sorted by score (0-1) with
    credibility, relevance, and the reason.
    """
    parsed = parse_sources(sources)
    if not parsed:
        return (
            "source_ranker error: no sources found — pass web_search output as-is or a JSON list "
            'of {"title", "url", "snippet"}'
        )
    return json.dumps(rank_sources(parsed, query), ensure_ascii=False)
