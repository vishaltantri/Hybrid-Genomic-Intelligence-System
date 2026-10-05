"""Phase 13: persisted ASHA referrals, follow-up tracking and clinician handoff.

Triage colour is always computed server-side from the submitted answers or transcript; clients cannot set it.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.app import store
from backend.app.models import TriageAnswersIn, TriageTextIn
from backend.app.security import require
from backend.app.services import registry
from ml_services.asha.triage_engine import TRIAGE_ACTIONS

router = APIRouter(prefix="/api/v1/community", tags=["community"])

DUE_DAYS = {"red": 1, "yellow": 3, "green": 14}
OUTCOMES = {"improved": ("closed", False), "unchanged": ("open", False), "worse": ("open", True),
            "visited_facility": ("facility_visited", False), "unreachable": ("lost", True)}


def _due(color: str) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=DUE_DAYS[color])).strftime("%Y-%m-%dT%H:%M:%SZ")


def _view(r: dict) -> dict:
    r = {**r}
    r["action"] = TRIAGE_ACTIONS[r["triage_color"]]
    r["overdue"] = r["status"] in ("open", "facility_visited") and (r["follow_up_due"] or "9") < store._now()
    return r


def _can_see(user: dict, r: dict) -> bool:
    return user["role"] in ("doctor", "admin") or r["created_by"] == user["username"]


def _notify_created(user: dict, r: dict) -> None:
    if r["triage_color"] in ("red", "yellow"):
        store.notify("referral", f"New {r['triage_color']} ASHA referral {r['referral_id']}",
                     f"{r.get('village') or 'Village not documented'}, {r.get('district') or 'District not documented'}",
                     recipient_role="doctor", created_by=user["username"])


def _own(user: dict, rid: str) -> dict:
    r = store.referral_get(rid)
    if not r or not _can_see(user, r):          # same 404 for missing and foreign records: no existence leak
        raise HTTPException(status_code=404, detail="Referral not found")
    return r


@router.post("/referrals/from-answers")
def from_answers(p: TriageAnswersIn, user: dict = Depends(require("referral:write"))):
    patient = {"age": p.age, "state": p.state, "district": p.district, "village": p.village, "asha_id": user["username"]}
    t = registry.triage.triage_answers(p.answers, patient)
    r = store.referral_create(user["username"], t, _due(t["triage_color"]))
    store.audit(user["username"], "referral.create", r["referral_id"], t["triage_color"])
    _notify_created(user, r)
    return _view(r)


@router.post("/referrals/from-text")
def from_text(p: TriageTextIn, user: dict = Depends(require("referral:write"))):
    from ml_services.asha.vocab_corrector import MedicalVocabCorrector
    corrected = MedicalVocabCorrector().correct_text(p.transcript)
    patient = {"age": p.age, "state": p.state, "district": p.district, "village": p.village, "asha_id": user["username"]}
    t = registry.triage.triage_text(corrected["corrected"], patient)
    r = store.referral_create(user["username"], t, _due(t["triage_color"]))
    store.audit(user["username"], "referral.create", r["referral_id"], t["triage_color"])
    _notify_created(user, r)
    return _view(r)


@router.get("/referrals")
def list_referrals(status: Optional[str] = None, color: Optional[str] = None, user: dict = Depends(require("referral:read"))):
    own = None if user["role"] in ("doctor", "admin") else user["username"]
    return [_view(r) for r in store.referral_list(own, status, color)]


@router.get("/summary")
def summary(user: dict = Depends(require("referral:read"))):
    own = None if user["role"] in ("doctor", "admin") else user["username"]
    rows = [_view(r) for r in store.referral_list(own)]
    by_color: Dict[str, int] = {"red": 0, "yellow": 0, "green": 0}
    by_status: Dict[str, int] = {}
    for r in rows:
        by_color[r["triage_color"]] += 1
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    return {"total": len(rows), "by_color": by_color, "by_status": by_status,
            "overdue": sum(1 for r in rows if r["overdue"]), "needs_review": sum(1 for r in rows if r["needs_review"])}


@router.get("/referrals/{rid}")
def get_referral(rid: str, user: dict = Depends(require("referral:read"))):
    return _view(_own(user, rid))


class FollowUpIn(BaseModel):
    outcome: str
    note: str = Field(default="", max_length=1000)


@router.post("/referrals/{rid}/followup")
def follow_up(rid: str, p: FollowUpIn, user: dict = Depends(require("referral:read"))):
    r = _own(user, rid)
    if user["role"] not in ("doctor", "admin", "asha"):
        raise HTTPException(status_code=403, detail="Not permitted")
    if p.outcome not in OUTCOMES:
        raise HTTPException(status_code=422, detail=f"Outcome must be one of {sorted(OUTCOMES)}.")
    if r["status"] in ("closed", "handed_off"):
        raise HTTPException(status_code=409, detail=f"Referral is already {r['status']}.")
    status, review = OUTCOMES[p.outcome]
    store.referral_followup(rid, user["username"], p.outcome, p.note.strip(), status, review)
    if p.outcome == "unchanged":
        with store._connect() as conn:
            conn.execute("UPDATE referrals SET follow_up_due=? WHERE referral_id=?", (_due("yellow"), rid))
    store.audit(user["username"], "referral.followup", rid, p.outcome)
    return _view(store.referral_get(rid))


class HandoffIn(BaseModel):
    confirm_hpo_ids: list[str] = []
    sex: Optional[str] = None


@router.post("/referrals/{rid}/handoff")
def handoff(rid: str, p: HandoffIn, user: dict = Depends(require("referral:handoff"))):
    r = store.referral_get(rid)
    if not r:
        raise HTTPException(status_code=404, detail="Referral not found")
    if r["case_id"]:
        raise HTTPException(status_code=409, detail=f"Already handed off as case {r['case_id']}.")
    t = r["triage"]
    unknown = [h for h in p.confirm_hpo_ids if h not in (t.get("hpo_ids") or [])]
    if unknown:
        raise HTTPException(status_code=422, detail=f"HPO terms not reported in this referral: {', '.join(unknown)}")
    case = store.create_patient({"age_years": r["age"], "sex": p.sex, "state": r["state"], "district": r["district"]}, user["username"])
    pid = case["patient_id"]
    store.add_event(pid, "asha_referral", {"referral_id": rid, "triage_color": r["triage_color"], "reported_symptoms": t.get("reported_symptoms"),
                                           "red_flags": t.get("red_flags"), "village": r["village"], "asha_id": r["created_by"],
                                           "note": "ASHA-reported symptoms; not clinician-confirmed phenotypes."})
    confirmed = 0
    if p.confirm_hpo_ids:
        confirmed = registry.phenotype.import_confirm(pid, user["username"], [{"hpo_id": h, "assertion": "present"} for h in p.confirm_hpo_ids])["present"]
    store.referral_handoff(rid, pid, user["username"])
    store.audit(user["username"], "referral.handoff", rid, pid)
    store.notify("handoff", f"Referral {rid} was taken over by a clinician", f"Case {pid} created.", pid, recipient=r["created_by"], created_by=user["username"])
    return {"referral": _view(store.referral_get(rid)), "case_id": pid, "phenotypes_confirmed": confirmed}
