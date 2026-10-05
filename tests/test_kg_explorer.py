"""Phase 6: knowledge graph explorer (search, neighbourhood, paths, case isolation, malformed input)."""
import os

os.environ.setdefault("GENOMIND_EMBED_MODEL", "none")

import pytest
from fastapi.testclient import TestClient

from backend.app import store
from backend.app.main import app
from backend.app.security import create_access_token
from backend.app.services import registry


@pytest.fixture
def client():
    return TestClient(app)


def hdr(name="clinician", role="doctor"):
    return {"Authorization": f"Bearer {create_access_token(name, role)}"}


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "t.db")
    store.init_db()


def test_types_and_unsupported(client):
    j = client.get("/api/v1/kg/types", headers=hdr()).json()
    assert j["node_types"]["Disease"] == 19 and "Pathway" in j["unsupported"]


def test_search_exact_synonym_and_filter(client):
    r = client.get("/api/v1/kg/search", params={"q": "ATP7B"}, headers=hdr()).json()
    assert r["results"][0]["key"] == "Gene::ATP7B" and r["results"][0]["match"] == "exact"
    r = client.get("/api/v1/kg/search", params={"q": "wilson", "types": "Disease"}, headers=hdr()).json()
    assert r["results"] and all(x["type"] == "Disease" for x in r["results"])
    assert client.get("/api/v1/kg/search", params={"q": "zzzzqqqq"}, headers=hdr()).json()["total"] == 0


def test_malformed_queries(client):
    h = hdr()
    assert client.get("/api/v1/kg/search", params={"q": "a"}, headers=h).status_code == 422
    assert client.get("/api/v1/kg/search", params={"q": "x" * 101}, headers=h).status_code == 422
    assert client.get("/api/v1/kg/node", params={"key": "nokey"}, headers=h).status_code == 422
    assert client.get("/api/v1/kg/node", params={"key": "Gene::NOPE"}, headers=h).status_code == 404
    assert client.get("/api/v1/kg/neighborhood", params={"key": "Gene::ATP7B", "depth": 9}, headers=h).status_code == 422
    assert client.get("/api/v1/kg/path", params={"source": "Gene::ATP7B", "target": "::"}, headers=h).status_code == 422


def test_node_detail_matches_graph(client):
    n = client.get("/api/v1/kg/node", params={"key": "Gene::ATP7B"}, headers=hdr()).json()
    deg = len(registry.graph.edges_from("ATP7B")) + len(registry.graph.edges_to("ATP7B"))
    assert n["degree"] == deg and n["type"] == "Gene"


def test_neighborhood_is_bounded_and_real(client):
    h = hdr()
    r = client.get("/api/v1/kg/neighborhood", params={"key": "Hpo::HP:0000001", "depth": 3, "max_nodes": 10}, headers=h).json()
    assert len(r["nodes"]) <= 10 and r["truncated"] is True
    keys = {n["key"] for n in r["nodes"]}
    assert all(e["source"] in keys and e["target"] in keys for e in r["edges"])
    r = client.get("/api/v1/kg/neighborhood", params={"key": "Gene::ATP7B", "node_types": "Disease"}, headers=h).json()
    assert {n["type"] for n in r["nodes"]} <= {"Gene", "Disease"}


def test_paths_gene_to_phenotype_exist_via_disease(client):
    h = hdr()
    wd = next(n for n in registry.graph.by_type("Disease") if "wilson" in n["name"].lower())
    ph = registry.graph.edges_from(wd["id"], "HAS_PHENOTYPE")[0]["dst"]
    r = client.get("/api/v1/kg/path", params={"source": "Gene::ATP7B", "target": f"Hpo::{ph}"}, headers=h).json()
    assert r["status"] == "found" and r["paths"][0]["length"] == 2
    assert [n["key"] for n in r["paths"][0]["nodes"]][1] == f"Disease::{wd['id']}"
    r = client.get("/api/v1/kg/path", params={"source": "Gene::ATP7B", "target": f"Hpo::{ph}", "max_len": 1}, headers=h).json()
    assert r["status"] == "no_path" and r["message"]


def test_rbac(client):
    assert client.get("/api/v1/kg/types").status_code in (401, 403)
    assert client.get("/api/v1/kg/types", headers=hdr("p", "patient")).status_code == 403
    assert client.get("/api/v1/kg/types", headers=hdr("r", "researcher")).status_code == 200
    # a researcher can browse the KG but never a patient case
    assert client.get("/api/v1/kg/case/ANY", headers=hdr("r", "researcher")).status_code == 403


def test_case_graph_isolation_and_unknown(client, db):
    h = hdr()
    assert client.get("/api/v1/kg/case/NOPE", headers=h).status_code == 404
    for pid, hpo in (("KG-A", "HP:0001337"), ("KG-B", "HP:0001250")):
        r = client.post("/api/v1/patients", json={"patient_id": pid, "age_years": 9, "sex": "F", "state": "Kerala"}, headers=h)
        assert r.status_code in (200, 201), r.text
        store.add_event(pid, "hpo_profile", {"hpo_profile": [{"hpo_id": hpo}]})
    a = client.get("/api/v1/kg/case/KG-A", headers=h).json()
    b = client.get("/api/v1/kg/case/KG-B", headers=h).json()
    ka = {n["key"] for n in a["nodes"]}
    kb = {n["key"] for n in b["nodes"]}
    assert "Patient::KG-A" in ka and "Patient::KG-B" not in ka
    assert "Hpo::HP:0001337" in ka and "Hpo::HP:0001250" not in ka
    assert "Hpo::HP:0001250" in kb and "Hpo::HP:0001337" not in kb
    assert all(n["case"] for n in a["nodes"] if n["type"] == "Patient")
    assert any("Pathway" in x for x in a["notes"])


def test_assistant_graph_context(client):
    j = client.post("/api/v1/assistant/chat", json={"message": "What links ATP7B to disease?", "graph_node": "Gene::ATP7B"}, headers=hdr())
    assert j.status_code == 200
    assert any(c.get("source_type") == "knowledge_graph" for c in j.json()["citations"])
    assert client.post("/api/v1/assistant/chat", json={"message": "x", "graph_node": "bad"}, headers=hdr()).status_code == 422
