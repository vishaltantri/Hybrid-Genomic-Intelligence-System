import os

os.environ.setdefault("GENOMIND_EMBED_MODEL", "none")

import pytest
from fastapi.testclient import TestClient

from backend.app import store
from backend.app.main import app
from backend.app.security import create_access_token
from test_pedigree import Fam, make_case

R = "/api/v1/repro"
P = "/api/v1/pedigree"


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "repro.sqlite3")
    store.init_db()


@pytest.fixture
def client():
    return TestClient(app)


def hdr(name="clinician", role="doctor"):
    return {"Authorization": f"Bearer {create_access_token(name, role)}"}


@pytest.fixture
def case(client):
    c = make_case(client, sex="F")
    assert client.post(f"{P}/{c}/demo-family", headers=hdr()).status_code == 200
    return c


def top(res):
    return next(r for r in res["risks"] if r["supported"] and r["probabilities"])


def test_carrier_table_and_mendelian_from_pedigree(client, case):
    res = client.get(f"{R}/case/{case}", headers=hdr()).json()
    assert res["available"] and len(res["partners"]) == 2
    assert all(p["variants"] for p in res["partners"])                      # recorded genotypes shown per partner
    wilson = next(r for r in res["risks"] if r["gene"] == "ATP7B")
    assert wilson["carrier_status"] == {"partner_a": "Carrier", "partner_b": "Carrier"}
    assert wilson["probabilities"]["child_affected"] > 0
    assert wilson["bayesian"]["partner_a"]["posterior"] is not None
    assert wilson["punnett"]["genotype_probabilities"] == {"AA": 0.25, "Aa": 0.5, "aa": 0.25}   # dynamic from carriers
    assert res["safety"]


def test_punnett_endpoint_and_validation(client):
    r = client.post(f"{R}/punnett", json={"parent_a": "Aa", "parent_b": "aa"}, headers=hdr()).json()
    assert r["outcome_probabilities"]["affected"] == 0.5
    assert client.post(f"{R}/punnett", json={"parent_a": "Aa", "parent_b": "XY"}, headers=hdr()).status_code == 422


def test_monte_carlo_is_reproducible_and_matches_analytic(client):
    body = {"p_a": 1.0, "p_b": 1.0, "n": 50000, "seed": 3}
    a = client.post(f"{R}/case/x/montecarlo", json=body, headers=hdr()).json()
    b = client.post(f"{R}/case/x/montecarlo", json=body, headers=hdr()).json()
    assert a["counts"] == b["counts"]
    lo, hi = a["affected_ci95"]
    assert lo <= 0.25 <= hi and a["analytic_affected_probability"] == 0.25
    assert abs(a["distribution"]["carrier"] - 0.5) < 0.02
    assert client.post(f"{R}/case/x/montecarlo", json={**body, "n": 10}, headers=hdr()).status_code == 422
    assert client.post(f"{R}/case/x/montecarlo", json={"p_a": 2, "p_b": 0.1}, headers=hdr()).status_code == 422


def test_case_monte_carlo_and_scenario_do_not_modify_case(client, case):
    res = client.get(f"{R}/case/{case}", headers=hdr()).json()
    did = next(r for r in res["risks"] if r["gene"] == "ATP7B")["disease_id"]
    mc = client.post(f"{R}/case/{case}/montecarlo", json={"disease_id": did, "n": 20000}, headers=hdr()).json()
    assert mc["disease_name"] and 0 <= mc["distribution"]["affected"] <= 1
    sc = client.post(f"{R}/case/{case}/scenario", json={"disease_id": did, "status_a": "carrier", "status_b": "not_carrier"}, headers=hdr()).json()
    assert sc["result"]["child_affected"] == 0 and sc["baseline"]["child_affected"] > 0
    assert client.get(f"{R}/case/{case}", headers=hdr()).json()["risks"] == res["risks"]


def test_missing_genotype_is_not_assumed_normal(client):
    c = make_case(client, sex="F")
    f = Fam(client, c)
    a = f.member("A", "M")
    b = f.member("B", "F")
    k = f.member("Kid", "F", proband=True)
    f.rel("partner", a, b)
    for p in (a, b):
        f.rel("parent", p, k)
    res = client.get(f"{R}/case/{c}", headers=hdr()).json()
    assert res["available"]
    assert not any(r["probabilities"] and r["probabilities"]["child_affected"] > 0 and r["carrier_status"]["partner_a"] == "Not a carrier" for r in res["risks"])
    for p in res["partners"]:
        assert p["variants"] == [] and "cannot be determined" in p["note"]


def test_no_pedigree_is_insufficient_data_not_an_error(client):
    c = make_case(client)
    r = client.get(f"{R}/case/{c}", headers=hdr())
    assert r.status_code == 200 and r.json()["available"] is False and "Insufficient" in r.json()["note"]
    assert client.get(f"{R}/case/nope", headers=hdr()).status_code == 404


def test_explain_report_section_and_ai_context(client, case):
    res = client.get(f"{R}/case/{case}", headers=hdr()).json()
    did = next(r for r in res["risks"] if r["gene"] == "ATP7B")["disease_id"]
    ex = client.get(f"{R}/case/{case}/explain", params={"disease_id": did}, headers=hdr()).json()
    assert ex["available"] and set(ex["sections"]) == {"what_we_know", "what_the_calculation_means", "what_remains_uncertain", "discuss_with_clinician"}
    rs = client.get(f"{R}/case/{case}/report-section", headers=hdr()).json()
    assert rs["available"] and rs["risks"] and rs["limitations"]
    chat = client.post("/api/v1/assistant/chat", json={"message": "Explain the reproductive risk", "patient_id": case, "include_repro": True}, headers=hdr())
    assert chat.status_code == 200
    assert any(c.get("source_type") == "reproductive" for c in chat.json().get("citations", []))


def test_authorization(client, case):
    assert client.get(f"{R}/case/{case}").status_code in (401, 403)
    assert client.get(f"{R}/case/{case}", headers=hdr("asha1", "asha")).status_code == 403
    assert client.get(f"{R}/case/{case}", headers=hdr("r", "researcher")).status_code == 403
