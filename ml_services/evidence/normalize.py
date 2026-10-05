"""Normalised evidence records, PubMed XML parsing, entity-mention detection and relevance ranking."""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from typing import Iterable, List, Optional

# PubMed publication type -> (evidence_type, design tier). The tier is a *study-design indicator taken from the
# PubMed publication-type tag*; it is not a quality grading and never a statement of certainty.
PUBTYPE_MAP = {
    "Meta-Analysis": ("Meta-analysis", "Synthesis"),
    "Systematic Review": ("Systematic review", "Synthesis"),
    "Randomized Controlled Trial": ("Randomized controlled trial", "Interventional study"),
    "Clinical Trial": ("Clinical trial", "Interventional study"),
    "Practice Guideline": ("Practice guideline", "Guideline"),
    "Guideline": ("Guideline", "Guideline"),
    "Observational Study": ("Observational study", "Observational study"),
    "Cohort Studies": ("Cohort study", "Observational study"),
    "Case-Control Studies": ("Case-control study", "Observational study"),
    "Case Reports": ("Case report", "Case-level report"),
    "Review": ("Review", "Narrative review"),
    "Comparative Study": ("Comparative study", "Observational study"),
    "Multicenter Study": ("Multicenter study", "Observational study"),
}
_TIER_ORDER = ["Synthesis", "Guideline", "Interventional study", "Observational study", "Case-level report", "Narrative review"]
_RELEVANCE_TYPE_WEIGHT = {"Synthesis": 1.0, "Guideline": 1.0, "Interventional study": 0.8, "Observational study": 0.6,
                          "Case-level report": 0.45, "Narrative review": 0.5}

HGVS_C = re.compile(r"\b(?:NM_\d+\.\d+:)?c\.[\d_+\-*]+(?:[ACGT]>[ACGT]|del[ACGT]*|ins[ACGT]+|dup[ACGT]*|delins[ACGT]+)", re.I)
HGVS_P = re.compile(r"\bp\.(?:[A-Z][a-z]{2}|[A-Z])\d+(?:[A-Z][a-z]{2}|[A-Z]|\*|fs(?:\*\d+|Ter\d+)?|del|dup)\b")
RSID = re.compile(r"\brs\d{3,12}\b", re.I)
TRANSCRIPT = re.compile(r"\b(?:NM|NR|ENST)_?\d+(?:\.\d+)?\b")
PMID_RE = re.compile(r"^\s*(?:PMID:?\s*)?(\d{1,9})\s*$", re.I)


def new_record(**kw) -> dict:
    rec = {"source": "", "source_id": "", "title": "", "authors": [], "journal": "", "publication_date": "",
           "pmid": None, "doi": None, "gene": [], "variant": [], "disease": [], "phenotype": [],
           "evidence_type": None, "evidence_strength": None, "summary": "", "url": "",
           "retrieved_at": "", "provenance": {}}
    rec.update(kw)
    return rec


def _text(el: Optional[ET.Element]) -> str:
    return "".join(el.itertext()).strip() if el is not None else ""


def _pub_date(art: ET.Element) -> str:
    d = art.find(".//Journal/JournalIssue/PubDate")
    if d is not None:
        y, m, dd = _text(d.find("Year")), _text(d.find("Month")), _text(d.find("Day"))
        if y:
            return "-".join(p for p in (y, m, dd) if p)
        medline = _text(d.find("MedlineDate"))
        if medline:
            return medline
    return _text(art.find(".//ArticleDate/Year"))


def parse_pubmed_xml(xml: str, retrieved_at: Optional[str] = None, query: str = "") -> List[dict]:
    """Parse efetch XML into normalised evidence records. Unparseable input yields an empty list."""
    if not xml.strip():
        return []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    stamp = retrieved_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    out: List[dict] = []
    for art in root.findall(".//PubmedArticle"):
        pmid = _text(art.find("./MedlineCitation/PMID"))
        if not pmid:
            continue
        parts = []
        for ab in art.findall(".//Abstract/AbstractText"):
            label = ab.get("Label")
            t = _text(ab)
            if t:
                parts.append(f"{label}: {t}" if label else t)
        authors = []
        for a in art.findall(".//AuthorList/Author"):
            last, init = _text(a.find("LastName")), _text(a.find("Initials"))
            coll = _text(a.find("CollectiveName"))
            if last:
                authors.append(f"{last} {init}".strip())
            elif coll:
                authors.append(coll)
        doi = None
        for aid in art.findall(".//PubmedData/ArticleIdList/ArticleId"):
            if aid.get("IdType") == "doi":
                doi = _text(aid)
        if doi is None:
            for el in art.findall(".//Article/ELocationID"):
                if el.get("EIdType") == "doi":
                    doi = _text(el)
        pubtypes = [_text(p) for p in art.findall(".//PublicationTypeList/PublicationType")]
        mapped = [PUBTYPE_MAP[p] for p in pubtypes if p in PUBTYPE_MAP]
        etype, tier = (None, None)
        if mapped:
            etype, tier = sorted(mapped, key=lambda m: _TIER_ORDER.index(m[1]))[0]
        mesh = [_text(m.find("DescriptorName")) for m in art.findall(".//MeshHeadingList/MeshHeading")]
        out.append(new_record(
            source="PubMed", source_id=pmid, pmid=pmid, doi=doi,
            title=_text(art.find(".//ArticleTitle")), authors=authors[:12],
            journal=_text(art.find(".//Journal/Title")), publication_date=_pub_date(art),
            evidence_type=etype, evidence_strength=tier,
            summary=" ".join(parts), url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", retrieved_at=stamp,
            provenance={"database": "PubMed (NCBI E-utilities efetch)", "query": query, "retrieved_at": stamp,
                        "publication_types": pubtypes, "mesh_terms": [m for m in mesh if m][:15],
                        "strength_basis": ("PubMed publication-type tag (study design indicator, not a quality grade)"
                                           if tier else "No recognised publication-type tag; design not classified"),
                        "abstract_available": bool(parts)},
        ))
    return out


# ---------------------------- mention detection ----------------------------

def detect_mentions(text: str, known_genes: Iterable[str] = ()) -> dict:
    genes = set(known_genes)
    found = sorted({m for m in re.findall(r"\b[A-Z][A-Z0-9]{1,9}\b", text) if m in genes})
    return {
        "genes": found,
        "hgvs_c": sorted({m.group(0) for m in HGVS_C.finditer(text)})[:20],
        "hgvs_p": sorted({m.group(0) for m in HGVS_P.finditer(text)})[:20],
        "rsids": sorted({m.group(0).lower() for m in RSID.finditer(text)})[:20],
        "transcripts": sorted({m.group(0) for m in TRANSCRIPT.finditer(text)})[:10],
    }


def _norm_hgvs(s: str) -> str:
    return re.sub(r"^NM_\d+\.\d+:", "", s or "").strip().lower()


def link_to_variants(mentions: dict, variants: List[dict]) -> List[dict]:
    """Link a paper to a case variant only when unambiguous: the variant's cDNA/protein/rsID is mentioned and, for
    cDNA/protein matches, that gene is mentioned too. A shared gene alone is *not* a variant link."""
    links = []
    c_set = {_norm_hgvs(x) for x in mentions["hgvs_c"]}
    p_set = {x.lower() for x in mentions["hgvs_p"]}
    rs_set = set(mentions["rsids"])
    for v in variants:
        gene = v.get("gene")
        basis, rs_basis = [], []
        cdna = _norm_hgvs(v.get("cdna") or "")
        prot = (v.get("protein") or "").lower()
        if cdna and cdna in c_set:
            basis.append(f"cDNA {v.get('cdna')} mentioned")
        if prot and prot in p_set:
            basis.append(f"protein {v.get('protein')} mentioned")
        if v.get("rsid") and v["rsid"].lower() in rs_set:
            rs_basis.append(f"{v['rsid']} mentioned")
        if rs_basis or (basis and (not gene or gene in mentions["genes"])):
            links.append({"variant_id": v.get("variant_id"), "gene": gene, "basis": basis + rs_basis})
    return links


# ------------------------------- ranking -------------------------------

def _year(rec: dict) -> Optional[int]:
    m = re.match(r"(\d{4})", rec.get("publication_date") or "")
    return int(m.group(1)) if m else None


def rank(records: List[dict], terms: List[str], current_year: Optional[int] = None) -> List[dict]:
    """Relevance (0-1), NOT certainty. Components are returned so the score is explainable:
    title match 0.45, abstract match 0.25, design tier 0.2, recency 0.1."""
    cy = current_year or time.gmtime().tm_year
    terms = [t.lower() for t in terms if t and len(t) > 1]
    for r in records:
        title, abstract = r["title"].lower(), r["summary"].lower()
        t_hit = sum(1 for t in terms if t in title) / len(terms) if terms else 0.0
        a_hit = sum(1 for t in terms if t in abstract) / len(terms) if terms else 0.0
        design = _RELEVANCE_TYPE_WEIGHT.get(r.get("evidence_strength") or "", 0.3)
        y = _year(r)
        recency = max(0.0, 1 - (cy - y) / 25) if y else 0.0
        comp = {"title_match": round(0.45 * t_hit, 3), "abstract_match": round(0.25 * a_hit, 3),
                "study_design": round(0.2 * design, 3), "recency": round(0.1 * recency, 3)}
        r["relevance"] = round(sum(comp.values()), 3)
        r["relevance_components"] = comp
        r["relevance_note"] = "Relevance to the query, not certainty or clinical validity"
    return sorted(records, key=lambda r: r["relevance"], reverse=True)
