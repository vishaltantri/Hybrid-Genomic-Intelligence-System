"""Phase 8: Diagnosis Intelligence layer."""
import os

os.environ.setdefault("GENOMIND_EMBED_MODEL", "none")

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.security import create_access_token
from backend.app.services import registry


@pytest.fixture
def client():
    return TestClient(app)


def hdr(name="clinician", role="doctor"):
    return {"Authorization": f"Bearer {create_access_token(name, role)}"}


def mkcase(client, hpos=("HP:0001337", "HP:0000952"), absent=()):
    pid = client.post("/api/v1/patients", json={"name": "Dx Case", "age": 12, "sex": "F", "state": "Kerala", "community": "General"}, headers=hdr()).json()["patient_id"]
    items = [{"hpo_id": h, "assertion": "present"} for h in hpos] + [{"hpo_id": h, "assertion": "absent"} for h in absent]
    if items:
        assert client.post(f"/api/v1/phenotype/case/{pid}/import", json={"items": items}, headers=hdr()).status_code == 200
    return pid


def test_workspace_matches_the_engine_exactly(client):
    pid = mkcase(client)
    w = client.get(f"/api/v1/dx/case/{pid}", headers=hdr()).json()
    core = registry.twin.load_core(pid)
    raw = registry.diagnosis.diagnose(core["hpo_ids"], core["context"], top_k=8, explain=True)["results"]
    assert [d["disease_id"] for d in w["differential"]] == [r["disease_id"] for r in raw]
    assert [d["probability"] for d in w["differential"]] == [r["probability"] for r in raw]
    top = w["top_diagnosis"]
    assert top["rank"] == 1 and top["supporting_phenotypes"] and "Clinical Decision Support" in w["disclaimer"]
    assert w["summary"]["variant_note"].startswith("Not analyzed") and w["summary"]["pedigree_note"] == "No pedigree recorded."
    assert top["evidence_quality"]["label"] in ("Insufficient evidence", "No matching record", "Evidence saved")
    assert all(m["status"] == "Not documented" for m in top["missing_findings"])


def test_empty_case_is_insufficient_not_invented(client):
    pid = mkcase(client, hpos=())
    w = client.get(f"/api/v1/dx/case/{pid}", headers=hdr()).json()
    assert w["available"] is False and w["differential"] == [] and "Insufficient" in w["note"]


def test_why_uses_real_factors(client):
    pid = mkcase(client)
    w = client.get(f"/api/v1/dx/case/{pid}", headers=hdr()).json()
    top, second = w["differential"][0], w["differential"][1]
    r = client.get(f"/api/v1/dx/case/{pid}/why", params={"disease_id": top["disease_id"]}, headers=hdr()).json()
    f = r["factors"]
    assert f["phenotype_similarity"] == top["phenotype_similarity"] and f["probability"] == top["probability"] and f["rank"] == 1
    assert f["prior_exposure"] == 0.15 and f["similarity_gate"] == 0.8
    assert any("similarity" in line for line in r["explanation"]) and r["supporting_symptoms"]
    r2 = client.get(f"/api/v1/dx/case/{pid}/why", params={"disease_id": second["disease_id"]}, headers=hdr()).json()
    assert any(top["disease_name"] in line for line in r2["explanation"])
    assert client.get(f"/api/v1/dx/case/{pid}/why", params={"disease_id": "ORPHA:0"}, headers=hdr()).status_code == 404


def test_matrix_shape_and_explicit_absence(client):
    pid = mkcase(client, absent=("HP:0000616",))
    m = client.get(f"/api/v1/dx/case/{pid}/matrix", headers=hdr()).json()
    assert [c["hpo_id"] for c in m["columns"]] == ["HP:0000952", "HP:0001337"]
    assert all(len(r["cells"]) == 2 for r in m["rows"])
    wilson = next(r for r in m["rows"] if r["disease_id"] == "ORPHA:915")
    assert [a["hpo_id"] for a in wilson["explicitly_absent"]] == ["HP:0000616"]


def test_discriminating_probes_are_real_engine_runs(client):
    pid = mkcase(client)
    d = client.get(f"/api/v1/dx/case/{pid}/discriminating", headers=hdr()).json()
    assert d["probes"] and all(p["status"] == "Not documented" for p in d["probes"])
    p = d["probes"][0]
    core = registry.twin.load_core(pid)
    top = registry.diagnosis.diagnose(sorted(core["hpo_ids"] + [p["hpo_id"]]), core["context"], top_k=1, explain=False, uncertainty=False)["results"][0]
    assert p["top_after"] == top["disease_name"] and p["top_probability_after"] == top["probability"]


def test_whatif_reruns_engine_and_does_not_touch_case(client):
    pid = mkcase(client)
    before = client.get(f"/api/v1/phenotype/case/{pid}", headers=hdr()).json()["observed"]
    r = client.post(f"/api/v1/dx/case/{pid}/whatif", json={"type": "phenotype_remove", "params": {"hpo_ids": ["HP:0000952"]}}, headers=hdr())
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["baseline"]["differential"] and j["scenario"]["differential"] and j["scenario_id"].startswith("SCN-")
    assert j["baseline"]["differential"] != j["scenario"]["differential"]
    assert client.get(f"/api/v1/phenotype/case/{pid}", headers=hdr()).json()["observed"] == before
    bad = client.post(f"/api/v1/dx/case/{pid}/whatif", json={"type": "phenotype_remove", "params": {"hpo_ids": ["HP:0009999"]}}, headers=hdr())
    assert bad.status_code == 422
    assert client.post(f"/api/v1/dx/case/{pid}/whatif", json={"type": "survival", "params": {}}, headers=hdr()).status_code == 422


def test_rbac_and_not_found(client):
    pid = mkcase(client)
    for who in (("p", "patient"), ("r", "researcher")):
        assert client.get(f"/api/v1/dx/case/{pid}", headers=hdr(*who)).status_code == 403
    assert client.get(f"/api/v1/dx/case/{pid}").status_code in (401, 403)
    assert client.get("/api/v1/dx/case/NOPE", headers=hdr()).status_code == 404


def test_assistant_receives_diagnosis_context(client):
    pid = mkcase(client)
    r = client.post("/api/v1/assistant/chat", json={"message": "Why is the first diagnosis ranked first?", "patient_id": pid, "include_diagnosis_intel": True}, headers=hdr())
    assert r.status_code == 200, r.text
    assert any(c.get("source_type") == "diagnosis_intelligence" for c in r.json()["citations"])
    assert client.post("/api/v1/assistant/chat", json={"message": "x", "patient_id": pid, "include_diagnosis_intel": True}, headers=hdr("p", "patient")).status_code == 403
