"""Phase 10: case reproductive genetics workspace."""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app import store
from backend.app.security import require
from backend.app.services import registry
from ml_services.reproductive.workspace import ReproError

router = APIRouter(prefix="/api/v1/repro", tags=["reproductive-workspace"])
_GENO = re.compile(r"^[Aa]{2}$")
_STATUS = "^(carrier|not_carrier|affected|unknown)$"


def _run(fn, *a, **k):
    try:
        return fn(*a, **k)
    except ReproError as ex:
        raise HTTPException(status_code=ex.status, detail=str(ex))
    except LookupError as ex:
        raise HTTPException(status_code=404, detail=str(ex))
    except ValueError as ex:
        raise HTTPException(status_code=422, detail=str(ex))


@router.get("/case/{pid}/members")
def members(pid: str, user: dict = Depends(require("reproductive:read"))):
    return _run(registry.repro.members, pid)


@router.get("/case/{pid}")
def analysis(pid: str, partner_a: Optional[str] = None, partner_b: Optional[str] = None, user: dict = Depends(require("reproductive:read"))):
    try:
        res = registry.repro.analyze(pid, partner_a, partner_b)
    except ReproError as ex:  # missing proband/parents is a state, not a server error
        return {"patient_id": pid, "available": False, "note": f"Insufficient data: {ex}", "risks": [], "partners": []}
    except LookupError as ex:
        raise HTTPException(status_code=404, detail=str(ex))
    store.audit(user["username"], "repro.analysis", pid, f"band={res['risk_band']}")
    return res


class PunnettIn(BaseModel):
    parent_a: str = Field(..., max_length=2)
    parent_b: str = Field(..., max_length=2)


@router.post("/punnett")
def punnett(body: PunnettIn, user: dict = Depends(require("reproductive:read"))):
    if not (_GENO.match(body.parent_a) and _GENO.match(body.parent_b)):
        raise HTTPException(status_code=422, detail="Genotypes must be two alleles made of A (normal) and a (disease), e.g. Aa.")
    return registry.repro.punnett(body.parent_a, body.parent_b)


class MonteCarloIn(BaseModel):
    disease_id: Optional[str] = None
    partner_a: Optional[str] = None
    partner_b: Optional[str] = None
    p_a: Optional[float] = Field(default=None, ge=0, le=1)
    p_b: Optional[float] = Field(default=None, ge=0, le=1)
    inbreeding: float = Field(default=0.0, ge=0, le=0.5)
    n: int = Field(default=20000, ge=1000, le=200000)
    seed: int = 5


@router.post("/case/{pid}/montecarlo")
def montecarlo(pid: str, body: MonteCarloIn, user: dict = Depends(require("reproductive:read"))):
    if body.disease_id:
        return _run(registry.repro.monte_carlo_for_case, pid, body.disease_id, body.partner_a, body.partner_b, body.n, body.seed)
    if body.p_a is None or body.p_b is None:
        raise HTTPException(status_code=422, detail="Provide a condition, or both carrier probabilities p_a and p_b.")
    return _run(registry.repro.monte_carlo, body.p_a, body.p_b, body.n, body.seed, body.inbreeding)


class ScenarioIn(BaseModel):
    disease_id: str
    status_a: str = Field(..., pattern=_STATUS)
    status_b: str = Field(..., pattern=_STATUS)
    partner_a: Optional[str] = None
    partner_b: Optional[str] = None


@router.post("/case/{pid}/scenario")
def scenario(pid: str, body: ScenarioIn, user: dict = Depends(require("reproductive:read"))):
    return _run(registry.repro.scenario, pid, body.disease_id, body.status_a, body.status_b, body.partner_a, body.partner_b)


@router.get("/case/{pid}/explain")
def explain(pid: str, disease_id: str = Query(...), partner_a: Optional[str] = None, partner_b: Optional[str] = None,
            user: dict = Depends(require("reproductive:read"))):
    return _run(registry.repro.explain, pid, disease_id, partner_a, partner_b)


@router.get("/case/{pid}/report-section")
def report_section(pid: str, user: dict = Depends(require("reproductive:read"))):
    return registry.repro.report_section(pid)
