import os

os.environ.setdefault("GENOMIND_EMBED_MODEL", "none")

import pytest
from fastapi.testclient import TestClient

from backend.app import store
from backend.app.main import app
from backend.app.security import create_access_token
from ml_services.config import SEEDS_DIR

E = "/api/v1/emr"


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "fhir.sqlite3")
    store.init_db()


@pytest.fixture
def client():
    return TestClient(app)


def hdr(name="clinician", role="doctor"):
    return {"Authorization": f"Bearer {create_access_token(name, role)}"}


@pytest.fixture
def case(client):
    pid = client.post("/api/v1/patients", json={"age_years": 9, "sex": "F", "state": "Andhra Pradesh", "community": "Reddy"}, headers=hdr()).json()["patient_id"]
    text = (SEEDS_DIR / "clinical_sample_trio.vcf").read_text()
    up = client.post("/api/v1/variants/upload", files={"file": ("t.vcf", text)}, data={"patient_id": pid, "hpo_ids_json": '["HP:0001337","HP:0000952"]'}, headers=hdr())
    assert up.status_code == 200, up.text
    items = [{"hpo_id": h, "assertion": "present"} for h in ("HP:0001337", "HP:0000952")]
    assert client.post(f"/api/v1/phenotype/case/{pid}/import", json={"items": items}, headers=hdr()).status_code == 200
    return pid


def test_case_export_is_valid_and_from_real_data(client, case):
    r = client.get(f"{E}/fhir/case/{case}", headers=hdr()).json()
    b = r["bundle"]
    assert b["resourceType"] == "Bundle" and r["validation"]["valid"] is True
    assert "NRCeS" in r["validation"]["scope"]
    c = r["validation"]["counts"]
    assert c["Patient"] == 1 and c["Observation"] >= 3
    hp = {x["resource"]["code"]["coding"][0]["code"] for x in b["entry"] if x["resource"]["resourceType"] == "Observation" and x["resource"]["code"].get("coding")}
    assert {"HP:0001337", "HP:0000952"} <= hp
    assert any("finalized report" in n for n in r["notes"])
    assert "DiagnosticReport" not in c


def test_final_report_included_and_unknown_case(client, case):
    rep = client.post(f"/api/v1/reports/case/{case}", json={}, headers=hdr()).json()
    client.post(f"/api/v1/reports/{rep['report_id']}/finalize", headers=hdr())
    r = client.get(f"{E}/fhir/case/{case}", headers=hdr()).json()
    assert r["validation"]["counts"]["DiagnosticReport"] == 1 and r["validation"]["valid"]
    assert client.get(f"{E}/fhir/case/NOPE", headers=hdr()).status_code == 404


def test_validation_catches_structural_errors(client):
    bad = {"resourceType": "Bundle", "type": "weird", "entry": [
        {"resource": {"resourceType": "Observation", "status": "nope", "subject": {"reference": "Patient/ghost"}}},
        {"resource": {"resourceType": "Patient", "id": "p1", "gender": "robot"}}]}
    v = client.post(f"{E}/fhir/validate", json=bad, headers=hdr()).json()
    msgs = " ".join(i["message"] for i in v["issues"])
    assert v["valid"] is False
    for frag in ("Bundle.type", "Missing required element 'code'", "Invalid Observation.status", "Unresolved reference", "Invalid gender"):
        assert frag in msgs
    assert client.post(f"{E}/fhir/validate", json={"resourceType": "Patient"}, headers=hdr()).json()["valid"] is False


def test_import_preview_persists_nothing_and_rbac(client, case):
    b = client.get(f"{E}/fhir/case/{case}", headers=hdr()).json()["bundle"]
    before = store.list_patients()
    p = client.post(f"{E}/fhir/import-preview", json=b, headers=hdr()).json()
    assert p["persisted"] is False and p["validation"]["valid"] and "HP:0001337" in p["mapped"]["phenotype_codes"]
    assert len(store.list_patients()) == len(before)
    assert client.post(f"{E}/fhir/import-preview", json=b, headers=hdr("a", "asha")).status_code == 403
    assert client.get(f"{E}/fhir/case/{case}", headers=hdr("p", "patient")).status_code == 403


def test_abdm_honestly_not_connected(client):
    s = client.get(f"{E}/abdm/status", headers=hdr()).json()
    assert s["connected"] is False and s["capabilities"]["abha_verification"] is False
    assert "fhir.export" not in {a["action"] for a in store.recent_audit(20)}
