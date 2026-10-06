"""Phase 27: data provenance, versions, conflicts and staleness for one case. Nothing here invents data: every item is derived
from stored records, and a domain with no record reports an explicit "Not provided / Not analyzed" state."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict, List, Optional

from backend.app import store
from ml_services.config import PROCESSED_DIR, SEEDS_DIR

# Source taxonomy shown to users. A label states how a value came to exist; it is never upgraded (a model output is never
# presented as laboratory-derived).
PATIENT = "Patient-provided"
CLINICIAN = "Clinician-entered"
LAB = "Laboratory-derived (uploaded VCF)"
DATABASE = "Database-derived"
LITERATURE = "Literature-derived"
MODEL = "Model-generated"
CALCULATED = "Calculated"
IMPORTED = "Imported"
SYNTHETIC = "Synthetic demonstration data"

MODEL_VERSIONS = {"diagnosis_engine": "resnik-bayes-deterministic", "variant_prioritizer": "acmg-composite", "gnn_reranker": "disabled (default)"}


def _sha(path: Path, n: int = 12) -> Optional[str]:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:n]
    except OSError:
        return None


def versions(registry) -> dict:
    """Identifiers of the data and logic behind a result, read from the running system."""
    from backend.app import migrations
    st = registry.status()
    return {"application": "GENOMERA 0.1.0",
            "knowledge_graph": {"nodes": st["graph_nodes"], "edges": st["graph_edges"], "sha256_12": _sha(PROCESSED_DIR / "kg.json")},
            "hpo_ontology": {"source_file": "hp_mini.obo", "sha256_12": _sha(SEEDS_DIR / "hp_mini.obo")},
            "models": MODEL_VERSIONS, "schema_version": migrations.MIGRATIONS[-1][0]}


def _dom(label, source, **kw) -> dict:
    return {"source": source, "label": label, **kw}


def provenance(registry, pid: str) -> dict:
    patient = store.get_patient(pid)
    if not patient:
        raise LookupError(f"Patient '{pid}' not found")
    extra = patient.get("extra") or {}
    synthetic = bool(extra.get("synthetic"))
    events = store.list_events(pid)
    members = store.ped_list_members(pid)
    analyses = [a for a in registry.variants.list_analyses() if a.get("patient_id") == pid]
    reports = store.report_list(pid)
    out: Dict[str, dict] = {}
    out["demographics"] = _dom("Demographics", SYNTHETIC if synthetic else CLINICIAN, recorded_utc=patient.get("created_utc"), recorded_by=patient.get("created_by"))
    prof = [e for e in events if e["kind"] in ("hpo_profile", "phenotype_assertions")]
    out["phenotypes"] = (_dom("Phenotypes", CLINICIAN, count_events=len(prof), first_recorded_utc=min(e["created_utc"] for e in prof),
                              last_recorded_utc=max(e["created_utc"] for e in prof),
                              confidence="Confidence not available unless entered with the term")
                         if prof else _dom("Phenotypes", "Not provided"))
    if analyses:
        a = analyses[0]
        out["variants"] = _dom("Variants", LAB, analysis_id=a["analysis_id"], filename=a.get("filename"), analysis_utc=a.get("timestamp"),
                               uploaded_by=a.get("created_by"),
                               classification_source=CALCULATED + " (rule-based ACMG/AMP engine; not a laboratory classification)")
    else:
        out["variants"] = _dom("Variants", "Not analyzed")
    out["diagnosis"] = _dom("Differential diagnosis", MODEL, engine=MODEL_VERSIONS["diagnosis_engine"],
                            claim="Model ranking from recorded phenotypes and variants; not a clinical diagnosis",
                            available=bool(prof))
    if not prof:
        out["diagnosis"]["source"] = "Insufficient data"
    conf = [e for e in events if e["kind"] == "diagnosis_confirmation"]
    out["diagnosis_confirmation"] = (_dom("Clinician-confirmed diagnosis", CLINICIAN, confirmations=[
        {"disease_id": e["payload"].get("disease_id"), "disease_name": e["payload"].get("disease_name"), "confirmed_by": e["payload"].get("confirmed_by"),
         "confirmed_utc": e["created_utc"]} for e in conf]) if conf else _dom("Clinician-confirmed diagnosis", "Not provided"))
    out["pedigree"] = (_dom("Pedigree", SYNTHETIC if any(m.get("synthetic") for m in members) else CLINICIAN, members=len(members))
                       if members else _dom("Pedigree", "Not provided"))
    out["pgx"] = _dom("Pharmacogenomics", CALCULATED + " from VCF genotypes and the bundled CPIC/PharmGKB-derived tables",
                      depends_on_variant_analysis=bool(analyses)) if analyses else _dom("Pharmacogenomics", "Not analyzed")
    out["reproductive"] = _dom("Reproductive risk", CALCULATED + " from carrier frequencies, community priors and the pedigree",
                               uses_pedigree=bool(members))
    saved = store.evidence_list(pid)
    out["evidence"] = (_dom("Evidence", LITERATURE + " / " + DATABASE, saved_items=len(saved),
                            retrieved_utc=sorted({(e.get("retrieved_at") or "") for e in saved if e.get("retrieved_at")})[-1:] or None)
                       if saved else _dom("Evidence", "No supporting evidence saved"))
    out["reports"] = _dom("Reports", CALCULATED, versions=len(reports), latest_utc=reports[0]["created_utc"] if reports else None)
    return {"case_id": pid, "domains": out, "versions": versions(registry)}


def quality(registry, pid: str) -> dict:
    patient = store.get_patient(pid)
    if not patient:
        raise LookupError(f"Patient '{pid}' not found")
    from ml_services.phenotype.service import assertion_state
    events = store.list_events(pid)
    members = store.ped_list_members(pid)
    analyses = [a for a in registry.variants.list_analyses() if a.get("patient_id") == pid]
    reports = store.report_list(pid)
    conflicts: List[dict] = []
    notes: List[dict] = []

    # 1. the same phenotype recorded with different assertions over time: surface it, never silently pick
    history: Dict[str, List[dict]] = {}
    for ev in sorted(events, key=lambda e: e.get("created_utc") or ""):
        p = ev.get("payload") or {}
        items = ([(i, "present") for i in p.get("hpo_profile", [])] if ev["kind"] == "hpo_profile"
                 else [(i, i.get("assertion")) for i in p.get("assertions", [])] if ev["kind"] == "phenotype_assertions" else [])
        for it, asr in items:
            history.setdefault(it["hpo_id"], []).append({"assertion": asr, "recorded_utc": ev["created_utc"], "recorded_by": p.get("confirmed_by")})
    current = assertion_state(events)
    for hid, hist in history.items():
        if len({h["assertion"] for h in hist}) > 1:
            conflicts.append({"type": "phenotype_assertion", "subject": hid, "message": f"Conflicting information: {hid} was recorded as "
                              + ", then ".join(f"{h['assertion']} ({h['recorded_utc']}, {h['recorded_by'] or 'unknown'})" for h in hist)
                              + f". The latest ({current[hid]['assertion']}) is used for analysis.", "sources": hist})

    # 2. patient record vs the pedigree proband
    proband = next((m for m in members if m.get("is_proband")), None)
    if proband:
        ps, ms = patient.get("sex"), proband.get("sex")
        if ps in ("M", "F") and ms in ("M", "F") and ps != ms:
            conflicts.append({"type": "sex", "subject": pid, "message": f"Conflicting information: patient record says sex {ps}; pedigree proband says {ms}.",
                              "sources": [{"source": "patient record", "value": ps}, {"source": "pedigree proband", "value": ms}]})
        pa, ma = patient.get("age_years"), proband.get("age_years")
        if isinstance(pa, int) and isinstance(ma, int) and pa != ma:
            conflicts.append({"type": "age", "subject": pid, "message": f"Conflicting information: patient record age {pa} vs pedigree proband age {ma}.",
                              "sources": [{"source": "patient record", "value": pa}, {"source": "pedigree proband", "value": ma}]})
    elif members:
        notes.append({"type": "pedigree", "message": "Pedigree has no proband marked; family analysis cannot be tied to this patient."})

    # 3. staleness: results that predate the data they depend on
    last_pheno = max([e["created_utc"] for e in events if e["kind"] in ("hpo_profile", "phenotype_assertions")] or [""])
    last_conf = max([e["created_utc"] for e in events if e["kind"] == "diagnosis_confirmation"] or [""])
    latest_input = max([last_pheno] + [str(a.get("timestamp") or "") for a in analyses] + [m.get("updated_utc") or m.get("created_utc") or "" for m in members])
    if reports and latest_input and reports[0]["created_utc"] < latest_input:
        notes.append({"type": "stale_report", "message": f"Stale data: the latest report (version {reports[0]['version']}, {reports[0]['created_utc']}) "
                      f"predates case data recorded at {latest_input}. Generate a new version to include it."})
    if last_conf and last_pheno and last_pheno > last_conf:
        notes.append({"type": "stale_confirmation", "message": "Stale data: phenotypes changed after the last diagnosis confirmation; re-review it."})

    # 4. explicit missing-data states
    missing = []
    if not history:
        missing.append({"domain": "phenotypes", "state": "Not provided"})
    if not analyses:
        missing.append({"domain": "variants", "state": "Not analyzed"})
    if not members:
        missing.append({"domain": "pedigree", "state": "Not provided"})
    for f in ("age_years", "sex", "state", "community"):
        if patient.get(f) in (None, ""):
            missing.append({"domain": f"patient.{f}", "state": "Not provided"})

    # 5. identifiers: everything that references this case points at this case
    problems = []
    for a in analyses:
        if a.get("patient_id") != pid:
            problems.append(f"analysis {a['analysis_id']} references {a.get('patient_id')}")
    for r in reports:
        if r["case_id"] != pid:
            problems.append(f"report {r['report_id']} references {r['case_id']}")
    return {"case_id": pid, "checked_utc": store._now(), "conflicts": conflicts, "notes": notes, "missing": missing, "identifier_problems": problems,
            "status": "Conflicting information" if conflicts else "No conflicts detected" if not problems else "Identifier problems",
            "scope": "Checks recorded phenotypes, patient vs pedigree demographics, result staleness, missing domains and identifiers. "
                     "It does not validate clinical correctness."}
