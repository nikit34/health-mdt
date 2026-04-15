"""PubMed (E-utilities) client — evidence base for agent conclusions.

No API key needed for ≤3 req/s. We cache hits in PubmedEvidence table so
repeated queries cost nothing.
"""
from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import httpx
from sqlmodel import Session, select

from ..db import PubmedEvidence

log = logging.getLogger(__name__)

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

CACHE_TTL_DAYS = 14


def fetch_pubmed_evidence(
    queries: list[str],
    *,
    session: Session | None = None,
    max_per_query: int = 3,
) -> dict[str, list[str]]:
    """For each query, return a list of PMIDs. Caches results.

    Returns: {query: [pmid, ...]}.
    """
    out: dict[str, list[str]] = {}
    with httpx.Client(timeout=15) as client:
        for q in queries:
            # Check cache
            if session:
                cached = _from_cache(session, q)
                if cached is not None:
                    out[q] = cached
                    continue
            try:
                pmids = _search(client, q, max_per_query)
            except Exception as e:
                log.warning("PubMed esearch failed for %r: %s", q, e)
                out[q] = []
                continue

            if not pmids:
                out[q] = []
                if session:
                    _cache_miss(session, q)
                continue

            try:
                records = _fetch(client, pmids)
            except Exception as e:
                log.warning("PubMed efetch failed: %s", e)
                records = [{"pmid": p, "title": "", "abstract": "", "authors": [], "journal": "", "year": None} for p in pmids]

            out[q] = [r["pmid"] for r in records]
            if session:
                _cache(session, q, records)

            # Be polite
            time.sleep(0.35)
    return out


def _search(client: httpx.Client, query: str, retmax: int) -> list[str]:
    resp = client.get(
        ESEARCH,
        params={
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": retmax,
            "sort": "relevance",
        },
    )
    resp.raise_for_status()
    return resp.json().get("esearchresult", {}).get("idlist", [])


def _fetch(client: httpx.Client, pmids: list[str]) -> list[dict]:
    resp = client.get(
        EFETCH,
        params={"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"},
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    out: list[dict] = []
    for article in root.findall(".//PubmedArticle"):
        pmid_el = article.find(".//PMID")
        title_el = article.find(".//ArticleTitle")
        abstract = " ".join(
            (el.text or "") for el in article.findall(".//Abstract/AbstractText")
        )
        journal_el = article.find(".//Journal/Title")
        year_el = article.find(".//JournalIssue/PubDate/Year")
        authors = [
            f"{(a.findtext('LastName') or '').strip()} {(a.findtext('Initials') or '').strip()}".strip()
            for a in article.findall(".//Author")
            if a.findtext("LastName")
        ]
        out.append({
            "pmid": pmid_el.text if pmid_el is not None else "",
            "title": title_el.text if title_el is not None else "",
            "abstract": abstract,
            "authors": authors[:6],
            "journal": journal_el.text if journal_el is not None else "",
            "year": int(year_el.text) if year_el is not None and year_el.text and year_el.text.isdigit() else None,
        })
    return out


def _from_cache(session: Session, query: str) -> list[str] | None:
    cutoff = datetime.utcnow() - timedelta(days=CACHE_TTL_DAYS)
    stmt = (
        select(PubmedEvidence)
        .where(PubmedEvidence.query == query, PubmedEvidence.fetched_at >= cutoff)
        .order_by(PubmedEvidence.fetched_at.desc())
    )
    rows = session.exec(stmt).all()
    if not rows:
        return None
    # If we have at least 1 hit, use the cached PMIDs for this query
    return [r.pmid for r in rows if r.pmid]


def _cache(session: Session, query: str, records: list[dict]) -> None:
    for r in records:
        session.add(PubmedEvidence(
            query=query,
            pmid=r.get("pmid", ""),
            title=r.get("title", ""),
            abstract=r.get("abstract", "")[:4000],
            authors=r.get("authors", []),
            journal=r.get("journal", ""),
            pub_year=r.get("year"),
        ))
    session.commit()


def _cache_miss(session: Session, query: str) -> None:
    """Record that we searched but found nothing — prevents hammering."""
    session.add(PubmedEvidence(
        query=query, pmid="", title="(no results)", abstract="", authors=[], journal="", pub_year=None,
    ))
    session.commit()


def pubmed_url(pmid: str) -> str:
    return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
