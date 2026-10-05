import os

os.environ.setdefault("GENOMIND_EMBED_MODEL", "none")

import pytest
from fastapi.testclient import TestClient

from backend.app import store
from backend.app.main import app
from backend.app.security import create_access_token, hash_password

W = "/api/v1/workflow"


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "w.sqlite3")
    store.init_db()
    for name, role in (("clinician", "doctor"), ("drb", "doctor"), ("asha1", "asha")):
        store.create_user(name, role, hash_password("x" * 8))


@pytest.fixture
def client():
    return TestClient(app)


def hdr(name="clinician", role="doctor"):
    return {"Authorization": f"Bearer {create_access_token(name, role)}"}


@pytest.fixture
def case(client):
    return client.post("/api/v1/patients", json={"age_years": 5, "sex": "M", "state": "Kerala", "community": "General"}, headers=hdr()).json()["patient_id"]


def test_status_transitions_and_history(client, case):
    assert client.get(f"{W}/case/{case}", headers=hdr()).json()["status"] == "new"
    assert client.post(f"{W}/case/{case}/status", json={"status": "report_ready"}, headers=hdr()).status_code == 409   # new -> report_ready not allowed
    assert client.post(f"{W}/case/{case}/status", json={"status": "bogus"}, headers=hdr()).status_code == 422
    r = client.post(f"{W}/case/{case}/status", json={"status": "in_review", "note": "starting"}, headers=hdr()).json()
    assert r["status"] == "in_review" and r["history"][0]["from_value"] == "new" and r["history"][0]["actor"] == "clinician"
    assert client.post(f"{W}/case/{case}/status", json={"status": "in_review"}, headers=hdr()).status_code == 409
    assert "report_ready" in client.get(f"{W}/case/{case}", headers=hdr()).json()["allowed_next"]
    assert client.get(f"{W}/case/NOPE", headers=hdr()).status_code == 404
    assert "workflow.status" in {a["action"] for a in store.recent_audit(20)}


def test_assignment_notifies_only_the_assignee_and_read_state_is_per_user(client, case):
    assert client.post(f"{W}/case/{case}/assign", json={"assignee": "ghost"}, headers=hdr()).status_code == 422
    assert client.post(f"{W}/case/{case}/assign", json={"assignee": "asha1"}, headers=hdr()).status_code == 422   # not a clinician
    client.post(f"{W}/case/{case}/assign", json={"assignee": "drb", "note": "please review"}, headers=hdr())
    mine = client.get(f"{W}/notifications", headers=hdr("drb", "doctor")).json()
    assert len(mine) == 1 and mine[0]["kind"] == "assignment" and mine[0]["case_id"] == case and mine[0]["read_utc"] is None
    assert client.get(f"{W}/notifications", headers=hdr()).json() == []                              # assigner gets nothing
    assert client.get(f"{W}/notifications/count", headers=hdr("drb", "doctor")).json() == {"unread": 1}
    nid = mine[0]["id"]
    assert client.post(f"{W}/notifications/{nid}/read", headers=hdr()).status_code == 404            # foreign id
    assert client.post(f"{W}/notifications/{nid}/read", headers=hdr("drb", "doctor")).status_code == 200
    assert client.get(f"{W}/notifications/count", headers=hdr("drb", "doctor")).json() == {"unread": 0}
    assert client.get(f"{W}/notifications?unread=true", headers=hdr("drb", "doctor")).json() == []
    assert [q["case_id"] for q in client.get(f"{W}/queue?mine=true", headers=hdr("drb", "doctor")).json()] == [case]
    assert client.get(f"{W}/queue?mine=true", headers=hdr()).json() == []


def test_role_broadcast_read_state_is_independent_per_doctor(client):
    store.notify("referral", "Broadcast", recipient_role="doctor")
    assert client.get(f"{W}/notifications/count", headers=hdr()).json()["unread"] == 1
    assert client.get(f"{W}/notifications/count", headers=hdr("drb", "doctor")).json()["unread"] == 1
    assert client.post(f"{W}/notifications/read-all", headers=hdr()).json()["marked"] == 1
    assert client.get(f"{W}/notifications/count", headers=hdr()).json()["unread"] == 0
    assert client.get(f"{W}/notifications/count", headers=hdr("drb", "doctor")).json()["unread"] == 1   # other doctor unaffected
    assert client.get(f"{W}/notifications", headers=hdr("asha1", "asha")).json() == []                   # other role sees nothing


def test_asha_referral_and_report_finalize_generate_real_notifications(client, case):
    asha = hdr("asha1", "asha")
    client.post("/api/v1/community/referrals/from-text", json={"transcript": "bachche ko daura aate hain aur peela pan hai", "village": "Rampur"}, headers=asha)
    docs = client.get(f"{W}/notifications", headers=hdr()).json()
    assert any(n["kind"] == "referral" and "Rampur" in n["body"] for n in docs)
    client.post(f"{W}/case/{case}/assign", json={"assignee": "drb"}, headers=hdr())
    rep = client.post(f"/api/v1/reports/case/{case}", json={"sections": ["patient"]}, headers=hdr()).json()
    client.post(f"/api/v1/reports/{rep['report_id']}/finalize", headers=hdr())
    kinds = [n["kind"] for n in client.get(f"{W}/notifications", headers=hdr("drb", "doctor")).json()]
    assert "report_final" in kinds and "assignment" in kinds


def test_authorization(client, case):
    assert client.get(f"{W}/notifications").status_code in (401, 403)
    assert client.get(f"{W}/case/{case}", headers=hdr("asha1", "asha")).status_code == 403            # no case access for ASHA
    assert client.get(f"{W}/queue", headers=hdr("p", "patient")).status_code == 403
    assert client.post(f"{W}/case/{case}/status", json={"status": "in_review"}, headers=hdr("asha1", "asha")).status_code == 403
    assert client.get(f"{W}/notifications", headers=hdr("asha1", "asha")).status_code == 200
