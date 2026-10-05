"""Master end-to-end workflow across Phases 1-15, driven through the real HTTP API (no mocks)."""
import os

os.environ.setdefault("GENOMIND_EMBED_MODEL", "none")

import pytest
from fastapi.testclient import TestClient

from backend.app import store
from backend.app.main import app
from backend.app.security import hash_password
from ml_services.config import SEEDS_DIR

API = "/api/v1"


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "e2e.sqlite3")
    store.init_db()
    store.create_user("clinician", "doctor", hash_password("changeme"))
    store.create_user("drb", "doctor", hash_password("x" * 8))


def test_master_workflow():
    c = TestClient(app)

    # login
    r = c.post(f"{API}/auth/token", data={"username": "clinician", "password": "changeme"})
    assert r.status_code == 200, r.text
    H = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # create case, then search for it
    pid = c.post(f"{API}/patients", json={"age_years": 9, "sex": "F", "state": "Andhra Pradesh", "community": "Reddy"}, headers=H).json()["patient_id"]
    found = c.get(f"{API}/search", params={"q": pid}, headers=H).json()["results"]["cases"]
    assert found[0]["id"] == pid and found[0]["route"] == "cases"
    assert c.get(f"{API}/patients/{pid}", headers=H).status_code == 200            # open case

    # phenotype
    items = [{"hpo_id": h, "assertion": "present"} for h in ("HP:0001337", "HP:0000952")]
    assert c.post(f"{API}/phenotype/case/{pid}/import", json={"items": items}, headers=H).status_code == 200
    assert c.get(f"{API}/phenotype/case/{pid}", headers=H).status_code == 200

    # variant
    vcf = (SEEDS_DIR / "clinical_sample_trio.vcf").read_text()
    up = c.post(f"{API}/variants/upload", files={"file": ("t.vcf", vcf)}, data={"patient_id": pid}, headers=H)
    assert up.status_code == 200, up.text
    analysis_id = up.json()["analysis_id"]
    gene = next(v["gene_symbol"] for v in up.json()["variants"] if v.get("gene_symbol"))

    # evidence
    assert c.get(f"{API}/evidence/variant/{analysis_id}", params={"variant_id": up.json()["variants"][0]["variant_id"]}, headers=H).status_code == 200
    assert c.get(f"{API}/evidence/case/{pid}", headers=H).status_code == 200

    # diagnosis
    dx = c.get(f"{API}/dx/case/{pid}", headers=H)
    assert dx.status_code == 200, dx.text

    # pedigree, PGx, reproductive
    assert c.post(f"{API}/pedigree/{pid}/demo-family", headers=H).status_code == 200
    assert c.get(f"{API}/pedigree/{pid}/overview", headers=H).status_code == 200
    assert c.get(f"{API}/pgx/case/{pid}", headers=H).status_code == 200
    assert c.get(f"{API}/repro/case/{pid}", headers=H).status_code == 200

    # workflow + report + notification
    assert c.post(f"{API}/workflow/case/{pid}/assign", json={"assignee": "drb"}, headers=H).status_code == 200
    assert c.post(f"{API}/workflow/case/{pid}/status", json={"status": "in_review"}, headers=H).status_code == 200
    rep = c.post(f"{API}/reports/case/{pid}", json={}, headers=H)
    assert rep.status_code in (200, 201), rep.text
    rid = rep.json()["report_id"]
    pdf = c.get(f"{API}/reports/{rid}/pdf", headers=H)
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"
    assert c.post(f"{API}/reports/{rid}/finalize", headers=H).status_code == 200
    assert c.post(f"{API}/workflow/case/{pid}/status", json={"status": "report_ready"}, headers=H).status_code == 200

    # FHIR export reflects the finalized report and is structurally valid
    fhir = c.get(f"{API}/emr/fhir/case/{pid}", headers=H).json()
    assert fhir["validation"]["valid"] is True and fhir["validation"]["counts"]["DiagnosticReport"] == 1

    # the assignee received real notifications
    DR = {"Authorization": "Bearer " + c.post(f"{API}/auth/token", data={"username": "drb", "password": "x" * 8}).json()["access_token"]}
    kinds = {n["kind"] for n in c.get(f"{API}/workflow/notifications", headers=DR).json()}
    assert {"assignment", "report_final"} <= kinds

    # search report / variant / disease, then command-center navigation targets
    assert c.get(f"{API}/search", params={"q": rid}, headers=H).json()["results"]["reports"][0]["context"]["patient_id"] == pid
    v = c.get(f"{API}/search", params={"q": gene, "types": "variants"}, headers=H).json()["results"]["variants"]
    assert v and v[0]["context"]["analysis_id"] == analysis_id
    assert any("Wilson" in d["label"] for d in c.get(f"{API}/search", params={"q": "wilson"}, headers=H).json()["results"]["diseases"])
    cmds = c.get(f"{API}/search", params={"q": "reports", "types": "commands"}, headers=H).json()["results"]["commands"]
    assert cmds[0]["route"] == "reports"
