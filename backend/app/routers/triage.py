"""Module 9 endpoints: ASHA triage, offline sync, community alerts."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Body, Depends

from backend.app import store
from backend.app.models import TriageAnswersIn, TriageTextIn
from backend.app.security import require
from backend.app.services import registry
from ml_services.asha.community_alerts import CommunityAlertEngine

router = APIRouter(prefix="/api/v1/triage", tags=["asha-triafe"])


@router.get("/questionnaire")
def questionnaire(user: dict = Depends(require("triage:read"))):
    """Voice-guided questionnaire the Flutter app renders offline."""
    return registry.triage.questionnaire


@router.post("/answers")
def triage_answers(payload: TriageAnswersIn, user: dict = Depends(require("triage:write"))):
    patient = {"age": payload.age, "state": payload.state, "district": payload.district,
               "village": payload.village, "asha_id": payload.asha_id or user["username"]}
    result = registry.triage.triage_answers(payload.answers, patient)
    store.add_event(payload.asha_id or user["username"], "triage", result)
    return result


@router.post("/text")
def triage_text(payload: TriageTextIn, user: dict = Depends(require("triage:write"))):
    """ASR transcript -> vocab correction -> NER/HPO -> triage colour."""
    from ml_services.asha.vocab_corrector import MedicalVocabCorrector

    corrected = MedicalVocabCorrector().correct_text(payload.transcript)
    patient = {"age": payload.age, "state": payload.state, "district": payload.district,
               "village": payload.village, "asha_id": payload.asha_id or user["username"]}
    result = registry.triage.triage_text(corrected["corrected"], patient)
    result["vocab_corrections"] = corrected["changes"]
    store.add_event(payload.asha_id or user["username"], "triage_text", result)
    return result


@router.post("/sync")
def sync_offline_records(records: List[dict] = Body(..., description="Batched offline records from the app"),
                         user: dict = Depends(require("sync:write"))):
    """Accept a batch of offline ASHA records and return community alerts for the district."""
    accepted = len(records)
    for r in records:
        store.add_event(r.get("local_id", user["username"]), "asha_sync", r)
    engine = CommunityAlertEngine()
    alerts = engine.scan(records) if records else {"alerts": [], "villages_scanned": 0}
    store.audit(user["username"], "triage.sync", "", f"{accepted} records")
    return {"accepted_records": accepted, "community_alerts": alerts}


@router.get("/alerts/simulated")
def simulated_alerts(user: dict = Depends(require("triage:read"))):
    """Demo path: village-level clustering alerts over simulated ASHA traffic."""
    engine = CommunityAlertEngine()
    records = engine.simulate_village_records(n_villages=30, outbreak_villages=2)
    return engine.scan(records)


@router.get("/offline-package")
def offline_package(user: dict = Depends(require("triage:read"))):
    """Everything the app needs to work with no connectivity: questionnaire + triage rules
    + the Indian synonym lexicon + the red-flag list (bundled into the app at build time)."""
    from ml_services.config import SEEDS_DIR
    from ml_services.utils import read_csv_rows

    return {
        "questionnaire": registry.triage.questionnaire,
        "synonyms": read_csv_rows(SEEDS_DIR / "indian_synonyms.csv"),
        "triage_actions": {"green": "monitor", "yellow": "refer_phc", "red": "urgent_referral"},
        "package_version": 1,
        "size_note": "Small enough to embed in the APK; no network required for triage.",
    }
