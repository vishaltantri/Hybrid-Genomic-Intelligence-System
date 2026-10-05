"""Genomera Clinical Digital Twin API (Phase 3D).

Endpoints (all authenticated; `twin:read` / `twin:write`, doctor + admin):
- GET    /api/v1/digital-twin/{patient_id}                     Full Twin state with provenance.
- GET    /api/v1/digital-twin/{patient_id}/snapshot            Versioned snapshot (computed, not stored).
- POST   /api/v1/digital-twin/{patient_id}/snapshot            Persist the snapshot for the current user.
- GET    /api/v1/digital-twin/{patient_id}/snapshots           The current user's saved snapshots.
- GET    /api/v1/digital-twin/{patient_id}/timeline            Dated events from stored data.
- POST   /api/v1/digital-twin/{patient_id}/scenarios           Run + persist a what-if scenario.
- GET    /api/v1/digital-twin/{patient_id}/scenarios           The current user's scenario history.
- GET    /api/v1/digital-twin/{patient_id}/scenarios/{id}      One stored scenario result.
- DELETE /api/v1/digital-twin/{patient_id}/scenarios/{id}      Remove one of the user's scenarios.
- POST   /api/v1/digital-twin/{patient_id}/report-handoff      Add snapshot (+ scenarios) to the clinical record.

Scenarios and saved snapshots are scoped to the creating user; other users receive 404.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app import store
from backend.app.security import require
from backend.app.services import registry
from ml_services.twin.scenario_engine import ScenarioError
from ml_services.twin.twin_service import TwinNotFound

router = APIRouter(prefix="/api/v1/digital-twin", tags=["digital-twin"])


class ScenarioIn(BaseModel):
    type: str = Field(description="variant_exclusion | variant_reclassification | phenotype_remove | "
                                  "phenotype_add | diagnosis_focus | medication")
    name: Optional[str] = Field(default=None, max_length=120)
    params: Dict[str, Any] = Field(default_factory=dict)
    analysis_id: Optional[str] = None


class TwinReportIn(BaseModel):
    scenario_ids: List[str] = Field(default_factory=list)
    analysis_id: Optional[str] = None
    clinical_notes: Optional[str] = Field(default=None, max_length=2000)


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except TwinNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ScenarioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{patient_id}")
def get_twin(patient_id: str, analysis_id: Optional[str] = Query(default=None),
             user: dict = Depends(require("twin:read"))):
    twin = _guard(registry.twin.build_twin, patient_id, analysis_id)
    store.audit(user["username"], "twin.view", patient_id, f"snapshot={twin['snapshot']['snapshot_version']}")
    return twin


@router.get("/{patient_id}/snapshot")
def get_snapshot(patient_id: str, analysis_id: Optional[str] = Query(default=None),
                 user: dict = Depends(require("twin:read"))):
    return _guard(registry.twin.build_snapshot, patient_id, analysis_id)


@router.post("/{patient_id}/snapshot")
def save_snapshot(patient_id: str, analysis_id: Optional[str] = Query(default=None),
                  user: dict = Depends(require("twin:write"))):
    snap = _guard(registry.twin.save_snapshot, patient_id, user["username"], analysis_id)
    store.audit(user["username"], "twin.snapshot_save", patient_id, snap["snapshot_version"])
    return snap


@router.get("/{patient_id}/snapshots")
def list_snapshots(patient_id: str, user: dict = Depends(require("twin:read"))):
    if not store.get_patient(patient_id):
        raise HTTPException(status_code=404, detail=f"Patient '{patient_id}' not found")
    return registry.twin.list_snapshots(patient_id, user["username"])


@router.get("/{patient_id}/timeline")
def get_timeline(patient_id: str, user: dict = Depends(require("twin:read"))):
    return _guard(registry.twin.build_timeline, patient_id)


@router.post("/{patient_id}/scenarios")
def create_scenario(patient_id: str, payload: ScenarioIn, user: dict = Depends(require("twin:write"))):
    result = _guard(registry.twin.create_scenario, patient_id, user["username"],
                    {"type": payload.type, "name": payload.name, "params": payload.params}, payload.analysis_id)
    store.audit(user["username"], "twin.scenario", patient_id, f"{result['type']} {result['scenario_id']}")
    return result


@router.get("/{patient_id}/scenarios")
def list_scenarios(patient_id: str, user: dict = Depends(require("twin:read"))):
    if not store.get_patient(patient_id):
        raise HTTPException(status_code=404, detail=f"Patient '{patient_id}' not found")
    return registry.twin.list_scenarios(patient_id, user["username"])


@router.get("/{patient_id}/scenarios/{scenario_id}")
def get_scenario(patient_id: str, scenario_id: str, user: dict = Depends(require("twin:read"))):
    sc = registry.twin.get_scenario(patient_id, user["username"], scenario_id)
    if not sc:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return sc


@router.delete("/{patient_id}/scenarios/{scenario_id}")
def delete_scenario(patient_id: str, scenario_id: str, user: dict = Depends(require("twin:write"))):
    if not registry.twin.delete_scenario(patient_id, user["username"], scenario_id):
        raise HTTPException(status_code=404, detail="Scenario not found")
    return {"status": "deleted", "scenario_id": scenario_id}


@router.post("/{patient_id}/report-handoff")
def report_handoff(patient_id: str, payload: TwinReportIn, user: dict = Depends(require("twin:write"))):
    bundle = _guard(registry.twin.report_handoff, patient_id, user["username"], payload.scenario_ids,
                    payload.analysis_id, payload.clinical_notes or "")
    store.audit(user["username"], "twin.report_handoff", patient_id,
                f"{bundle['snapshot_version']} scenarios={len(bundle['scenarios'])}")
    return bundle
