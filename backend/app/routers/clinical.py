"""Module 1/2 endpoints + patient records."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from backend.app import store
from backend.app.models import ClinicalNoteIn, HpoProfileOut, PatientCreate, PatientOut
from backend.app.security import current_user, require
from backend.app.services import registry

router = APIRouter(prefix="/api/v1", tags=["clinical"])


@router.get("/reference")
def reference_data(user: dict = Depends(require("clinical:read"))):
    """Dropdown data for the frontends: Indian states (with consanguinity rates)
    and communities with documented founder risks. Keeps UI selects consistent
    with the graph's canonical ids so population priors always fire."""
    graph = registry.graph
    states = sorted(
        ({"id": s["id"], "name": s.get("name") or s["id"],
          "consanguinity_rate": s.get("consanguinity_rate")}
         for s in graph.by_type("State")),
        key=lambda x: x["name"])
    communities = sorted(
        ({"id": e["id"], "name": e.get("name") or e["id"],
          "founder_disease": e.get("founder_disease_id")}
         for e in graph.by_type("Ethnicity")),
        key=lambda x: x["name"])
    return {"states": states, "communities": communities}


@router.post("/patients", response_model=PatientOut)
def create_patient(payload: PatientCreate, user: dict = Depends(require("clinical:write"))):
    created = store.create_patient(payload.model_dump(), user["username"])
    return PatientOut(**{k: created.get(k) for k in PatientOut.model_fields if k != "demo"})


@router.get("/patients", response_model=List[PatientOut])
def list_patients(response: Response, state: Optional[str] = Query(default=None, max_length=80),
                  limit: int = Query(default=50, ge=1, le=500), offset: int = Query(default=0, ge=0, le=1_000_000),
                  user: dict = Depends(require("clinical:read"))):
    response.headers["X-Total-Count"] = str(store.count_patients(state))
    rows = store.list_patients(state=state, limit=limit, offset=offset)
    return [PatientOut(**{k: r.get(k) for k in PatientOut.model_fields if k != "demo"}, demo=bool((r.get("extra") or {}).get("demo"))) for r in rows]


@router.get("/patients/{patient_id}")
def get_patient(patient_id: str, user: dict = Depends(require("clinical:read"))):
    patient = store.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="patient not found")
    if user["role"] == "patient" and patient.get("created_by") != user["username"]:
        raise HTTPException(status_code=403, detail="patients may only read their own record")
    events = store.list_events(patient_id)
    return {"patient": patient, "events": events}


@router.post("/clinical/extract")
def extract_entities(payload: ClinicalNoteIn, user: dict = Depends(require("clinical:write"))):
    """Module 1: token-level NER + language ID over a clinical note."""
    result = registry.ner.extract(payload.text)
    store.add_event_for_case(payload.patient_id, "clinical_note", {"text": payload.text, "entities": result["entities"]})
    store.audit(user["username"], "clinical.extract", payload.patient_id or "", f"{len(payload.text)} chars, {len(result['entities'])} entities")   # never log note text
    return result


@router.post("/clinical/hpo-map", response_model=HpoProfileOut)
def hpo_map(payload: ClinicalNoteIn, user: dict = Depends(require("clinical:write"))):
    """Module 2: map clinical text to HPO terms (with low-confidence review flagging)."""
    from ml_services.nlp.llm_symptoms import assisted_profile
    profile = assisted_profile(registry, payload.text)
    store.add_event_for_case(payload.patient_id, "hpo_profile", profile)

    # Feed the active-learning queue when the mapper was unsure (Module 10)
    uncertainty = registry.active_learning.score_uncertainty(
        profile["hpo_profile"], None, profile["unmapped_symptoms"])
    registry.active_learning.enqueue({"text": payload.text, "hpo_profile": profile["hpo_profile"],
                                      "unmapped_symptoms": profile["unmapped_symptoms"],
                                      "uncertainty": uncertainty})
    store.audit(user["username"], "clinical.hpo_map", payload.patient_id or "",
                f"{len(profile['hpo_ids'])} terms")
    return HpoProfileOut(**profile)


@router.get("/clinical/synonyms")
def synonym_dictionary(user: dict = Depends(require("clinical:read")), limit: int = Query(200, le=2000)):
    """The Indian medical synonym dictionary (patent claim #2) as a browsable artifact."""
    from ml_services.config import SEEDS_DIR
    from ml_services.utils import read_csv_rows

    synonyms = read_csv_rows(SEEDS_DIR / "indian_synonyms.csv")
    return {"n_entries": len(synonyms), "entries": synonyms[:limit]}
