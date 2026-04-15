"""Semantic Scholar API client — grounds agents in broader clinical literature.

Why Semantic Scholar and not Google Scholar:
- Google Scholar has no official API; scraping is brittle and rate-limited.
- Semantic Scholar is free, has a real API, covers PubMed + ArXiv + conferences +
  clinical guidelines, and returns structured metadata (venue, year, citations).
- We index results by the same PubmedEvidence table using a `source` prefix in `query`,
  so UI/orchestrator can treat them uniformly.

https://api.semanticscholar.org/graph/v1/paper/search
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

import httpx
from sqlmodel import Session, select

from ..config import get_settings
from ..db import PubmedEvidence

log = logging.getLogger(__name__)

BASE = "https://api.semanticscholar.org/graph/v1"
CACHE_TTL_DAYS = 14
FIELDS = "paperId,externalIds,title,abstract,year,venue,authors.name,citationCount,publicationTypes,isOpenAccess,openAccessPdf"


def fetch_scholar_evidence(
    queries: list[str],
    *,
    session: Session | None = None,
    max_per_query: int = 3,
) -> dict[str, list[dict]]:
    """For each query, return Semantic Scholar papers.

    Returns: {query: [{paper_id, title, year, venue, url, ...}]}.
    Cached via `scholar:<query>` in PubmedEvidence.
    """
    settings = get_settings()
    headers = {}
    key = getattr(settings, "semantic_scholar_api_key", "") or ""
    if key:
        headers["x-api-key"] = key

    out: dict[str, list[dict]] = {}
    with httpx.Client(timeout=20, headers=headers) as client:
        for q in queries:
            cached = _from_cache(session, q) if session else None
            if cached is not None:
                out[q] = cached
                continue
            try:
                papers = _search(client, q, max_per_query)
            except httpx.HTTPStatusError as e:
                log.warning("SS search failed for %r: %s", q, e.response.status_code)
                out[q] = []
                continue
            except Exception as e:
                log.warning("SS search exception for %r: %s", q, e)
                out[q] = []
                continue

            records = [_normalize(p) for p in papers]
            out[q] = records
            if session:
                _cache(session, q, records)
            time.sleep(0.35)  # polite even with key
    return out


def _search(client: httpx.Client, query: str, limit: int) -> list[dict]:
    resp = client.get(
        f"{BASE}/paper/search",
        params={"query": query, "limit": limit, "fields": FIELDS},
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", [])


def _normalize(p: dict) -> dict:
    """Produce a compact record shared with PubMed evidence shape."""
    authors = [a.get("name", "") for a in p.get("authors", []) if a.get("name")]
    # Prefer PubMed ID if present, else Semantic Scholar paper ID
    ext = p.get("externalIds") or {}
    pmid = ext.get("PubMed") or ""
    ss_id = p.get("paperId") or ""
    url = (
        f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        if pmid
        else f"https://www.semanticscholar.org/paper/{ss_id}"
    )
    return {
        "pmid": pmid,
        "ss_id": ss_id,
        "title": p.get("title", "") or "",
        "abstract": (p.get("abstract") or "")[:4000],
        "authors": authors[:6],
        "journal": p.get("venue", "") or "",
        "year": p.get("year"),
        "citations": p.get("citationCount", 0),
        "open_access_pdf": (p.get("openAccessPdf") or {}).get("url"),
        "url": url,
        "source": "semantic_scholar",
    }


def _cache_key(query: str) -> str:
    return f"scholar:{query}"


def _from_cache(session: Session, query: str) -> list[dict] | None:
    cutoff = datetime.utcnow() - timedelta(days=CACHE_TTL_DAYS)
    stmt = (
        select(PubmedEvidence)
        .where(PubmedEvidence.query == _cache_key(query), PubmedEvidence.fetched_at >= cutoff)
        .order_by(PubmedEvidence.fetched_at.desc())
    )
    rows = session.exec(stmt).all()
    if not rows:
        return None
    # Reconstruct records from cached rows
    return [
        {
            "pmid": r.pmid,
            "ss_id": (r.meta or {}).get("ss_id", "") if hasattr(r, "meta") else "",
            "title": r.title,
            "abstract": r.abstract,
            "authors": r.authors,
            "journal": r.journal,
            "year": r.pub_year,
            "url": (
                f"https://pubmed.ncbi.nlm.nih.gov/{r.pmid}/"
                if r.pmid
                else f"https://www.semanticscholar.org/search?q={query}"
            ),
            "source": "semantic_scholar",
        }
        for r in rows
        if r.title and r.title != "(no results)"
    ]


def _cache(session: Session, query: str, records: list[dict]) -> None:
    if not records:
        session.add(PubmedEvidence(
            query=_cache_key(query), pmid="", title="(no results)",
            abstract="", authors=[], journal="", pub_year=None,
        ))
        session.commit()
        return
    for r in records:
        session.add(PubmedEvidence(
            query=_cache_key(query),
            pmid=r.get("pmid") or "",
            title=r.get("title", ""),
            abstract=r.get("abstract", "")[:4000],
            authors=r.get("authors", []),
            journal=r.get("journal", ""),
            pub_year=r.get("year"),
        ))
    session.commit()
