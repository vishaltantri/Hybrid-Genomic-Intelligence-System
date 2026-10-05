import os

os.environ.setdefault("GENOMIND_EMBED_MODEL", "none")

import pytest
from fastapi.testclient import TestClient

from backend.app import store
from backend.app.main import app
from backend.app.security import create_access_token
from ml_services.config import SEEDS_DIR

R = "/api/v1/reports"


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "reports.sqlite3")
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
    up = client.post("/api/v1/variants/upload", files={"file": ("t.vcf", text)}, data={"patient_id": pid, "hpo_ids_json": '["HP:0001394","HP:0001267"]'}, headers=hdr())
    assert up.status_code == 200, up.text
    assert client.post(f"/api/v1/pedigree/{pid}/demo-family", headers=hdr()).status_code == 200
    store.evidence_save(pid, {"source": "pubmed", "source_id": "123", "pmid": "123", "title": "Wilson disease review"}, "clinician", note="key", in_report=True)
    return pid


def pdf_text(data: bytes):
    import fitz
    doc = fitz.open(stream=data, filetype="pdf")
    return doc.page_count, "\n".join(p.get_text() for p in doc)


def test_generate_preview_and_pdf_match(client, case):
    r = client.post(f"{R}/case/{case}", json={}, headers=hdr()).json()
    assert r["version"] == 1 and r["status"] == "draft"
    secs = {s["id"]: s for s in r["content"]["sections"]}
    assert set(secs) >= {"patient", "phenotypes", "variants", "diagnosis", "pedigree", "pgx", "reproductive", "evidence"}
    assert secs["pgx"]["status"] == "available" and any("Poor" in str(row) for row in secs["pgx"]["rows"])
    assert secs["variants"]["status"] == "available" and secs["evidence"]["rows"][0][2] == "123"
    res = client.get(f"{R}/{r['report_id']}/pdf", headers=hdr())
    assert res.status_code == 200 and res.headers["content-type"] == "application/pdf" and res.content[:5] == b"%PDF-"
    pages, text = pdf_text(res.content)
    assert pages >= 1 and case in text and r["report_id"] in text
    for s in r["content"]["sections"]:                      # PDF is rendered from exactly the previewed content
        assert s["title"] in text
    for row in secs["variants"]["rows"]:
        assert row[0] in text                                # every previewed variant gene is in the PDF
    assert "not a diagnosis" in text.lower()


def test_versioning_finalize_immutability_and_integrity(client, case):
    v1 = client.post(f"{R}/case/{case}", json={}, headers=hdr()).json()
    v2 = client.post(f"{R}/case/{case}", json={}, headers=hdr()).json()
    assert (v1["version"], v2["version"]) == (1, 2)
    assert [x["version"] for x in client.get(f"{R}/case/{case}", headers=hdr()).json()] == [2, 1]
    fin = client.post(f"{R}/{v1['report_id']}/finalize", headers=hdr()).json()
    assert fin["status"] == "final" and fin["finalized_by"] == "clinician"
    assert client.post(f"{R}/{v1['report_id']}/finalize", headers=hdr()).status_code == 409
    assert client.post(f"{R}/{v1['report_id']}/refresh", headers=hdr()).status_code == 409
    assert client.post(f"{R}/{v2['report_id']}/refresh", headers=hdr()).status_code == 200
    assert client.get(f"{R}/{v1['report_id']}", headers=hdr()).json()["integrity_ok"] is True
    with store._connect() as conn:                          # tamper with stored content: integrity flag must catch it
        conn.execute("UPDATE case_reports SET content = replace(content, 'Andhra Pradesh', 'Tampered') WHERE report_id=?", (v1["report_id"],))
    assert client.get(f"{R}/{v1['report_id']}", headers=hdr()).json()["integrity_ok"] is False


def test_empty_case_uses_distinct_states_not_invented_content(client):
    pid = client.post("/api/v1/patients", json={"age_years": 4, "sex": "M", "state": "Kerala", "community": "General"}, headers=hdr()).json()["patient_id"]
    r = client.post(f"{R}/case/{pid}", json={}, headers=hdr()).json()
    st = {s["id"]: s["status"] for s in r["content"]["sections"]}
    assert st["phenotypes"] == "not_documented" and st["variants"] == "not_analyzed" and st["diagnosis"] == "insufficient"
    assert st["pedigree"] == "not_documented" and st["evidence"] == "no_result"
    _, text = pdf_text(client.get(f"{R}/{r['report_id']}/pdf", headers=hdr()).content)
    assert "Not analyzed" in text and "Not documented" in text


def test_section_selection_json_export_and_errors(client, case):
    r = client.post(f"{R}/case/{case}", json={"sections": ["patient", "variants"]}, headers=hdr()).json()
    assert [s["id"] for s in r["content"]["sections"]] == ["patient", "variants"]
    j = client.get(f"{R}/{r['report_id']}/json", headers=hdr())
    assert j.status_code == 200 and j.json()["content"]["case_id"] == case
    assert client.post(f"{R}/case/{case}", json={"sections": ["bogus"]}, headers=hdr()).status_code == 422
    assert client.post(f"{R}/case/NOPE", json={}, headers=hdr()).status_code == 404
    assert client.get(f"{R}/RPT-NOPE", headers=hdr()).status_code == 404


def test_authorization_and_audit(client, case):
    assert client.post(f"{R}/case/{case}", json={}).status_code in (401, 403)
    assert client.post(f"{R}/case/{case}", json={}, headers=hdr("a", "asha")).status_code == 403
    assert client.get(f"{R}/case/{case}", headers=hdr("p", "patient")).status_code == 403
    r = client.post(f"{R}/case/{case}", json={}, headers=hdr()).json()
    client.get(f"{R}/{r['report_id']}/pdf", headers=hdr())
    actions = {a["action"] for a in store.recent_audit(50)}
    assert {"report.generate", "report.pdf"} <= actions
