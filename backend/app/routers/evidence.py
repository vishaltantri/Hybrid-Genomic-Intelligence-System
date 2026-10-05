"""Genomera Clinical Evidence & Literature API (Phase 4).

  GET    /api/v1/evidence/sources                       configured evidence sources and their honest status
  GET    /api/v1/evidence/search?q=&kind=&gene=&...     PubMed search (NCBI E-utilities), normalised + ranked
  GET    /api/v1/evidence/pmid/{pmid}                   one PubMed record
  GET    /api/v1/evidence/variant/{analysis_id}?variant_id=   ClinVar + Orphanet + PubMed evidence for a variant
  GET    /api/v1/evidence/case/{case_id}                saved evidence for a case
  POST   /api/v1/evidence/case/{case_id}                save an evidence record to a case (optionally add to report)
  PATCH  /api/v1/evidence/case/{case_id}/{evidence_id}  edit note / report flag
  DELETE /api/v1/evidence/case/{case_id}/{evidence_id}
  GET    /api/v1/evidence/case/{case_id}/report         evidence section for the clinical report
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app import store
from backend.app.security import require
from backend.app.services import registry
from ml_services.evidence.service import EvidenceError

router = APIRouter(prefix="/api/v1/evidence", tags=["evidence"])

_RATE = defaultdict(deque)
RATE_LIMIT = 30          # searches per user per minute (NCBI is shared infrastructure)


def _limit(user: dict) -> None:
    q, now = _RATE[user["username"]], time.monotonic()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many literature searches; wait a minute and retry")
    q.append(now)


def _run(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except EvidenceError as ex:
        raise HTTPException(status_code=ex.status, detail=str(ex)) from ex


def _case(case_id: str) -> None:
    if not store.get_patient(case_id):
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")


@router.get("/sources")
def sources(user: dict = Depends(require("evidence:read"))):
    return {"sources": registry.evidence.sources()}


@router.get("/search")
def search(q: str = Query(..., max_length=400), kind: str = "auto", gene: Optional[str] = Query(default=None, max_length=20),
           page: int = Query(default=1, ge=1, le=200), size: int = Query(default=10, ge=1, le=25),
           year_from: Optional[int] = Query(default=None, ge=1800, le=2100), year_to: Optional[int] = Query(default=None, ge=1800, le=2100),
           evidence_type: Optional[str] = Query(default=None, max_length=60), analysis_id: Optional[str] = None,
           user: dict = Depends(require("evidence:read"))):
    _limit(user)
    res = _run(registry.evidence.search, q, kind, gene, page, size, year_from, year_to, evidence_type, None, analysis_id)
    store.audit(user["username"], "evidence.search", "", f"kind={res['query'].get('kind')} status={res['status']}")
    return res


@router.get("/pmid/{pmid}")
def by_pmid(pmid: str, user: dict = Depends(require("evidence:read"))):
    _limit(user)
    return _run(registry.evidence.get_by_pmid, pmid)


@router.get("/variant/{analysis_id}")
def variant_evidence(analysis_id: str, variant_id: str = Query(..., max_length=300), page: int = Query(default=1, ge=1, le=50),
                     user: dict = Depends(require("evidence:read"))):
    _limit(user)
    res = _run(registry.evidence.variant_evidence, analysis_id, variant_id, page)
    store.audit(user["username"], "evidence.variant", analysis_id, variant_id[:80])
    return res


class SaveIn(BaseModel):
    record: Dict[str, Any]
    variant_id: Optional[str] = Field(default=None, max_length=300)
    note: str = Field(default="", max_length=2000)
    in_report: bool = False


class PatchIn(BaseModel):
    note: Optional[str] = Field(default=None, max_length=2000)
    in_report: Optional[bool] = None


@router.get("/case/{case_id}")
def case_evidence(case_id: str, user: dict = Depends(require("evidence:read"))):
    _case(case_id)
    return {"case_id": case_id, "items": store.evidence_list(case_id)}


@router.post("/case/{case_id}", status_code=201)
def save_case_evidence(case_id: str, body: SaveIn, user: dict = Depends(require("evidence:write"))):
    _case(case_id)
    rec = _run(registry.evidence.to_save, body.record)
    item = store.evidence_save(case_id, rec, user["username"], body.variant_id, body.note, body.in_report)
    store.audit(user["username"], "evidence.save", case_id, f'{rec["source"]}:{rec.get("pmid") or rec["source_id"]} report={body.in_report}')
    return item


@router.patch("/case/{case_id}/{evidence_id}")
def patch_case_evidence(case_id: str, evidence_id: str, body: PatchIn, user: dict = Depends(require("evidence:write"))):
    _case(case_id)
    item = store.evidence_update(case_id, evidence_id, body.note, body.in_report)
    if not item:
        raise HTTPException(status_code=404, detail="Evidence item not found for this case")
    store.audit(user["username"], "evidence.update", case_id, evidence_id)
    return item


@router.delete("/case/{case_id}/{evidence_id}")
def delete_case_evidence(case_id: str, evidence_id: str, user: dict = Depends(require("evidence:write"))):
    _case(case_id)
    if not store.evidence_delete(case_id, evidence_id):
        raise HTTPException(status_code=404, detail="Evidence item not found for this case")
    store.audit(user["username"], "evidence.delete", case_id, evidence_id)
    return {"status": "deleted", "evidence_id": evidence_id}


@router.get("/case/{case_id}/report")
def report_section(case_id: str, user: dict = Depends(require("evidence:read"))):
    _case(case_id)
    items = [i for i in store.evidence_list(case_id) if i["in_report"]]
    section = {"case_id": case_id, "title": "Supporting evidence and literature", "count": len(items),
               "disclaimer": "Literature listed for clinician review; relevance is not certainty. Clinical decision support only.",
               "items": [{"source": i["source"], "identifier": f'PMID:{i["payload"].get("pmid")}' if i["payload"].get("pmid") else i["source_id"],
                          "title": i["payload"].get("title"), "journal": i["payload"].get("journal"),
                          "publication_date": i["payload"].get("publication_date"), "doi": i["payload"].get("doi"),
                          "evidence_type": i["payload"].get("evidence_type"), "variant_id": i["variant_id"] or None,
                          "note": i["note"], "url": i["payload"].get("url"), "retrieved_at": i["payload"].get("retrieved_at")} for i in items]}
    if items:
        store.add_event(case_id, "evidence_report_section", section)
        store.audit(user["username"], "evidence.report", case_id, f"n={len(items)}")
    return section
