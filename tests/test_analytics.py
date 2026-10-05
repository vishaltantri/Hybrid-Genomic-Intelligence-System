"""Phase 16 analytics: real aggregates, honest empty states, role restrictions, export safety."""
import os

os.environ.setdefault("GENOMIND_EMBED_MODEL", "none")

import pytest
from fastapi.testclient import TestClient

from backend.app import analytics, store
from backend.app.main import app
from backend.app.security import hash_password
from ml_services.config import SEEDS_DIR

API = "/api/v1/analytics"


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "an.sqlite3")
    store.init_db()
    analytics.clear_cache()
    for u, r in (("doc", "doctor"), ("res", "researcher"), ("pat", "patient"), ("ash", "asha")):
        store.create_user(u, r, hash_password("password1"))
    yield
    analytics.clear_cache()


def hdr(c, u):
    t = c.post("/api/v1/auth/token", data={"username": u, "password": "password1"}).json()["access_token"]
    return {"Authorization": f"Bearer {t}"}


def test_empty_database_is_honest():
    c = TestClient(app)
    H = hdr(c, "doc")
    o = c.get(f"{API}/overview", headers=H).json()
    assert o["metrics"]["total_cases"] == 0 and o["metrics"]["reports_generated"] == 0
    ts = c.get(f"{API}/timeseries", params={"metric": "cases"}, headers=H).json()
    assert ts["points"] == [] and ts["state"] == "No data in range"
    assert c.get(f"{API}/phenotypes", headers=H).json()["state"] == "No phenotyped cases in range"
    assert c.get(f"{API}/phenotypes", headers=H).json()["coverage_pct"] is None


def test_counts_come_from_real_rows_and_model_score_is_separate():
    c = TestClient(app)
    H = hdr(c, "doc")
    pids = [c.post("/api/v1/patients", json={"age_years": 5, "sex": "F"}, headers=H).json()["patient_id"] for _ in range(3)]
    c.post(f"/api/v1/phenotype/case/{pids[0]}/import", json={"items": [{"hpo_id": "HP:0001337", "assertion": "present"}]}, headers=H)
    c.post("/api/v1/workflow/case/%s/status" % pids[1], json={"status": "in_review"}, headers=H)
    analytics.clear_cache()
    o = c.get(f"{API}/overview", headers=H).json()
    assert o["metrics"]["total_cases"] == 3 and o["metrics"]["pending_reviews"] == 1
    assert o["metrics"]["active_cases"] == 3 and o["metrics"]["completed_cases"] == 0
    ph = c.get(f"{API}/phenotypes", headers=H).json()
    assert ph["cases_with_phenotypes"] == 1 and ph["coverage_pct"] == 33.3
    assert ph["cooccurrence"] is None and ph["cooccurrence_state"].startswith("Insufficient data")
    dx = c.get(f"{API}/diagnoses", headers=H).json()
    assert dx["unresolved"]["no_diagnosis_run"] == 3
    assert "not a clinical diagnosis" in dx["note"].lower()
    assert "Model score" in dx["model_score"]["label"]


def test_variant_analytics_and_privacy():
    c = TestClient(app)
    H = hdr(c, "doc")
    pid = c.post("/api/v1/patients", json={"age_years": 5, "sex": "M"}, headers=H).json()["patient_id"]
    vcf = (SEEDS_DIR / "clinical_sample_trio.vcf").read_text()
    assert c.post("/api/v1/variants/upload", files={"file": ("t.vcf", vcf)}, data={"patient_id": pid}, headers=H).status_code == 200
    analytics.clear_cache()
    v = c.get(f"{API}/variants", headers=H).json()
    assert v["total_variants"] > 0 and sum(r["count"] for r in v["acmg"]) == v["total_variants"]
    assert v["reviewed"] + v["unreviewed"] == v["total_variants"]
    assert pid not in c.get(f"{API}/variants", headers=H).text            # no identifiers
    assert pid not in c.get(f"{API}/export", params={"section": "overview", "format": "json"}, headers=H).text


def test_researcher_small_cell_suppression_and_no_cooccurrence():
    c = TestClient(app)
    D, R = hdr(c, "doc"), hdr(c, "res")
    pid = c.post("/api/v1/patients", json={"age_years": 5, "sex": "M"}, headers=D).json()["patient_id"]
    c.post(f"/api/v1/phenotype/case/{pid}/import", json={"items": [{"hpo_id": "HP:0001337", "assertion": "present"}]}, headers=D)
    analytics.clear_cache()
    assert c.get(f"{API}/phenotypes", headers=D).json()["frequencies"]
    p = c.get(f"{API}/phenotypes", headers=R).json()
    assert p["frequencies"] == [] and p["frequencies_suppressed"] == 1
    assert p["cooccurrence_state"].startswith("Not available")
    assert p["privacy"]["small_cell_suppression"] == analytics.MIN_CELL


def test_role_restrictions():
    c = TestClient(app)
    assert c.get(f"{API}/overview").status_code == 401
    for u in ("pat", "ash"):
        assert c.get(f"{API}/overview", headers=hdr(c, u)).status_code == 403
        assert c.get(f"{API}/export", params={"section": "overview"}, headers=hdr(c, u)).status_code == 403


def test_validation_and_export():
    c = TestClient(app)
    H = hdr(c, "doc")
    assert c.get(f"{API}/overview", params={"from": "2026-13-01"}, headers=H).status_code == 422
    assert c.get(f"{API}/overview", params={"from": "2026-05-02", "to": "2026-05-01"}, headers=H).status_code == 422
    assert c.get(f"{API}/timeseries", params={"metric": "nope"}, headers=H).status_code == 422
    assert c.get(f"{API}/timeseries", params={"interval": "year"}, headers=H).status_code == 422
    assert c.get(f"{API}/export", params={"section": "users"}, headers=H).status_code == 422
    r = c.get(f"{API}/export", params={"section": "overview", "format": "csv"}, headers=H)
    assert r.status_code == 200 and r.text.startswith("series,label,count") and "attachment" in r.headers["content-disposition"]
    assert any(a["action"] == "analytics.export" for a in store.recent_audit(5))
    assert analytics.to_csv([{"label": "=cmd()", "count": 1}], ["label", "count"]).splitlines()[1].startswith("'=")


def test_date_range_filters_and_timeseries_buckets():
    c = TestClient(app)
    H = hdr(c, "doc")
    for _ in range(2):
        c.post("/api/v1/patients", json={"age_years": 5, "sex": "F"}, headers=H)
    analytics.clear_cache()
    assert c.get(f"{API}/overview", params={"from": "2000-01-01", "to": "2000-12-31"}, headers=H).json()["metrics"]["total_cases"] == 0
    ts = c.get(f"{API}/timeseries", params={"metric": "cases", "interval": "month"}, headers=H).json()
    assert ts["total"] == 2 and "Insufficient data" in ts["state"]
