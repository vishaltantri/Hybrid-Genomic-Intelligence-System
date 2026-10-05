import os

os.environ.setdefault("GENOMIND_EMBED_MODEL", "none")

import pytest
from fastapi.testclient import TestClient

from backend.app import store
from backend.app.main import app
from backend.app.security import create_access_token

C = "/api/v1/community"


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "c.sqlite3")
    store.init_db()


@pytest.fixture
def client():
    return TestClient(app)


def hdr(name="clinician", role="doctor"):
    return {"Authorization": f"Bearer {create_access_token(name, role)}"}


ASHA = hdr("asha1", "asha")
BODY = {"transcript": "bachche ko daura aate hain aur peela pan hai", "age": 3, "state": "Uttar Pradesh", "district": "Lucknow", "village": "Rampur"}


def mk(client, h=ASHA, body=BODY):
    r = client.post(f"{C}/referrals/from-text", json=body, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_server_computes_colour_and_persists_with_hindi_and_due_date(client):
    r = mk(client)
    assert r["triage_color"] in ("yellow", "red") and r["status"] == "open" and r["created_by"] == "asha1"
    assert r["action"]["hi"] and r["action"]["en"] and r["follow_up_due"]
    assert "seizures" in r["triage"]["red_flags"]
    got = client.get(f"{C}/referrals/{r['referral_id']}", headers=ASHA).json()
    assert got["referral_id"] == r["referral_id"]
    green = mk(client, body={"transcript": "bachcha theek hai", "age": 5})
    assert green["triage_color"] == "green" and green["follow_up_due"] > r["follow_up_due"]


def test_asha_isolation_and_clinician_visibility(client):
    r = mk(client)
    other = hdr("asha2", "asha")
    assert client.get(f"{C}/referrals/{r['referral_id']}", headers=other).status_code == 404
    assert client.post(f"{C}/referrals/{r['referral_id']}/followup", json={"outcome": "improved"}, headers=other).status_code == 404
    assert client.get(f"{C}/referrals", headers=other).json() == []
    assert len(client.get(f"{C}/referrals", headers=hdr()).json()) == 1
    assert client.post(f"{C}/referrals/{r['referral_id']}/handoff", json={}, headers=ASHA).status_code == 403
    assert client.get(f"{C}/referrals", headers=hdr("p", "patient")).status_code == 403
    assert client.get(f"{C}/referrals").status_code in (401, 403)


def test_followup_lifecycle_overdue_and_summary(client):
    r = mk(client)
    rid = r["referral_id"]
    assert client.post(f"{C}/referrals/{rid}/followup", json={"outcome": "bogus"}, headers=ASHA).status_code == 422
    w = client.post(f"{C}/referrals/{rid}/followup", json={"outcome": "worse", "note": "fever"}, headers=ASHA).json()
    assert w["needs_review"] is True and w["followups"][0]["note"] == "fever"
    with store._connect() as conn:
        conn.execute("UPDATE referrals SET follow_up_due='2000-01-01T00:00:00Z' WHERE referral_id=?", (rid,))
    s = client.get(f"{C}/summary", headers=ASHA).json()
    assert s["total"] == 1 and s["overdue"] == 1 and s["needs_review"] == 1
    done = client.post(f"{C}/referrals/{rid}/followup", json={"outcome": "improved"}, headers=ASHA).json()
    assert done["status"] == "closed" and done["overdue"] is False and done["needs_review"] is False
    assert client.post(f"{C}/referrals/{rid}/followup", json={"outcome": "worse"}, headers=ASHA).status_code == 409


def test_clinician_handoff_creates_case_without_auto_confirming_phenotypes(client):
    r = mk(client)
    rid = r["referral_id"]
    assert client.post(f"{C}/referrals/{rid}/handoff", json={"confirm_hpo_ids": ["HP:9999999"]}, headers=hdr()).status_code == 422
    h = client.post(f"{C}/referrals/{rid}/handoff", json={}, headers=hdr()).json()
    pid = h["case_id"]
    assert h["phenotypes_confirmed"] == 0 and h["referral"]["status"] == "handed_off"
    assert store.get_patient(pid)["district"] == "Lucknow"
    assert [e["kind"] for e in store.list_events(pid)] == ["asha_referral"]
    assert client.post(f"{C}/referrals/{rid}/handoff", json={}, headers=hdr()).status_code == 409
    assert "referral.handoff" in {a["action"] for a in store.recent_audit(30)}


def test_handoff_confirms_only_reported_hpo(client):
    r = mk(client)
    ids = r["triage"]["hpo_ids"]
    if not ids:
        pytest.skip("transcript produced no HPO ids in this environment")
    h = client.post(f"{C}/referrals/{r['referral_id']}/handoff", json={"confirm_hpo_ids": ids[:1]}, headers=hdr()).json()
    assert h["phenotypes_confirmed"] == 1


def test_from_answers_path(client):
    q = client.get("/api/v1/triage/questionnaire", headers=ASHA).json()["questions"][0]["id"]
    r = client.post(f"{C}/referrals/from-answers", json={"answers": {q: "haan"}, "age": 2}, headers=ASHA)
    assert r.status_code == 200 and r.json()["triage"]["source"] == "questionnaire"
