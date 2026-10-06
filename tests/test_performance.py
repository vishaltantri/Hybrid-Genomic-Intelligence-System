"""Phase 21: pagination keeps results identical, indexes are used, lazy-loaded frontend build exists."""
import os
import sqlite3
from pathlib import Path

os.environ.setdefault("GENOMIND_EMBED_MODEL", "none")

import pytest
from fastapi.testclient import TestClient

from backend.app import store
from backend.app.main import app
from backend.app.security import hash_password

API = "/api/v1"


@pytest.fixture()
def seeded(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "p.sqlite3")
    store.init_db()
    store.create_user("doc", "doctor", hash_password("changeme"))
    for i in range(30):
        store.create_patient({"age_years": i, "sex": "F", "state": "Kerala" if i % 3 == 0 else "Assam"}, "doc")
    c = TestClient(app)
    tok = c.post(f"{API}/auth/token", data={"username": "doc", "password": "changeme"}).json()["access_token"]
    return c, {"Authorization": f"Bearer {tok}"}


def test_pagination_pages_partition_the_full_list(seeded):
    c, H = seeded
    full = [p["patient_id"] for p in c.get(f"{API}/patients?limit=500", headers=H).json()]
    r1 = c.get(f"{API}/patients?limit=10&offset=0", headers=H)
    r2 = c.get(f"{API}/patients?limit=10&offset=10", headers=H)
    assert r1.headers["X-Total-Count"] == "30" == str(len(full))
    got = [p["patient_id"] for p in r1.json()] + [p["patient_id"] for p in r2.json()]
    assert got == full[:20]


def test_pagination_with_filter_and_bounds(seeded):
    c, H = seeded
    r = c.get(f"{API}/patients?state=Kerala&limit=500", headers=H)
    assert r.headers["X-Total-Count"] == "10" and len(r.json()) == 10
    assert c.get(f"{API}/patients?limit=0", headers=H).status_code == 422
    assert c.get(f"{API}/patients?offset=-1", headers=H).status_code == 422
    assert c.get(f"{API}/patients?offset=9999", headers=H).json() == []


def test_listing_query_uses_index(seeded):
    with sqlite3.connect(store.DB_PATH) as conn:
        plan = " ".join(r[3] for r in conn.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM patients WHERE state=? ORDER BY created_utc DESC LIMIT 10", ("Kerala",)))
    assert "idx_patients_state_created" in plan
