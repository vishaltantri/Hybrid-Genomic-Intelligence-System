"""Phase 20 QA gate: workflow across Phases 16-19 over real HTTP, negative cases, and measured latency budgets."""
import os
import time

os.environ.setdefault("GENOMIND_EMBED_MODEL", "none")

import pytest
from fastapi.testclient import TestClient

from backend.app import store
from backend.app.main import app
from backend.app.security import hash_password

API = "/api/v1"


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "qa.sqlite3")
    store.init_db()
    store.create_user("doc", "doctor", hash_password("changeme"))


def _auth(c):
    r = c.post(f"{API}/auth/token", data={"username": "doc", "password": "changeme"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_e2e_case_to_analytics_to_ml_registry():
    c = TestClient(app)
    H = _auth(c)
    pid = c.post(f"{API}/patients", json={"age_years": 7, "sex": "M", "state": "Kerala", "community": "Nair"}, headers=H).json()["patient_id"]
    assert c.get(f"{API}/patients/{pid}", headers=H).status_code == 200
    ov = c.get(f"{API}/analytics/overview", headers=H)
    assert ov.status_code == 200
    reg = c.get(f"{API}/ml/registry", headers=H).json()
    assert reg["available"] and any(m["id"] == "diagnosis_engine" for m in reg["models"])
    assert c.get(f"{API}/ml/benchmark", headers=H).status_code == 200


@pytest.mark.parametrize("method,path", [("get", "/analytics/overview"), ("get", "/ml/registry"), ("get", "/patients"), ("get", "/variants/analyses")])
def test_unauthenticated_rejected(method, path):
    assert getattr(TestClient(app), method)(API + path).status_code in (401, 403, 404, 405)


def test_negative_inputs():
    c = TestClient(app)
    H = _auth(c)
    assert c.get(f"{API}/analytics/timeseries", params={"metric": "x" * 200}, headers=H).status_code in (400, 422)
    assert c.get(f"{API}/patients/NOPE-404", headers=H).status_code == 404
    assert c.post(f"{API}/patients", json={"age_years": "abc"}, headers=H).status_code == 422
    bad = c.post(f"{API}/auth/token", data={"username": "doc", "password": "wrong"})
    assert bad.status_code in (400, 401)
    assert c.get(f"{API}/analytics/overview", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_latency_budgets():
    c = TestClient(app)
    H = _auth(c)
    for path, budget in (("/analytics/overview", 2.0), ("/ml/registry", 0.5), ("/patients", 1.0)):
        t = time.perf_counter()
        r = c.get(API + path, headers=H)
        dt = time.perf_counter() - t
        assert r.status_code == 200 and dt < budget, (path, dt)
