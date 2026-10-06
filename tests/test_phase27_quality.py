"""Phase 27: provenance, versions, conflicts, staleness, missing-data states, model-vs-clinician distinction."""
import json
import os
import time

os.environ.setdefault("GENOMIND_EMBED_MODEL", "none")

import pytest
from fastapi.testclient import TestClient

from backend.app import store
from backend.app.main import app
from backend.app.security import hash_password
from backend.app.services import registry
from ml_services.config import SEEDS_DIR

API = "/api/v1"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "p27.sqlite3")
    store.init_db()
    registry.variants._analyses.clear()
    for u, role in (("doc", "doctor"), ("res", "researcher"), ("asha1", "asha")):
        store.create_user(u, role, hash_password("changeme"))
    c = TestClient(app)

    def hdr(u):
        t = c.post(f"{API}/auth/token", data={"username": u, "password": "changeme"}).json()["access_token"]
        return {"Authorization": f"Bearer {t}"}
    return c, hdr


def _patient(c, H, **kw):
    body = {"age_years": 9, "sex": "F", "state": "Andhra Pradesh", "community": "Reddy"}
    body.update(kw)
    return c.post(f"{API}/patients", json=body, headers=H).json()["patient_id"]


def _pheno(c, H, pid, hpo, assertion):
    assert c.post(f"{API}/phenotype/case/{pid}/import", json={"items": [{"hpo_id": hpo, "assertion": assertion}]}, headers=H).status_code == 200


def test_missing_data_uses_explicit_states(env):
    c, hdr = env
    H = hdr("doc")
    pid = _patient(c, H, age_years=None, community=None)
    q = c.get(f"{API}/quality/case/{pid}", headers=H).json()
    states = {m["domain"]: m["state"] for m in q["missing"]}
    assert states["phenotypes"] == "Not provided" and states["variants"] == "Not analyzed" and states["pedigree"] == "Not provided"
    assert states["patient.age_years"] == "Not provided" and states["patient.community"] == "Not provided"
    prov = c.get(f"{API}/quality/provenance/{pid}", headers=H).json()["domains"]
    assert prov["variants"]["source"] == "Not analyzed" and prov["phenotypes"]["source"] == "Not provided"
    assert prov["diagnosis"]["source"] == "Insufficient data" and prov["pgx"]["source"] == "Not analyzed"


def test_provenance_labels_do_not_upgrade_model_output(env):
    c, hdr = env
    H = hdr("doc")
    pid = _patient(c, H)
    _pheno(c, H, pid, "HP:0001337", "present")
    up = c.post(f"{API}/variants/upload", files={"file": ("t.vcf", (SEEDS_DIR / "demo_wilson_trio.vcf").read_text())}, data={"patient_id": pid}, headers=H)
    assert up.status_code == 200
    d = c.get(f"{API}/quality/provenance/{pid}", headers=H).json()["domains"]
    assert d["phenotypes"]["source"] == "Clinician-entered"
    assert d["variants"]["source"].startswith("Laboratory-derived") and "Calculated" in d["variants"]["classification_source"]
    assert d["variants"]["analysis_id"] == up.json()["analysis_id"] and d["variants"]["filename"] == "t.vcf"
    assert d["diagnosis"]["source"] == "Model-generated" and "not a clinical diagnosis" in d["diagnosis"]["claim"]
    assert d["pgx"]["source"].startswith("Calculated") and d["reproductive"]["source"].startswith("Calculated")
    assert d["diagnosis_confirmation"]["source"] == "Not provided"


def test_versions_come_from_the_running_system(env):
    c, hdr = env
    H = hdr("doc")
    v = c.get(f"{API}/quality/provenance/{_patient(c, H)}", headers=H).json()["versions"]
    assert v["knowledge_graph"]["nodes"] == registry.status()["graph_nodes"] and len(v["knowledge_graph"]["sha256_12"]) == 12
    assert len(v["hpo_ontology"]["sha256_12"]) == 12 and v["models"]["gnn_reranker"].startswith("disabled")
    assert v["schema_version"] >= 4


def test_conflicting_phenotype_assertions_are_reported_not_silently_resolved(env):
    c, hdr = env
    H = hdr("doc")
    pid = _patient(c, H)
    _pheno(c, H, pid, "HP:0001337", "present")
    time.sleep(1.1)                                         # event timestamps have 1 s resolution
    _pheno(c, H, pid, "HP:0001337", "absent")
    q = c.get(f"{API}/quality/case/{pid}", headers=H).json()
    conf = [x for x in q["conflicts"] if x["type"] == "phenotype_assertion"]
    assert conf and q["status"] == "Conflicting information"
    assert "Conflicting information" in conf[0]["message"] and "present" in conf[0]["message"] and "absent" in conf[0]["message"]
    assert [s["assertion"] for s in conf[0]["sources"]] == ["present", "absent"] and "doc" in conf[0]["message"]
    assert "latest (absent)" in conf[0]["message"]


def test_patient_vs_pedigree_conflicts_and_stale_report(env):
    c, hdr = env
    H = hdr("doc")
    pid = _patient(c, H, sex="F", age_years=9)
    _pheno(c, H, pid, "HP:0001337", "present")
    c.post(f"{API}/variants/upload", files={"file": ("t.vcf", (SEEDS_DIR / "demo_wilson_trio.vcf").read_text())}, data={"patient_id": pid}, headers=H)
    c.post(f"{API}/pedigree/{pid}/demo-family", headers=H)
    assert c.get(f"{API}/quality/case/{pid}", headers=H).json()["conflicts"] == []
    # corrupt the proband demographics so they disagree with the patient record
    with store._connect() as conn:
        conn.execute("UPDATE pedigree_members SET sex='M', age_years=40 WHERE case_id=? AND is_proband=1", (pid,))
    types = {x["type"] for x in c.get(f"{API}/quality/case/{pid}", headers=H).json()["conflicts"]}
    assert {"sex", "age"} <= types
    # a report followed by newer phenotype data is flagged stale
    c.post(f"{API}/reports/case/{pid}", json={}, headers=H)
    time.sleep(1.1)
    _pheno(c, H, pid, "HP:0000952", "present")
    notes = c.get(f"{API}/quality/case/{pid}", headers=H).json()["notes"]
    assert any(n["type"] == "stale_report" and "Stale data" in n["message"] for n in notes)


def test_invalid_identifiers(env):
    c, hdr = env
    H = hdr("doc")
    assert c.get(f"{API}/quality/case/NOPE-1", headers=H).status_code == 404
    assert c.get(f"{API}/quality/provenance/NOPE-1", headers=H).status_code == 404
    assert c.get(f"{API}/quality/case/NOPE-1").status_code == 401
    assert c.get(f"{API}/quality/case/x", headers=hdr("asha1")).status_code == 403
    assert c.post(f"{API}/dx/case/NOPE-1/confirm", json={"disease_id": "ORPHA:915"}, headers=H).status_code == 404


def test_model_ranking_vs_clinician_confirmation(env):
    c, hdr = env
    H = hdr("doc")
    pid = _patient(c, H)
    for h in ("HP:0001337", "HP:0000952", "HP:0002240"):
        _pheno(c, H, pid, h, "present")
    ws = c.get(f"{API}/dx/case/{pid}", headers=H).json()
    assert ws["confirmed_diagnoses"] == [] and all(r["claim"] == "Model ranking" for r in ws["differential"])
    assert "not a clinical diagnosis" in ws["interpretation"] and "not calibrated" in ws["confidence_note"]
    # only a clinician with the permission can confirm; researchers and ASHA workers cannot
    assert c.post(f"{API}/dx/case/{pid}/confirm", json={"disease_id": "ORPHA:915"}, headers=hdr("res")).status_code == 403
    assert c.post(f"{API}/dx/case/{pid}/confirm", json={"disease_id": "ORPHA:NOPE"}, headers=H).status_code == 422
    r = c.post(f"{API}/dx/case/{pid}/confirm", json={"disease_id": "ORPHA:915", "note": "Ceruloplasmin low"}, headers=H)
    assert r.status_code == 200 and r.json()["confirmed_by"] == "doc" and r.json()["model_rank_at_confirmation"] == 1
    ws = c.get(f"{API}/dx/case/{pid}", headers=H).json()
    claims = {x["disease_id"]: x["claim"] for x in ws["differential"]}
    assert claims["ORPHA:915"] == "Clinician-confirmed" and ws["confirmed_diagnoses"][0]["confirmed_by"] == "doc"
    assert [v for k, v in claims.items() if k != "ORPHA:915"] == ["Model ranking"] * (len(claims) - 1)
    prov = c.get(f"{API}/quality/provenance/{pid}", headers=H).json()["domains"]["diagnosis_confirmation"]
    assert prov["source"] == "Clinician-entered" and prov["confirmations"][0]["disease_id"] == "ORPHA:915"
    assert any(a["action"] == "dx_confirm" for a in store.recent_audit(20))


def test_report_carries_provenance_quality_versions_and_confirmation_state(env):
    c, hdr = env
    H = hdr("doc")
    pid = _patient(c, H)
    for h in ("HP:0001337", "HP:0000952"):
        _pheno(c, H, pid, h, "present")
    rid = c.post(f"{API}/reports/case/{pid}", json={}, headers=H).json()["report_id"]
    body = c.get(f"{API}/reports/{rid}/json", headers=H).json()
    content = body.get("content", body)
    assert content["data_quality"]["case_id"] == pid and content["provenance"]["case_id"] == pid
    assert content["provenance"]["versions"]["knowledge_graph"]["nodes"] > 0
    dx = next(s for s in content["sections"] if s["id"] == "diagnosis")
    assert "not a clinical diagnosis" in dx["note"] and "No clinician has confirmed" in dx["note"]
    c.post(f"{API}/dx/case/{pid}/confirm", json={"disease_id": "ORPHA:915"}, headers=H)
    rid2 = c.post(f"{API}/reports/case/{pid}", json={}, headers=H).json()["report_id"]
    dx2 = next(s for s in c.get(f"{API}/reports/{rid2}/json", headers=H).json().get("content", {}).get("sections", []) or
               c.get(f"{API}/reports/{rid2}/json", headers=H).json()["sections"] if s["id"] == "diagnosis")
    assert "Clinician-confirmed: Wilson disease (confirmed by doc" in dx2["note"]
    pdf = c.get(f"{API}/reports/{rid2}/pdf", headers=H)
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"


def test_cross_module_identifiers_are_consistent(env):
    """Patient, case, variants, pedigree, reports and FHIR all carry the same id; nothing references an unknown case."""
    c, hdr = env
    H = hdr("doc")
    pid = _patient(c, H)
    _pheno(c, H, pid, "HP:0001337", "present")
    c.post(f"{API}/variants/upload", files={"file": ("t.vcf", (SEEDS_DIR / "demo_wilson_trio.vcf").read_text())}, data={"patient_id": pid}, headers=H)
    c.post(f"{API}/pedigree/{pid}/demo-family", headers=H)
    c.post(f"{API}/reports/case/{pid}", json={}, headers=H)
    q = c.get(f"{API}/quality/case/{pid}", headers=H).json()
    assert q["identifier_problems"] == [] and q["status"] == "No conflicts detected"
    fhir = json.dumps(c.get(f"{API}/emr/fhir/case/{pid}", headers=H).json())
    assert pid in fhir
    with store._connect() as conn:
        orphans = conn.execute("SELECT COUNT(*) FROM case_reports WHERE case_id NOT IN (SELECT patient_id FROM patients)").fetchone()[0]
    assert orphans == 0
