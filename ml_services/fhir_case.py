"""Phase 12: case FHIR R4 export, structural validation and import preview.

The export is built only from stored case data. Validation is a structural R4 check implemented here (required
elements, value-set codes, reference resolution). It is NOT NRCeS/ABDM profile validation and is reported as such.
"""
from __future__ import annotations

import os
import re
from typing import Dict, List
from uuid import uuid4

from backend.api.v1 import emr_integration as fhir
from backend.app import store

VALIDATION_SCOPE = ("Structural FHIR R4 check only (required elements, codes, reference resolution). "
                    "Not validated against NRCeS or ABDM profiles.")
OBS_STATUS = {"registered", "preliminary", "final", "amended", "corrected", "cancelled", "entered-in-error", "unknown"}
REPORT_STATUS = {"registered", "partial", "preliminary", "final", "amended", "corrected", "appended", "cancelled",
                 "entered-in-error", "unknown"}
BUNDLE_TYPES = {"document", "message", "transaction", "transaction-response", "batch", "batch-response",
                "history", "searchset", "collection"}
GENDERS = {"male", "female", "other", "unknown"}
ID_RE = re.compile(r"^[A-Za-z0-9\-.]{1,64}$")
MAX_ENTRIES = 500


def abdm_status() -> dict:
    configured = bool(os.environ.get("ABDM_CLIENT_ID") and os.environ.get("ABDM_CLIENT_SECRET"))
    return {"connected": False, "configured": configured,
            "note": ("ABDM gateway integration is not implemented in this build; no ABHA verification, consent or "
                     "record-linking calls are made. ABHA numbers are stored and exported as plain identifiers only."),
            "capabilities": {"fhir_export": True, "fhir_import_preview": True, "abha_verification": False,
                             "consent_manager": False, "health_information_exchange": False}}


def _ref(rid: str, rtype: str) -> str:
    return f"{rtype}/{rid}"


def build_case_bundle(registry, pid: str, user: str) -> dict:
    core = registry.twin.load_core(pid)
    patient = fhir.to_fhir_patient(core["patient"])
    pat_ref = f"Patient/{patient['id']}"
    entries: List[dict] = [patient]
    onto = registry.twin.ontology
    for h in core["hpo_ids"]:
        entries.append({"resourceType": "Observation", "id": f"obs-{uuid4().hex[:12]}", "status": "preliminary",
                        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "exam"}]}],
                        "code": {"coding": [{"system": fhir.HPO_SYSTEM, "code": h, "display": onto.name(h) or h}]},
                        "subject": {"reference": pat_ref}, "valueBoolean": True})
    for v in core["variants"]:
        if (v.get("acmg_classification") or "") in ("Benign", "Likely benign"):
            continue
        comps = []
        if v.get("gene_symbol"):
            comps.append({"code": {"text": "gene-studied"}, "valueString": v["gene_symbol"]})
        if v.get("zygosity"):
            comps.append({"code": {"text": "zygosity"}, "valueString": v["zygosity"]})
        if v.get("acmg_classification"):
            comps.append({"code": {"text": "acmg-classification"}, "valueString": v["acmg_classification"]})
        entries.append({"resourceType": "Observation", "id": f"var-{uuid4().hex[:12]}", "status": "preliminary",
                        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "laboratory"}]}],
                        "code": {"text": "Genetic variant"}, "subject": {"reference": pat_ref},
                        "valueString": str(v.get("hgvs") or v.get("variant_id") or "Not documented"), "component": comps})
    ws = registry.diagnosis_intel.workspace(pid)
    if ws.get("available") and ws.get("differential"):
        top = ws["differential"][0]
        entries.append({"resourceType": "Condition", "id": f"cond-{uuid4().hex[:12]}",
                        "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
                        "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "provisional"}]},
                        "code": {"text": top["disease_name"]}, "subject": {"reference": pat_ref},
                        "note": [{"text": "Top-ranked differential from decision support; unconfirmed. Requires clinician review."}]})
    reports = [r for r in store.report_list(pid)]
    final = next((r for r in reports if r["status"] == "final"), None)
    if final:
        entries.append({"resourceType": "DiagnosticReport", "id": f"rpt-{final['report_id'].lower()}"[:64], "status": "final",
                        "code": {"text": "Genomera clinical genomics report"}, "subject": {"reference": pat_ref},
                        "conclusion": f"Report {final['report_id']} version {final['version']} (finalized by {final.get('finalized_by')}). Decision support, not a diagnosis."})
    bundle = {"resourceType": "Bundle", "id": f"bundle-{uuid4().hex[:12]}", "type": "collection", "timestamp": store._now(),
              "entry": [{"fullUrl": f"{e['resourceType']}/{e['id']}", "resource": e} for e in entries]}
    summary = validate_bundle(bundle)
    return {"bundle": bundle, "validation": summary,
            "included": {"phenotypes": len(core["hpo_ids"]), "final_report": bool(final),
                         "diagnosis": bool(ws.get("available") and ws.get("differential"))},
            "notes": [] if final else ["Not included: no finalized report exists for this case."]}


def _req(res: dict, field: str, issues: list, where: str):
    if res.get(field) in (None, "", [], {}):
        issues.append({"severity": "error", "where": where, "message": f"Missing required element '{field}'."})


def _check_resource(res: dict, where: str, issues: list):
    t = res.get("resourceType")
    if not t:
        issues.append({"severity": "error", "where": where, "message": "Missing resourceType."})
        return
    rid = res.get("id")
    if rid is not None and not ID_RE.match(str(rid)):
        issues.append({"severity": "error", "where": where, "message": f"Invalid id '{rid}'."})
    if t == "Patient":
        if res.get("gender") and res["gender"] not in GENDERS:
            issues.append({"severity": "error", "where": where, "message": f"Invalid gender '{res['gender']}'."})
    elif t == "Observation":
        _req(res, "status", issues, where)
        _req(res, "code", issues, where)
        if res.get("status") and res["status"] not in OBS_STATUS:
            issues.append({"severity": "error", "where": where, "message": f"Invalid Observation.status '{res['status']}'."})
        if not res.get("subject"):
            issues.append({"severity": "warning", "where": where, "message": "Observation has no subject."})
    elif t == "Condition":
        _req(res, "subject", issues, where)
        _req(res, "code", issues, where)
    elif t == "DiagnosticReport":
        _req(res, "status", issues, where)
        _req(res, "code", issues, where)
        if res.get("status") and res["status"] not in REPORT_STATUS:
            issues.append({"severity": "error", "where": where, "message": f"Invalid DiagnosticReport.status '{res['status']}'."})


def validate_bundle(bundle: dict) -> dict:
    issues: List[dict] = []
    if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle":
        return {"valid": False, "scope": VALIDATION_SCOPE, "errors": 1, "warnings": 0, "counts": {},
                "issues": [{"severity": "error", "where": "Bundle", "message": "Resource is not a FHIR Bundle."}]}
    if bundle.get("type") not in BUNDLE_TYPES:
        issues.append({"severity": "error", "where": "Bundle", "message": f"Invalid or missing Bundle.type '{bundle.get('type')}'."})
    entries = bundle.get("entry") or []
    if not isinstance(entries, list):
        entries, _ = [], issues.append({"severity": "error", "where": "Bundle", "message": "Bundle.entry must be a list."})
    if len(entries) > MAX_ENTRIES:
        issues.append({"severity": "error", "where": "Bundle", "message": f"Too many entries (limit {MAX_ENTRIES})."})
        entries = entries[:MAX_ENTRIES]
    counts: Dict[str, int] = {}
    known = set()
    resources = []
    for i, e in enumerate(entries):
        res = e.get("resource") if isinstance(e, dict) else None
        where = f"entry[{i}]"
        if not isinstance(res, dict):
            issues.append({"severity": "error", "where": where, "message": "Entry has no resource."})
            continue
        t = res.get("resourceType") or "Unknown"
        counts[t] = counts.get(t, 0) + 1
        _check_resource(res, f"{where} {t}", issues)
        if res.get("id"):
            known.add(f"{t}/{res['id']}")
        if e.get("fullUrl"):
            known.add(e["fullUrl"])
        resources.append((where, t, res))
    for where, t, res in resources:
        for key in ("subject", "patient"):
            r = (res.get(key) or {}).get("reference") if isinstance(res.get(key), dict) else None
            if r and r not in known:
                issues.append({"severity": "error", "where": f"{where} {t}", "message": f"Unresolved reference '{r}'."})
    errors = sum(1 for x in issues if x["severity"] == "error")
    return {"valid": errors == 0, "scope": VALIDATION_SCOPE, "errors": errors,
            "warnings": len(issues) - errors, "counts": counts, "issues": issues[:100]}


def import_preview(bundle: dict) -> dict:
    """Validate an inbound Bundle and show what would be mapped. Nothing is persisted."""
    v = validate_bundle(bundle)
    mapped = {"patient": None, "phenotype_codes": [], "unmapped": []}
    if isinstance(bundle, dict):
        for e in (bundle.get("entry") or [])[:MAX_ENTRIES]:
            r = e.get("resource") if isinstance(e, dict) else None
            if not isinstance(r, dict):
                continue
            t = r.get("resourceType")
            if t == "Patient" and not mapped["patient"]:
                ids = r.get("identifier") or []
                mapped["patient"] = {"id": r.get("id"), "gender": r.get("gender"),
                                     "has_abha_identifier": any("healthid" in (x.get("system") or "") for x in ids if isinstance(x, dict))}
            elif t == "Observation":
                codings = (r.get("code") or {}).get("coding") or []
                hp = [c.get("code") for c in codings if isinstance(c, dict) and c.get("system") == fhir.HPO_SYSTEM and c.get("code")]
                if hp:
                    mapped["phenotype_codes"].extend(hp)
                else:
                    mapped["unmapped"].append("Observation without an HPO code")
            elif t:
                mapped["unmapped"].append(t)
    return {"validation": v, "mapped": mapped, "persisted": False,
            "note": "Preview only. Nothing was written to any case. Import into a case is not supported in this build."}
