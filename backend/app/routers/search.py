"""Phase 15: authorization-aware global search and command palette navigation.

Every category is gated by the caller's role permissions; nothing outside them is queried or returned.
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app import store
from backend.app.hardening import rate_limit
from backend.app.security import ROLE_PERMISSIONS, require
from backend.app.services import registry

router = APIRouter(prefix="/api/v1/search", tags=["search"])

CATEGORIES = ("commands", "cases", "variants", "diseases", "genes", "phenotypes", "reports", "referrals")
PER_CATEGORY = 6
MAX_Q = 80

# (route, label, keywords, permission required)
COMMANDS = [
    ("overview", "Overview", "home dashboard", None),
    ("patients", "Patients", "patient cases list", "clinical:read"),
    ("cases", "Cases", "case workspace", "clinical:read"),
    ("clinical-text", "Clinical Text", "notes extract phenotype", "clinical:read"),
    ("phenotypes", "Phenotypes", "hpo terms", "clinical:read"),
    ("diagnosis", "Diagnosis", "differential ranking", "clinical:read"),
    ("dx-intel", "Diagnosis Intelligence", "explain differential", "clinical:read"),
    ("variants", "Variants", "vcf upload annotate", "variants:read"),
    ("kg", "Knowledge Graph", "graph explorer gene disease", "kg:read"),
    ("pedigree", "Pedigree", "family tree", "clinical:read"),
    ("evidence", "Evidence", "literature citations", "evidence:read"),
    ("pgx", "Pharmacogenomics", "drug gene pgx", "pgx:read"),
    ("repro", "Reproductive", "carrier couple planning", "reproductive:read"),
    ("reports", "Reports", "report pdf workflow", "clinical:read"),
    ("asha", "ASHA Triage", "community referral triage", "triage:*"),
    ("fhir", "FHIR / EMR", "export interoperability abdm", "clinical:read"),
    ("settings", "Settings & Status", "status", None),
]


def _allowed(role: str, perm: Optional[str]) -> bool:
    if perm is None:
        return True
    perms = ROLE_PERMISSIONS.get(role, [])
    return "*" in perms or perm in perms or (perm.endswith(":*") and any(p.startswith(perm[:-1]) for p in perms))


def _hit(kind: str, id_: str, label: str, route: str, sub: str = "", ctx: Optional[dict] = None) -> dict:
    return {"type": kind, "id": id_, "label": label, "sub": sub, "route": route, "context": ctx or {}}


def _safe(fn):
    try:
        return fn()
    except Exception:  # a failing source must not leak details or break the other categories
        return None


@router.get("")
def search(q: str = Query(..., description="At least 2 characters"), types: Optional[str] = None,
           user: dict = Depends(require("search:read")), _rl: None = Depends(rate_limit("search"))):
    q = (q or "").strip()
    if len(q) < 2:
        raise HTTPException(status_code=422, detail="Enter at least 2 characters.")
    if len(q) > MAX_Q:
        raise HTTPException(status_code=422, detail=f"Query is too long (max {MAX_Q} characters).")
    wanted = [t.strip() for t in types.split(",")] if types else list(CATEGORIES)
    bad = [t for t in wanted if t not in CATEGORIES]
    if bad:
        raise HTTPException(status_code=422, detail=f"Unknown search type(s): {', '.join(bad)}.")

    role, ql = user["role"], q.lower()
    out: Dict[str, List[dict]] = {}
    unavailable: List[str] = []
    denied: List[str] = []

    def gate(cat: str, perm: Optional[str]) -> bool:
        if cat not in wanted:
            return False
        if not _allowed(role, perm):
            denied.append(cat)
            return False
        return True

    if gate("commands", None):
        out["commands"] = [_hit("command", r, label, r, "Go to") for r, label, kw, perm in COMMANDS
                           if _allowed(role, perm) and (ql in label.lower() or ql in kw)][:PER_CATEGORY]

    if gate("cases", "clinical:read"):
        pts = _safe(lambda: store.list_patients(limit=500))
        if pts is None:
            unavailable.append("cases")
        else:
            out["cases"] = [_hit("case", p["patient_id"], p["patient_id"], "cases",
                                 " · ".join(str(x) for x in (p.get("state"), p.get("community"), f"{p['age_years']}y" if p.get("age_years") else None) if x),
                                 {"patient_id": p["patient_id"]})
                            for p in pts if any(ql in str(p.get(k) or "").lower() for k in ("patient_id", "state", "community"))][:PER_CATEGORY]

    if gate("variants", "variants:read"):
        def scan():
            hits = []
            for a in registry.variants.list_analyses():
                for v in registry.variants.get_analysis(a["analysis_id"]).get("variants", []):
                    if any(ql in str(v.get(k) or "").lower() for k in ("variant_id", "gene_symbol", "hgvs", "cdna", "protein", "clinvar_id")):
                        hits.append(_hit("variant", v.get("variant_id", ""), v.get("hgvs") or v.get("variant_id", ""), "variants",
                                         f"{v.get('gene_symbol') or 'Gene not documented'} · {v.get('clinical_significance') or 'Not classified'} · case {a['patient_id'] or 'not linked'}",
                                         {"analysis_id": a["analysis_id"], "patient_id": a["patient_id"]}))
                        if len(hits) >= PER_CATEGORY:
                            return hits
            return hits
        res = _safe(scan)
        if res is None:
            unavailable.append("variants")
        else:
            out["variants"] = res

    kg_wanted = [(c, t) for c, t in (("diseases", "Disease"), ("genes", "Gene"), ("phenotypes", "Hpo")) if c in wanted]
    for cat, node_type in kg_wanted:
        if not gate(cat, "kg:read"):
            continue
        res = _safe(lambda: registry.graph_explorer.search(q, types=[node_type], limit=PER_CATEGORY))
        if res is None:
            unavailable.append(cat)
            continue
        route = {"diseases": "diagnosis", "genes": "kg", "phenotypes": "phenotypes"}[cat]
        out[cat] = [_hit(cat[:-1] if cat != "phenotypes" else "phenotype", r["id"], r["label"], route, r["id"], {"node": r["key"], "query": r["label"]})
                    for r in res["results"]]

    if gate("reports", "clinical:read"):
        def rep():
            with store._connect() as conn:
                rows = conn.execute("SELECT report_id, case_id, version, status FROM case_reports "
                                    "WHERE lower(report_id) LIKE ? OR lower(case_id) LIKE ? ORDER BY created_utc DESC LIMIT ?",
                                    (f"%{ql}%", f"%{ql}%", PER_CATEGORY)).fetchall()
            return [_hit("report", r["report_id"], r["report_id"], "reports", f"case {r['case_id']} · v{r['version']} · {r['status']}",
                         {"patient_id": r["case_id"], "report_id": r["report_id"]}) for r in rows]
        res = _safe(rep)
        if res is None:
            unavailable.append("reports")
        else:
            out["reports"] = res

    if gate("referrals", "referral:read"):
        own = None if role in ("doctor", "admin") else user["username"]   # ASHA workers only ever see their own
        refs = _safe(lambda: store.referral_list(created_by=own))
        if refs is None:
            unavailable.append("referrals")
        else:
            out["referrals"] = [_hit("referral", r["referral_id"], r["referral_id"], "asha",
                                     f"{r['triage_color']} · {r.get('village') or 'Village not documented'} · {r['status']}", {"referral_id": r["referral_id"]})
                                for r in refs if any(ql in str(r.get(k) or "").lower() for k in ("referral_id", "village", "district", "case_id"))][:PER_CATEGORY]

    total = sum(len(v) for v in out.values())
    store.audit(user["username"], "search.query", "search", json.dumps({"len": len(q), "types": wanted, "results": total}))
    return {"query": q, "total": total, "results": out, "unavailable": unavailable, "not_permitted": denied,
            "state": "No matching result" if total == 0 and not unavailable else ("results" if total else "Not available")}
