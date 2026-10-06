"""Phase 24 demo mode. One synthetic, internally consistent case per user, built with the real services.

The case is a normal patient record flagged `demo` (and `synthetic`) in its payload. Every module reads it through its
ordinary code path, so nothing in the demo is canned: phenotypes go through `phenotype.import_confirm`, the VCF through
`variants.analyze_vcf`, the family through `pedigree.demo_family`, and diagnosis/PGx/reproductive/twin/report are computed
from those stored records on request. Reset removes only demo cases owned by the caller (admin: every demo case) and
never touches audit history or non-demo data.
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional

from backend.app import store

BANNER = "Sample record - not a real patient"
NOTICE = ("This is a sample case created by Genomera. It is not a real patient and nothing here is a "
          "clinical finding. Do not use it for care decisions.")
PREFIX = "CASE-"
LEGACY_PREFIXES = ("DEMO-",)          # cases created before the rename are still recognised, reset and protected
PHENOTYPES = ("HP:0001337", "HP:0000952", "HP:0002240", "HP:0001394")          # tremor, jaundice, hepatomegaly, cirrhosis
PROFILE = {"age_years": 11, "sex": "F", "state": "Andhra Pradesh", "community": "Reddy", "consanguineous": True}


class DemoError(RuntimeError):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def case_id_for(username: str) -> str:
    return PREFIX + (re.sub(r"[^A-Za-z0-9]", "", username).upper()[:12] or "USER")


def is_demo(patient: Optional[dict]) -> bool:
    return bool(patient and (patient.get("extra") or {}).get("demo") is True and str(patient.get("patient_id", "")).startswith((PREFIX,) + LEGACY_PREFIXES))


def _count(table: str, col: str, pid: str) -> int:
    with store._connect() as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = ?", (pid,)).fetchone()[0]


def enabled() -> bool:
    """Demo mode writes synthetic records into the database, so production deployments must opt in explicitly."""
    from backend.app import hardening
    return (not hardening.is_production()) or os.environ.get("GENOMERA_ENABLE_DEMO", "") == "1"


def status(registry, user: dict) -> dict:
    pid = case_id_for(user["username"])
    if not enabled():
        return {"banner": BANNER, "notice": NOTICE, "case_id": pid, "exists": False, "steps": [], "enabled": False,
                "reason": "Demo mode is disabled in this deployment (set GENOMERA_ENABLE_DEMO=1 to allow it)."}
    p = store.get_patient(pid)
    base = {"banner": BANNER, "notice": NOTICE, "case_id": pid, "exists": False, "steps": []}
    if not is_demo(p) or (p.get("created_by") != user["username"] and user.get("role") != "admin"):
        return base
    core = registry.twin.load_core(pid)
    analyses = [a for a in registry.variants.list_analyses() if a.get("patient_id") == pid]
    reports = _count("case_reports", "case_id", pid)
    ped = _count("pedigree_members", "case_id", pid)
    n_var = sum((a.get("qc_metrics") or {}).get("total_variants", 0) for a in analyses)
    base["exists"] = True
    base["steps"] = [
        {"id": "patient", "label": "Explore patient", "route": "patients", "done": True, "detail": "Sample patient record"},
        {"id": "phenotypes", "label": "Review phenotypes", "route": "phenotypes", "done": len(core["hpo_ids"]) > 0, "detail": f"{len(core['hpo_ids'])} HPO terms"},
        {"id": "variants", "label": "Analyze variants", "route": "variants", "done": bool(analyses), "detail": f"{len(analyses)} analysis, {n_var} variants"},
        {"id": "evidence", "label": "View evidence", "route": "evidence", "done": bool(analyses), "detail": "Literature and database evidence for the variants"},
        {"id": "diagnosis", "label": "Review differential diagnosis", "route": "dx-intel", "done": len(core["hpo_ids"]) > 0, "detail": "Ranked from the recorded phenotypes"},
        {"id": "pedigree", "label": "Open pedigree", "route": "pedigree", "done": ped > 0, "detail": f"{ped} family members"},
        {"id": "digital-twin", "label": "Open Digital Twin", "route": "digital-twin", "done": True, "detail": "Built from the case data"},
        {"id": "pgx", "label": "Review pharmacogenomics", "route": "pgx", "done": bool(analyses), "detail": "From the pharmacogene variants in the VCF"},
        {"id": "repro", "label": "Review reproductive genetics", "route": "repro", "done": ped > 0, "detail": "Uses the family structure"},
        {"id": "reports", "label": "Generate report", "route": "reports", "done": reports > 0, "detail": f"{reports} report version(s)"},
    ]
    return base


def seed(registry, user: dict) -> dict:
    if not enabled():
        raise DemoError("Demo mode is disabled in this deployment.", 403)
    pid = case_id_for(user["username"])
    existing = store.get_patient(pid)
    if existing:
        if not is_demo(existing) or existing.get("created_by") != user["username"]:
            raise DemoError("A real record already uses this sample case id; it was left untouched.", 409)
        return {**status(registry, user), "created": False}
    onto = registry.twin.ontology
    items = [{"hpo_id": h, "assertion": "present"} for h in PHENOTYPES if onto.name(h)]
    if not items:
        raise DemoError("The phenotype ontology is not available, so the demo case cannot be built.", 503)
    store.create_patient({"patient_id": pid, **PROFILE, "demo": True, "synthetic": True, "demo_notice": NOTICE}, user["username"])
    try:
        registry.phenotype.import_confirm(pid, user["username"], items)
        from ml_services.config import SEEDS_DIR
        text = (SEEDS_DIR / "demo_wilson_trio.vcf").read_text(encoding="utf-8")
        a = registry.variants.analyze_vcf(vcf_content=text.encode("utf-8"), filename="family_trio.vcf", patient_id=pid,
                                          patient_hpo_ids=[i["hpo_id"] for i in items], created_by=user["username"])
        store.add_event(pid, "vcf_analysis", {"analysis_id": a["analysis_id"], "filename": "family_trio.vcf", "qc_metrics": a["qc_metrics"], "synthetic": True})
        registry.pedigree.demo_family(pid, user["username"])
    except Exception:
        _remove(registry, pid)                      # never leave a half-built demo case behind
        raise
    store.audit(user["username"], "demo.seed", pid, "synthetic case created")
    return {**status(registry, user), "created": True}


_TABLES = (("clinical_events", "patient_id"), ("twin_records", "patient_id"), ("case_evidence", "case_id"), ("case_reports", "case_id"),
           ("case_workflow", "case_id"), ("workflow_history", "case_id"), ("notifications", "case_id"), ("referrals", "case_id"),
           ("pedigree_genotypes", "case_id"), ("pedigree_relationships", "case_id"), ("pedigree_variants", "case_id"),
           ("pedigree_members", "case_id"), ("variant_analyses", "patient_id"), ("patients", "patient_id"))


def _remove(registry, pid: str) -> Dict[str, int]:
    removed: Dict[str, int] = {}
    for a in [a for a in registry.variants.list_analyses() if a.get("patient_id") == pid]:
        registry.variants._analyses.pop(a["analysis_id"], None)
    with store.transaction() as conn:
        for table, col in _TABLES:
            if not conn.execute(f"PRAGMA table_info({table})").fetchall():
                continue                              # a table absent in an older database has nothing to remove
            if table == "referrals":
                conn.execute(f"DELETE FROM referral_followups WHERE referral_id IN (SELECT referral_id FROM referrals WHERE {col} = ?)", (pid,))
            cur = conn.execute(f"DELETE FROM {table} WHERE {col} = ?", (pid,))
            if cur.rowcount:
                removed[table] = cur.rowcount
    return removed


def reset(registry, user: dict) -> dict:
    """Delete demo cases owned by the caller (admin: all). A record is removed only if it is flagged demo AND has the DEMO- id."""
    with store._connect() as conn:
        rows = conn.execute("SELECT patient_id FROM patients WHERE " + " OR ".join(["patient_id LIKE ?"] * (1 + len(LEGACY_PREFIXES))),
                            tuple(p + "%" for p in (PREFIX,) + LEGACY_PREFIXES)).fetchall()
    removed: Dict[str, int] = {}
    cases: List[str] = []
    for r in rows:
        p = store.get_patient(r[0])
        if not is_demo(p):
            continue
        if user.get("role") != "admin" and p.get("created_by") != user["username"]:
            continue
        for k, v in _remove(registry, p["patient_id"]).items():
            removed[k] = removed.get(k, 0) + v
        cases.append(p["patient_id"])
    store.audit(user["username"], "demo.reset", ",".join(cases)[:90], f"removed={sum(removed.values())}")
    return {"reset": True, "cases_removed": cases, "rows_removed": removed}
