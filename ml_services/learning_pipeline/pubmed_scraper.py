"""PubMed scraper for the continuous-learning pipeline (Module 10).

Uses NCBI E-utilities (esearch + efetch) — free, no key required (a key raises rate limits).
Every fetch is cached under data/raw/pubmed/ so the pipeline is reproducible offline and
tests never touch the network.

Patent claim #11: automated KG updating from Indian genomic literature via NLP triples.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional

from ml_services.config import RAW_DIR

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
CACHE_DIR = RAW_DIR / "pubmed"

DEFAULT_QUERIES = [
    '(rare disease[Title/Abstract]) AND (India[Title/Abstract] OR Indian[Title/Abstract])',
    '(thalassemia[Title/Abstract] OR "sickle cell"[Title/Abstract]) AND India[Title/Abstract]',
    '(consanguinity[Title/Abstract] AND (India[Title/Abstract] OR Indian[Title/Abstract]))',
    '(pharmacogenomics[Title/Abstract] OR "CYP2C19"[Title/Abstract]) AND India[Title/Abstract]',
    '(whole exome sequencing[Title/Abstract] OR "WES"[Title/Abstract]) AND India[Title/Abstract]',
]

ALLOWED_HOST = "eutils.ncbi.nlm.nih.gov"


def _cache_path(query: str, retmax: int) -> Path:
    safe = "".join(c if c.isalnum() else "_" for c in query)[:80]
    return CACHE_DIR / f"{safe}_{retmax}.json"


def fetch_pubmed(query: str, retmax: int = 20, api_key: Optional[str] = None, offline: bool = False) -> Dict:
    """Search PubMed and fetch abstracts. Cached; pass offline=True in tests."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = _cache_path(query, retmax)
    if cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        data["from_cache"] = True
        return data
    if offline:
        return {"query": query, "articles": [], "from_cache": False,
                "note": "offline mode and no cache present"}

    params = {"db": "pubmed", "term": query, "retmax": str(retmax), "retmode": "json",
              "sort": "date"}
    if api_key:
        params["api_key"] = api_key
    search_url = f"{EUTILS}/esearch.fcgi?" + urllib.parse.urlencode(params)
    parsed = urllib.parse.urlparse(search_url)
    if parsed.hostname != ALLOWED_HOST:
        raise ValueError("Refusing to fetch from a non-NCBI host")
    with urllib.request.urlopen(search_url, timeout=30) as resp:  # noqa: S310 (validated host)
        search = json.loads(resp.read().decode("utf-8"))
    ids = search.get("esearchresult", {}).get("idlist", [])
    articles: List[dict] = []
    if ids:
        fetch_url = (f"{EUTILS}/efetch.fcgi?" +
                     urllib.parse.urlencode({"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}))
        with urllib.request.urlopen(fetch_url, timeout=60) as resp:  # noqa: S310
            xml = resp.read().decode("utf-8", errors="ignore")
        articles = _parse_xml(xml)
    payload = {"query": query, "retrieved_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "n_articles": len(articles), "articles": articles, "from_cache": False}
    cache.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _parse_xml(xml: str) -> List[dict]:
    out: List[dict] = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return out
    for art in root.findall(".//PubmedArticle"):
        pmid = art.findtext(".//PMID") or ""
        title = art.findtext(".//ArticleTitle") or ""
        journal = art.findtext(".//Journal/Title") or ""
        year = art.findtext(".//JournalIssue/PubDate/Year") or art.findtext(".//PubDate/Year") or ""
        abstract_parts = []
        for ab in art.findall(".//Abstract/AbstractText"):
            label = ab.get("Label")
            text = "".join(ab.itertext())
            abstract_parts.append(f"{label}: {text}" if label else text)
        authors = []
        for a in art.findall(".//Author")[:5]:
            last = a.findtext("LastName") or ""
            init = a.findtext("Initials") or ""
            if last:
                authors.append(f"{last} {init}".strip())
        mesh = [m.findtext("DescriptorName") or "" for m in art.findall(".//MeshHeading")]
        out.append({
            "pmid": pmid, "title": title, "journal": journal, "year": year,
            "authors": authors, "abstract": " ".join(abstract_parts).strip(),
            "mesh_terms": [m for m in mesh if m],
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
        })
    return out


def run_pipeline_queries(queries: Optional[List[str]] = None, retmax: int = 15, offline: bool = False) -> Dict:
    queries = queries or DEFAULT_QUERIES
    results = [fetch_pubmed(q, retmax=retmax, offline=offline) for q in queries]
    all_articles = [a for r in results for a in r["articles"]]
    seen, unique = set(), []
    for a in all_articles:
        if a["pmid"] and a["pmid"] not in seen:
            seen.add(a["pmid"])
            unique.append(a)
    return {"queries": len(queries), "n_total_articles": len(unique), "articles": unique,
            "per_query": [{"query": r["query"], "n": r.get("n_articles", 0), "cached": r["from_cache"]}
                          for r in results]}


if __name__ == "__main__":
    import sys

    offline = "--offline" in sys.argv
    res = run_pipeline_queries(retmax=5, offline=offline)
    print(f"Queries: {res['queries']} | unique articles: {res['n_total_articles']}")
    for pq in res["per_query"]:
        print(f"  [{pq['n']:3d}] cached={pq['cached']} {pq['query'][:70]}")
    for a in res["articles"][:3]:
        print(f"\n  PMID {a['pmid']} ({a['year']}) {a['title'][:90]}")
        print(f"    {a['abstract'][:160]}...")
