"""Phase 27 data quality and provenance API.

  GET /api/v1/quality/case/{pid}      conflicts, staleness, missing-data states, identifier checks
  GET /api/v1/quality/provenance/{pid} per-domain source labels (patient/lab/model/calculated...) and data/model versions
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.app.security import require
from backend.app.services import registry
from ml_services.quality import service as q

router = APIRouter(prefix="/api/v1/quality", tags=["data-quality"])


def _run(fn, pid):
    try:
        return fn(registry, pid)
    except LookupError as ex:
        raise HTTPException(status_code=404, detail=str(ex))


@router.get("/case/{pid}")
def case_quality(pid: str, user: dict = Depends(require("clinical:read"))):
    return _run(q.quality, pid)


@router.get("/provenance/{pid}")
def case_provenance(pid: str, user: dict = Depends(require("clinical:read"))):
    return _run(q.provenance, pid)
