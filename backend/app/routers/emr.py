"""Phase 6 endpoints: FHIR R4 / ABDM-compatible EMR integration."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from backend.api.v1 import emr_integration as fhir
from backend.app import store
from backend.app.models import DiagnosisRequest, PgxRequest
from backend.app.security import require
from backend.app.services import registry

router = APIRouter(prefix="/api/v1/emr", tags=["emr-fhir"])


@router.get("/fhir/Patient/{patient_id}")
def fhir_patient(patient_id: str, user: dict = Depends(require("clinical:read"))):
    patient = store.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="patient not found")
    return fhir.to_fhir_patient(patient)


@router.post("/fhir/Observation")
def inbound_observation(observation: dict = Body(...),
                        user: dict = Depends(require("clinical:write"))):
    """Accept a lab Observation from an EMR/LIS and convert it to internal values."""
    values = fhir.parse_fhir_observation(observation)
    from ml_services.reproductive import lab_report_parser

    text = " ".join(f"{k} {v['value']} {v['unit']}" for k, v in values.items())
    interpretation = lab_report_parser.parse_text(text)
    store.audit(user["username"], "emr.observation", "", str(list(values.keys())))
    return {"parsed_values": values, "interpretation": interpretation}


@router.post("/fhir/Bundle/{patient_id}")
def outbound_bundle(patient_id: str,
                    diagnosis_hpo: Optional[List[str]] = Query(default=None,
                                                               description="Repeatable: HPO ids"),
                    text: Optional[str] = Query(default=None, description="Free-text note to map"),
                    drugs: Optional[List[str]] = Query(default=None,
                                                       description="Repeatable: prescribed drugs"),
                    user: dict = Depends(require("clinical:read"))):
    """Build a transaction Bundle (Patient + Observations + Condition + ServiceRequests + DetectedIssues)."""
    patient = store.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="patient not found")

    hpo_profile = None
    if text:
        hpo_profile = registry.hpo_mapper.map_text(text)["hpo_profile"]
    elif diagnosis_hpo:
        hpo_profile = [{"hpo_id": h, "hpo_name": (registry.graph.node("Hpo", h) or {}).get("name", h),
                        "confidence": 1.0, "method": "clinician_entered", "evidence_text": ""}
                       for h in diagnosis_hpo]

    diagnosis = None
    hpo_ids = diagnosis_hpo or ([i["hpo_id"] for i in hpo_profile] if hpo_profile else [])
    if hpo_ids:
        diagnosis = registry.diagnosis.diagnose(
            hpo_ids, {"state": patient.get("state"), "community": patient.get("community"),
                      "sex": patient.get("sex")}, top_k=3, explain=True)

    pgx_alerts = []
    if drugs:
        pgx_alerts = registry.pgx.check_drugs(drugs, state=patient.get("state") or "",
                                              ethnicity="", sex=patient.get("sex") or "")["alerts"]

    bundle = fhir.to_fhir_bundle(patient, hpo_profile, diagnosis, pgx_alerts, recorded_by=user["username"])
    store.audit(user["username"], "emr.bundle", patient_id, f"{len(bundle['entry'])} entries")
    return bundle


@router.get("/fhir/metadata")
def fhir_metadata(user: dict = Depends(require("clinical:read"))):
    """Capability statement fragment so an EMR team knows what this endpoint supports."""
    return {
        "resourceType": "CapabilityStatement",
        "fhirVersion": fhir.FHIR_VERSION,
        "status": "draft",
        "software": {"name": "GENOMIND-INDIA", "version": "0.1.0"},
        "rest": [{
            "mode": "server",
            "resource": [
                {"type": "Patient", "interaction": [{"code": "read"}, {"code": "create"}]},
                {"type": "Observation", "interaction": [{"code": "create"}]},
                {"type": "Condition", "interaction": [{"code": "create"}]},
                {"type": "ServiceRequest", "interaction": [{"code": "create"}]},
                {"type": "DetectedIssue", "interaction": [{"code": "create"}]},
            ],
        }],
        "note": ("NRCeS/ABDM-aligned profiles are targeted (nrces.in/ndhm/fhir/r4); formal validation "
                 "against the NRCeS validator is a Phase 6 task."),
    }
