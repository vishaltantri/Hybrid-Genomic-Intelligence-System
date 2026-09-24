"""API + FHIR integration tests (Phase 6 contract)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api.v1 import emr_integration as fhir
from backend.app.main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def doctor_headers(client):
    r = client.post("/api/v1/auth/token",
                    data={"username": "admin", "password": "admin-password-change-me"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["graph_nodes"] > 100
    assert len(body["modules"]) == 11


def test_platform_status_shows_fallbacks(client):
    body = client.get("/api/v1/platform/status").json()
    assert "ner_backend" in body
    assert set(body["trained_checkpoints"]) == {"clinical_ner_muril", "gnn_han", "hpo_mapper",
                                                "whisper_hi"}


def test_unauthenticated_is_rejected(client):
    assert client.post("/api/v1/clinical/extract", json={"text": "hello world"}).status_code == 401


def test_invalid_credentials_rejected(client):
    r = client.post("/api/v1/auth/token", data={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_role_based_access_control(client, doctor_headers):
    # create an ASHA user (admin-only action), then prove ASHA cannot run diagnosis
    client.post("/api/v1/auth/register",
                json={"username": "asha_test", "password": "asha-password-1", "role": "asha"},
                headers=doctor_headers)
    token = client.post("/api/v1/auth/token",
                        data={"username": "asha_test", "password": "asha-password-1"}).json()["access_token"]
    asha_headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/triage/questionnaire", headers=asha_headers).status_code == 200
    assert client.post("/api/v1/diagnosis", json={"hpo_ids": ["HP:0000952"]},
                       headers=asha_headers).status_code == 403


def test_clinical_extract_and_hpo_map(client, doctor_headers):
    r = client.post("/api/v1/clinical/extract",
                    json={"text": "Bacha teen saal ka hai, mirgi ka daura padta hai"}, headers=doctor_headers)
    assert r.status_code == 200
    assert any(e["label"] == "SYMPTOM" for e in r.json()["entities"])

    m = client.post("/api/v1/clinical/hpo-map",
                    json={"text": "Peeli aankhein aur piliya do hafte se hai"}, headers=doctor_headers)
    assert m.status_code == 200
    assert "HP:0000952" in m.json()["hpo_ids"]


def test_diagnosis_endpoint(client, doctor_headers):
    # realistic Wilson profile: vignette terms alone cannot identify a disease
    # among the 12,880 in the real hpoa-backed graph (see seed_cases C001)
    from ml_services.config import SEEDS_DIR
    from ml_services.utils import read_jsonl

    hpo = read_jsonl(SEEDS_DIR / "seed_cases.jsonl")[0]["hpo"]
    r = client.post("/api/v1/diagnosis",
                    json={"hpo_ids": hpo,
                          "state": "Andhra Pradesh", "explain": True}, headers=doctor_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["results"][0]["disease_id"] == "ORPHA:915"
    assert body["results"][0]["driving_symptoms"]


def test_diagnosis_requires_input(client, doctor_headers):
    assert client.post("/api/v1/diagnosis", json={}, headers=doctor_headers).status_code == 400


def test_pgx_endpoints(client, doctor_headers):
    r = client.post("/api/v1/pgx/check",
                    json={"drugs": ["clopidogrel", "primaquine"], "state": "Tamil Nadu", "sex": "M"},
                    headers=doctor_headers)
    assert r.status_code == 200
    assert r.json()["alerts"]
    assert r.json()["report"]["markdown"]
    cov = client.get("/api/v1/pgx/coverage", headers=doctor_headers).json()
    assert cov["n_pairs"] > 10


def test_reproductive_endpoints(client, doctor_headers):
    r = client.post("/api/v1/reproductive/couple-risk",
                    json={"partner_a": {"state": "Tamil Nadu", "relationship": "first_cousins"},
                          "partner_b": {"state": "Tamil Nadu", "age": 31,
                                        "family_history": {"ORPHA:231222": "affected_sibling"}}},
                    headers=doctor_headers)
    assert r.status_code == 200
    assert r.json()["report"]["markdown"]
    lab = client.post("/api/v1/reproductive/lab-report",
                      json={"text": "HbA2 5.4 %, MCV 68 fL"}, headers=doctor_headers)
    assert lab.status_code == 200
    assert lab.json()["flags"]


def test_triage_endpoints(client, doctor_headers):
    q = client.get("/api/v1/triage/questionnaire", headers=doctor_headers)
    assert q.status_code == 200 and q.json()["questions"]
    t = client.post("/api/v1/triage/text",
                    json={"transcript": "bacche ko daura pad raha hai", "age": 3}, headers=doctor_headers)
    assert t.status_code == 200
    assert t.json()["triage_color"] == "red"
    sync = client.post("/api/v1/triage/sync",
                       json=[{"local_id": "A1", "village": "V1", "district": "D1", "state": "Odisha",
                              "hpo_ids": ["HP:0001878"], "triage_color": "red"}],
                       headers=doctor_headers)
    assert sync.status_code == 200 and sync.json()["accepted_records"] == 1


def test_dashboard_and_policy_brief(client, doctor_headers):
    d = client.get("/api/v1/dashboard/national?month=2026-01", headers=doctor_headers).json()
    assert d["totals"]["cases"] > 0
    assert "SIMULATED" in d["data_note"]
    brief = client.post("/api/v1/dashboard/policy-brief", headers=doctor_headers).json()
    assert "Policy Brief" in brief["markdown"]
    assert client.get("/api/v1/dashboard/research-gap", headers=doctor_headers).json()["rows"]


def test_federated_endpoint(client, doctor_headers):
    r = client.post("/api/v1/federated/simulate?rounds=3&n_clients=4&sigma=1.1&secure_aggregation=true",
                    headers=doctor_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["history"]
    assert body["epidemiology_map"]["totals"]
    assert body["privacy_utility_table"]


def test_learning_endpoints(client, doctor_headers):
    assert client.get("/api/v1/learning/queue", headers=doctor_headers).status_code == 200
    assert client.get("/api/v1/learning/drift", headers=doctor_headers).json()["report"]["checks"]
    proposals = client.post("/api/v1/learning/kg-proposals", json={"offline": True},
                            headers=doctor_headers)
    assert proposals.status_code == 200


def test_kg_endpoints(client, doctor_headers):
    stats = client.get("/api/v1/kg/stats", headers=doctor_headers).json()
    assert stats["total_nodes"] > 100
    d = client.get("/api/v1/diseases/ORPHA:915", headers=doctor_headers).json()
    assert d["disease"]["name"] == "Wilson disease"
    assert "ATP7B" in d["genes"]
    assert client.get("/api/v1/diseases/ORPHA:NOPE", headers=doctor_headers).status_code == 404


def test_emr_fhir_flow(client, doctor_headers):
    pid = client.post("/api/v1/patients",
                      json={"age_years": 11, "sex": "F", "state": "Chhattisgarh", "community": "Gond"},
                      headers=doctor_headers).json()["patient_id"]
    patient = client.get(f"/api/v1/emr/fhir/Patient/{pid}", headers=doctor_headers).json()
    assert patient["resourceType"] == "Patient"
    assert patient["address"][0]["country"] == "IN"

    bundle = client.post(f"/api/v1/emr/fhir/Bundle/{pid}?diagnosis_hpo=HP:0001878&drugs=primaquine",
                         headers=doctor_headers).json()
    kinds = {e["resource"]["resourceType"] for e in bundle["entry"]}
    assert {"Patient", "Observation", "Condition", "DetectedIssue"} <= kinds

    obs = client.post("/api/v1/emr/fhir/Observation",
                      json={"code": {"text": "HbA2", "coding": [{"system": fhir.LOINC, "code": "4547-6"}]},
                            "valueQuantity": {"value": 5.2, "unit": "%"}},
                      headers=doctor_headers).json()
    assert obs["parsed_values"]
    assert client.get("/api/v1/emr/fhir/metadata", headers=doctor_headers).status_code == 200


def test_fhir_mapping_units_and_severity():
    alert = {"drug": "primaquine", "gene": "G6PD", "severity": "critical", "recommendation": "avoid",
             "inferred_status": "deficient", "probability_of_risk_status": 0.07, "allele_frequency": 0.07}
    issue = fhir.to_fhir_detected_issue("PT-1", alert)
    assert issue["severity"] == "high"
    assert issue["patient"]["reference"] == "Patient/PT-1"

    obs = fhir.to_fhir_observations("PT-1", [{"hpo_id": "HP:0000952", "hpo_name": "Jaundice",
                                              "confidence": 0.9, "method": "dictionary",
                                              "evidence_text": "piliya"}])
    assert obs[0]["code"]["coding"][0]["system"] == fhir.HPO_SYSTEM
    assert obs[0]["subject"]["reference"] == "Patient/PT-1"
