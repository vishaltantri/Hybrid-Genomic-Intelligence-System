"""Diagnosis Intelligence API (Phase 8). Presentation layer over the existing engine; Clinical Decision Support.

  GET  /api/v1/dx/case/{pid}                    workspace: case summary, differential, supporting/missing, variants, evidence
  GET  /api/v1/dx/case/{pid}/why?disease_id=    why a disease holds its rank (actual engine factors)
  GET  /api/v1/dx/case/{pid}/matrix             differential x phenotype matrix
  GET  /api/v1/dx/case/{pid}/discriminating     which undocumented finding would change the differential (real re-runs)
  POST /api/v1/dx/case/{pid}/whatif             real engine re-run through the Twin scenario engine
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app import store
from backend.app.security import require
from backend.app.services import registry
from ml_services.diagnosis_intel.service import DiagnosisIntelError
from ml_services.twin.twin_service import TwinNotFound

router = APIRouter(prefix="/api/v1/dx", tags=["diagnosis-intelligence"])


class WhatIfIn(BaseModel):
    type: str = Field(..., pattern="^(phenotype_add|phenotype_remove|variant_exclusion|variant_reclassification|diagnosis_focus)$")
    name: Optional[str] = Field(None, max_length=80)
    params: dict = Field(default_factory=dict)


def _run(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except DiagnosisIntelError as ex:
        raise HTTPException(status_code=422, detail=str(ex))
    except (LookupError, TwinNotFound) as ex:
        raise HTTPException(status_code=404, detail=str(ex))


def _audited(user: dict, action: str, pid: str):
    store.audit(user.get("sub") or user.get("username") or "unknown", action, pid, "")


@router.get("/case/{patient_id}")
def workspace(patient_id: str, user: dict = Depends(require("diagnosis:run"))):
    out = _run(registry.diagnosis_intel.workspace, patient_id)
    _audited(user, "dx_workspace_view", patient_id)
    return out


class ConfirmIn(BaseModel):
    disease_id: str = Field(..., max_length=64)
    note: Optional[str] = Field(None, max_length=500)


@router.post("/case/{patient_id}/confirm")
def confirm_diagnosis(patient_id: str, body: ConfirmIn, user: dict = Depends(require("diagnosis:confirm"))):
    """A clinician records that THEY confirm this diagnosis for the case. The model ranking itself never becomes a diagnosis."""
    if not store.get_patient(patient_id):
        raise HTTPException(status_code=404, detail=f"Patient '{patient_id}' not found")
    node = registry.graph.node("Disease", body.disease_id)
    if not node:
        raise HTTPException(status_code=422, detail=f"Disease '{body.disease_id}' is not in the knowledge graph")
    who = user.get("sub") or user.get("username")
    ws = registry.diagnosis_intel.workspace(patient_id)
    rank = next((d["rank"] for d in ws.get("differential", []) if d["disease_id"] == body.disease_id), None)
    ev = store.add_event(patient_id, "diagnosis_confirmation", {
        "disease_id": body.disease_id, "disease_name": node.get("name"), "confirmed_by": who, "note": body.note,
        "model_rank_at_confirmation": rank, "model": "resnik-bayes-deterministic"})
    store.audit(who, "dx_confirm", patient_id, f"{body.disease_id} rank={rank}")
    return {"event_id": ev["event_id"], "patient_id": patient_id, "disease_id": body.disease_id, "disease_name": node.get("name"),
            "confirmed_by": who, "confirmed_utc": ev["created_utc"], "model_rank_at_confirmation": rank}


@router.get("/case/{patient_id}/why")
def why(patient_id: str, disease_id: str = Query(..., max_length=64), user: dict = Depends(require("diagnosis:run"))):
    return _run(registry.diagnosis_intel.why, patient_id, disease_id)


@router.get("/case/{patient_id}/matrix")
def matrix(patient_id: str, user: dict = Depends(require("diagnosis:run"))):
    return _run(registry.diagnosis_intel.matrix, patient_id)


@router.get("/case/{patient_id}/discriminating")
def discriminating(patient_id: str, user: dict = Depends(require("diagnosis:run"))):
    return _run(registry.diagnosis_intel.discriminating, patient_id)


@router.post("/case/{patient_id}/whatif")
def whatif(patient_id: str, body: WhatIfIn, user: dict = Depends(require("twin:write"))):
    who = user.get("sub") or user.get("username") or "unknown"
    out = _run(registry.diagnosis_intel.whatif, patient_id, who, body.model_dump())
    _audited(user, "dx_whatif", patient_id)
    return out
