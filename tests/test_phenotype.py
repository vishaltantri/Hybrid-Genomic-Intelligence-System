"""Phase 7: phenotype / HPO intelligence."""
import os

os.environ.setdefault("GENOMIND_EMBED_MODEL", "none")

import pytest
from fastapi.testclient import TestClient

from backend.app import store
from backend.app.main import app
from backend.app.security import create_access_token


@pytest.fixture
def client():
    return TestClient(app)


def hdr(name="clinician", role="doctor"):
    return {"Authorization": f"Bearer {create_access_token(name, role)}"}


def mkcase(client, name="Pheno Case"):
    r = client.post("/api/v1/patients", json={"name": name, "age": 12, "sex": "F", "state": "Kerala", "community": "General"}, headers=hdr())
    assert r.status_code in (200, 201), r.text
    return r.json()["patient_id"]


def S(client, q):
    r = client.get("/api/v1/phenotype/search", params={"q": q}, headers=hdr())
    assert r.status_code == 200, r.text
    return r.json()["results"]


def test_search_by_name_id_synonym_and_hindi(client):
    assert S(client, "tremor")[0]["hpo_id"] == "HP:0001337" and S(client, "tremor")[0]["match"] == "name"
    assert S(client, "HP:0001337")[0]["match"] == "id"
    h = [r for r in S(client, "piliya") if r["hpo_id"] == "HP:0000952"]
    assert h and h[0]["match"] in ("synonym", "indian_synonym") and h[0]["matched_text"] == "piliya"


def test_semantic_results_carry_mapper_score_only(client):
    sem = [r for r in S(client, "yellow skin and eyes") if r["match"] == "semantic"]
    assert sem and all(isinstance(r["score"], float) and r["source"] for r in sem)
    assert all("score" not in r for r in S(client, "tremor") if r["match"] != "semantic")


def test_search_validation_and_rbac(client):
    assert client.get("/api/v1/phenotype/search", params={"q": "x"}, headers=hdr()).status_code == 422
    assert client.get("/api/v1/phenotype/search", params={"q": "x" * 201}, headers=hdr()).status_code == 422
    assert client.get("/api/v1/phenotype/search", params={"q": "tremor"}).status_code in (401, 403)
    assert client.get("/api/v1/phenotype/search", params={"q": "tremor"}, headers=hdr("p", "patient")).status_code == 403
    assert client.get("/api/v1/phenotype/search", params={"q": "tremor"}, headers=hdr("r", "researcher")).status_code == 403
    assert S(client, "qqzzxxww")[0:0] == []


def test_term_detail_hierarchy_and_diseases(client):
    j = client.get("/api/v1/phenotype/term/HP:0001337", headers=hdr()).json()
    assert j["name"] == "Tremor" and j["definition"] and j["ancestors"]
    assert any(d["disease_id"] == "ORPHA:915" and "ATP7B" in d["genes"] for d in j["diseases"])
    assert client.get("/api/v1/phenotype/term/HP:9999999", headers=hdr()).status_code == 404
    assert client.get("/api/v1/phenotype/term/bad", headers=hdr()).status_code == 422


def test_case_not_documented_and_empty_state(client):
    pid = mkcase(client)
    j = client.get(f"/api/v1/phenotype/case/{pid}", headers=hdr()).json()
    assert j["observed"] == [] and j["top_diagnoses"] == [] and "Insufficient evidence" in j["diagnosis_note"]
    assert client.get("/api/v1/phenotype/case/NOPE", headers=hdr()).status_code == 404


def test_import_requires_confirmation_payload_and_updates_case(client):
    pid = mkcase(client, "Import Case")
    items = [{"hpo_id": "HP:0001337", "assertion": "present", "onset": "6 months", "severity": "Moderate"},
             {"hpo_id": "HP:0000952", "assertion": "present"},
             {"hpo_id": "HP:0001250", "assertion": "absent"},
             {"hpo_id": "HP:0001945", "assertion": "possible"}]
    r = client.post(f"/api/v1/phenotype/case/{pid}/import", json={"items": items}, headers=hdr())
    assert r.status_code == 200 and r.json()["present"] == 2 and r.json()["negated_or_uncertain"] == 2
    j = client.get(f"/api/v1/phenotype/case/{pid}", headers=hdr()).json()
    obs = {o["hpo_id"]: o for o in j["observed"]}
    assert set(obs) == {"HP:0001337", "HP:0000952"} and obs["HP:0001337"]["onset"] == "6 months"
    assert obs["HP:0000952"]["onset"] == "Not documented"
    assert [n["hpo_id"] for n in j["negated"]] == ["HP:0001250"] and [u["hpo_id"] for u in j["uncertain"]] == ["HP:0001945"]
    assert j["top_diagnoses"] and j["not_documented"] and all(n["status"] == "Not documented" for n in j["not_documented"])
    assert j["conflicts"] == []
    # uncertain / negated terms are not fed to the diagnosis engine
    from backend.app.services import registry
    assert registry.twin.load_core(pid)["hpo_ids"] == ["HP:0000952", "HP:0001337"]
    assert any(e["kind"] == "phenotype_assertions" for e in store.list_events(pid))


def test_negation_removes_previously_observed_term(client):
    pid = mkcase(client, "Negate Case")
    client.post(f"/api/v1/phenotype/case/{pid}/import", json={"items": [{"hpo_id": "HP:0001337", "assertion": "present"}]}, headers=hdr())
    client.post(f"/api/v1/phenotype/case/{pid}/import", json={"items": [{"hpo_id": "HP:0001337", "assertion": "absent"}]}, headers=hdr())
    j = client.get(f"/api/v1/phenotype/case/{pid}", headers=hdr()).json()
    assert j["observed"] == [] and [n["hpo_id"] for n in j["negated"]] == ["HP:0001337"]


def test_import_validation_and_rbac(client):
    pid = mkcase(client, "Val Case")
    u = f"/api/v1/phenotype/case/{pid}/import"
    assert client.post(u, json={"items": []}, headers=hdr()).status_code == 422
    assert client.post(u, json={"items": [{"hpo_id": "bad", "assertion": "present"}]}, headers=hdr()).status_code == 422
    assert client.post(u, json={"items": [{"hpo_id": "HP:0001337", "assertion": "maybe"}]}, headers=hdr()).status_code == 422
    assert client.post(u, json={"items": [{"hpo_id": "HP:9999999", "assertion": "present"}]}, headers=hdr()).status_code == 422
    assert client.post("/api/v1/phenotype/case/NOPE/import", json={"items": [{"hpo_id": "HP:0001337", "assertion": "present"}]}, headers=hdr()).status_code == 404
    assert client.post(u, json={"items": [{"hpo_id": "HP:0001337", "assertion": "present"}]}, headers=hdr("p", "patient")).status_code == 403
    assert store.list_events(pid) == []


def test_compare_uses_engine_and_separates_absent_from_undocumented(client):
    pid = mkcase(client, "Compare Case")
    client.post(f"/api/v1/phenotype/case/{pid}/import", json={"items": [
        {"hpo_id": "HP:0001337", "assertion": "present"}, {"hpo_id": "HP:0000952", "assertion": "present"},
        {"hpo_id": "HP:0000616", "assertion": "absent"}]}, headers=hdr())
    j = client.get(f"/api/v1/phenotype/case/{pid}/compare", params={"disease_id": "ORPHA:915"}, headers=hdr()).json()
    assert j["disease_name"] == "Wilson disease" and j["matched"] and j["score"]["probability"] > 0
    assert [a["hpo_id"] for a in j["explicitly_absent"]] == ["HP:0000616"]
    assert "HP:0000616" not in [n["hpo_id"] for n in j["not_documented"]]
    assert j["genes"] == ["ATP7B"] and j["case_variants"] == [] and j["variant_note"].startswith("Not analyzed")
    assert client.get(f"/api/v1/phenotype/case/{pid}/compare", params={"disease_id": "ORPHA:0"}, headers=hdr()).status_code == 404
