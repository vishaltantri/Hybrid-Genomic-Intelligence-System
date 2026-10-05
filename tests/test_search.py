import os

os.environ.setdefault("GENOMIND_EMBED_MODEL", "none")

import pytest
from fastapi.testclient import TestClient

from backend.app import store
from backend.app.main import app
from backend.app.security import create_access_token

S = "/api/v1/search"
SEEDS = None


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "s.sqlite3")
    store.init_db()


@pytest.fixture
def client():
    return TestClient(app)


def hdr(name="clinician", role="doctor"):
    return {"Authorization": f"Bearer {create_access_token(name, role)}"}


def test_validation_and_auth(client):
    assert client.get(S, params={"q": "w"}).status_code in (401, 403)
    assert client.get(S, params={"q": "w"}, headers=hdr()).status_code == 422
    assert client.get(S, params={"q": "x" * 200}, headers=hdr()).status_code == 422
    assert client.get(S, params={"q": "wilson", "types": "bogus"}, headers=hdr()).status_code == 422


def test_kg_cases_reports_and_no_match_state(client):
    pid = client.post("/api/v1/patients", json={"age_years": 5, "sex": "M", "state": "Kerala", "community": "General"}, headers=hdr()).json()["patient_id"]
    rep = client.post(f"/api/v1/reports/case/{pid}", json={"sections": ["patient"]}, headers=hdr()).json()
    r = client.get(S, params={"q": "wilson"}, headers=hdr()).json()
    assert any("Wilson" in h["label"] for h in r["results"]["diseases"])
    assert any(h["id"] == pid for h in client.get(S, params={"q": pid}, headers=hdr()).json()["results"]["cases"])
    assert client.get(S, params={"q": rep["report_id"]}, headers=hdr()).json()["results"]["reports"][0]["context"]["patient_id"] == pid
    none = client.get(S, params={"q": "zzzqqq"}, headers=hdr()).json()
    assert none["total"] == 0 and none["state"] == "No matching result"
    assert "search.query" in {a["action"] for a in store.recent_audit(20)}


def test_variant_search(client):
    from pathlib import Path
    vcf = next(Path(__file__).resolve().parents[1].rglob("clinical_sample_trio.vcf"))
    pid = client.post("/api/v1/patients", json={"age_years": 5, "sex": "M", "state": "Kerala", "community": "General"}, headers=hdr()).json()["patient_id"]
    up = client.post("/api/v1/variants/upload", files={"file": ("t.vcf", vcf.read_bytes())}, data={"patient_id": pid}, headers=hdr())
    assert up.status_code == 200, up.text
    gene = next(v["gene_symbol"] for v in up.json()["variants"] if v.get("gene_symbol"))
    hits = client.get(S, params={"q": gene, "types": "variants"}, headers=hdr()).json()["results"]["variants"]
    assert hits and hits[0]["context"]["patient_id"] == pid


def test_role_scoping(client):
    store.create_user  # noqa
    client.post("/api/v1/patients", json={"age_years": 5, "sex": "M", "state": "Kerala", "community": "General"}, headers=hdr())
    asha = client.get(S, params={"q": "Kerala"}, headers=hdr("a1", "asha")).json()
    assert "cases" not in asha["results"] and "cases" in asha["not_permitted"]
    pat = client.get(S, params={"q": "wilson"}, headers=hdr("p", "patient")).json()
    assert "diseases" not in pat["results"] and "diseases" in pat["not_permitted"]
    cmds = {h["id"] for h in client.get(S, params={"q": "re"}, headers=hdr("p", "patient")).json()["results"]["commands"]}
    assert "repro" not in cmds and "variants" not in cmds
    assert "asha" in {h["id"] for h in client.get(S, params={"q": "asha"}, headers=hdr("a1", "asha")).json()["results"]["commands"]}


def test_asha_sees_only_own_referrals(client):
    a1, a2 = hdr("a1", "asha"), hdr("a2", "asha")
    body = {"transcript": "bachche ko daura aate hain aur peela pan hai", "village": "Rampur"}
    rid = client.post("/api/v1/community/referrals/from-text", json=body, headers=a1).json()["referral_id"]
    assert client.get(S, params={"q": "Rampur"}, headers=a1).json()["results"]["referrals"][0]["id"] == rid
    assert client.get(S, params={"q": "Rampur"}, headers=a2).json()["results"]["referrals"] == []
    assert client.get(S, params={"q": "Rampur"}, headers=hdr()).json()["results"]["referrals"][0]["id"] == rid
