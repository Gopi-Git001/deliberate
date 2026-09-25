"""Normalize a citation (title, url, quote) so claims carry consistent references."""

from __future__ import annotations

import hashlib
import json
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from langchain_core.tools import tool

_TRACKING = ("utm_", "fbclid", "gclid", "mc_cid", "mc_eid", "ref_src")


def normalize_url(url: str) -> str:
    """Strip tracking params and fragments; return '' for non-http(s) URLs."""
    url = (url or "").strip()
    parts = urlsplit(url)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return ""
    query = urlencode(
        [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith(_TRACKING)]
    )
    path = parts.path.rstrip("/") or ""
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def domain_of(url: str) -> str:
    netloc = urlsplit(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def make_citation(title: str, url: str = "", quote: str = "") -> dict:
    clean_url = normalize_url(url)
    title = (title or "").strip() or "untitled"
    quote = " ".join((quote or "").split())[:300]
    key = clean_url or title.lower()
    cite = {
        "id": "cite-" + hashlib.sha1(key.encode()).hexdigest()[:6],
        "title": title,
        "url": clean_url,
        "domain": domain_of(clean_url) if clean_url else "",
        "quote": quote,
    }
    src = f"{title} ({cite['domain']}) <{clean_url}>" if clean_url else f"{title} (no URL)"
    cite["formatted"] = f'"{quote}" — {src}' if quote else src
    if url and not clean_url:
        cite["warning"] = "URL was not a valid http(s) link and was dropped."
    return cite


@tool
def citation(title: str, url: str = "", quote: str = "") -> str:
    """Normalize a citation for a claim: cleans the URL, trims the quote, returns a stable id and formatted reference (JSON)."""
    return json.dumps(make_citation(title, url, quote), ensure_ascii=False)
