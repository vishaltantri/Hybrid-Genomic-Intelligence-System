"""Module 6 endpoints: couple carrier risk, lab report parsing, pedigree, reports."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app import store
from backend.app.models import CoupleRequest, LabReportIn
from backend.app.security import require
from backend.app.services import registry
from ml_services.reproductive import lab_report_parser, pedigree
from ml_services.reproductive.report_generator import generate_carrier_report

router = APIRouter(prefix="/api/v1/reproductive", tags=["reproductive"])


@router.post("/couple-risk")
def couple_risk(payload: CoupleRequest, user: dict = Depends(require("reproductive:counsel"))):
    """Bayesian carrier probability for the top recessive/dominant/X-linked conditions."""
    assessment = registry.counselor.couple_assessment(payload.partner_a.model_dump(),
                                                     payload.partner_b.model_dump(),
                                                     top_n=payload.top_n)
    assessment["report"] = generate_carrier_report(assessment, lang=payload.lang)
    store.audit(user["username"], "reproductive.couple_risk", "",
                f"band={assessment['risk_band']}")
    return assessment


@router.post("/lab-report")
def lab_report(payload: LabReportIn, user: dict = Depends(require("reproductive:read"))):
    """Parse CBC/HPLC/biochemistry/prenatal screening report text and interpret it."""
    parsed = lab_report_parser.parse_text(payload.text)
    store.add_event_for_case(payload.patient_id, "lab_report", parsed)
    store.audit(user["username"], "reproductive.lab_report", payload.patient_id or "",
                f"{parsed['n_values_extracted']} values, {len(parsed['flags'])} flags")
    return parsed


@router.get("/conditions")
def conditions(user: dict = Depends(require("reproductive:read"))):
    """Carrier-frequency table used by the counselor (transparency endpoint)."""
    return {"n_conditions": len(registry.counselor.diseases), "conditions": registry.counselor.diseases}


@router.get("/pedigree/sample")
def pedigree_sample(user: dict = Depends(require("reproductive:read"))):
    fam = {
        "grandparents": [{"id": "G1", "name": "Grandfather", "sex": "M"},
                         {"id": "G2", "name": "Grandmother", "sex": "F"}],
        "parents": [{"id": "P1", "name": "Father", "sex": "M"},
                    {"id": "P2", "name": "Mother", "sex": "F", "carrier": True}],
        "children": [{"id": "C1", "name": "Patient", "sex": "M", "affected": True},
                     {"id": "C2", "name": "Sister", "sex": "F"}],
    }
    return pedigree.build_pedigree(fam, "Beta-thalassemia", consanguineous=False)
