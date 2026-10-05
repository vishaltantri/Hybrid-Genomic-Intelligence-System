"""Phenotype / HPO intelligence API (Phase 7).

  GET  /api/v1/phenotype/search?q=            id / name / synonym / Hindi / semantic HPO search
  GET  /api/v1/phenotype/term/{hpo_id}        definition, hierarchy, diseases, genes (+ case variants)
  GET  /api/v1/phenotype/case/{pid}           observed / negated / uncertain / not documented
  GET  /api/v1/phenotype/case/{pid}/compare?disease_id=
  POST /api/v1/phenotype/case/{pid}/import    clinician-confirmed phenotype import (writes events, audited)
"""
from __future__ import annotations

import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.security import require
from backend.app.services import registry
from ml_services.phenotype.service import PhenotypeError
from ml_services.twin.twin_service import TwinNotFound

router = APIRouter(prefix="/api/v1/phenotype", tags=["phenotype"])
HPO_RE = r"^HP:\d{7}$"


class ImportItem(BaseModel):
    hpo_id: str = Field(..., pattern=HPO_RE)
    assertion: str = Field(..., pattern="^(present|absent|possible)$")
    evidence_text: Optional[str] = Field(None, max_length=300)
    onset: Optional[str] = Field(None, max_length=60)
    severity: Optional[str] = Field(None, max_length=40)
    confidence: Optional[float] = Field(None, ge=0, le=1)


class ImportIn(BaseModel):
    items: List[ImportItem] = Field(..., min_length=1, max_length=100)


def _run(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except PhenotypeError as ex:
        raise HTTPException(status_code=422, detail=str(ex))
    except (LookupError, TwinNotFound) as ex:
        raise HTTPException(status_code=404, detail=str(ex))


def _who(user: dict) -> str:
    return user.get("sub") or user.get("username") or "unknown"


@router.get("/search")
def search(q: str = Query(..., max_length=200), limit: int = Query(15, ge=1, le=30), user: dict = Depends(require("clinical:read"))):
    return _run(registry.phenotype.search, q, limit)


@router.get("/term/{hpo_id}")
def term(hpo_id: str, patient_id: Optional[str] = Query(None, max_length=64), user: dict = Depends(require("clinical:read"))):
    if not re.match(HPO_RE, hpo_id):
        raise HTTPException(status_code=422, detail="Invalid HPO id")
    return _run(registry.phenotype.term, hpo_id, patient_id)


@router.get("/case/{patient_id}")
def case(patient_id: str, user: dict = Depends(require("clinical:read"))):
    return _run(registry.phenotype.case, patient_id)


@router.get("/case/{patient_id}/compare")
def compare(patient_id: str, disease_id: str = Query(..., max_length=64), user: dict = Depends(require("clinical:read"))):
    return _run(registry.phenotype.compare, patient_id, disease_id)


@router.post("/case/{patient_id}/import")
def import_confirm(patient_id: str, body: ImportIn, user: dict = Depends(require("clinical:write"))):
    return _run(registry.phenotype.import_confirm, patient_id, _who(user), [i.model_dump() for i in body.items])
