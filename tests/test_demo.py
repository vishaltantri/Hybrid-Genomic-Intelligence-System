"""Phase 24: the demo case is built by real services, labelled synthetic everywhere, secured normally, and resettable safely."""
import os

os.environ.setdefault("GENOMIND_EMBED_MODEL", "none")

import pytest
from fastapi.testclient import TestClient

from backend.app import demo, store
from backend.app.main import app
from backend.app.security import hash_password

API = "/api/v1"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "demo.sqlite3")
    store.init_db()
    from backend.app.services import registry
    registry.variants._analyses.clear()          # analyses are cached in memory; each test starts from this test's empty database
    for u, role in (("doc", "doctor"), ("doc2", "doctor"), ("asha1", "asha"), ("adm", "admin")):
        store.create_user(u, role, hash_password("changeme"))
    c = TestClient(app)

    def hdr(u):
        t = c.post(f"{API}/auth/token", data={"username": u, "password": "changeme"}).json()["access_token"]
        return {"Authorization": f"Bearer {t}"}
    return c, hdr


def test_requires_auth_and_permission(env):
    c, hdr = env
    assert c.get(f"{API}/demo/status").status_code == 401
    assert c.post(f"{API}/demo/seed", headers=hdr("asha1")).status_code == 403
    assert c.post(f"{API}/demo/reset", headers=hdr("asha1")).status_code == 403


def test_status_before_seed_is_honest(env):
    c, hdr = env
    s = c.get(f"{API}/demo/status", headers=hdr("doc")).json()
    assert s["exists"] is False and s["steps"] == [] and "Sample" in s["banner"]


def test_seed_builds_coherent_case_through_real_modules(env):
    c, hdr = env
    H = hdr("doc")
    s = c.post(f"{API}/demo/seed", headers=H).json()
    pid = s["case_id"]
    assert s["created"] and s["exists"] and pid.startswith("CASE-")
    assert all(step["done"] for step in s["steps"] if step["id"] in ("phenotypes", "variants", "pedigree"))
    # patient flagged demo and listed as such
    plist = c.get(f"{API}/patients?limit=50", headers=H).json()
    assert [p["demo"] for p in plist if p["patient_id"] == pid] == [True]
    # real module outputs exist and are linked to this case
    assert c.get(f"{API}/phenotype/case/{pid}", headers=H).status_code == 200
    ph = c.get(f"{API}/phenotype/case/{pid}", headers=H).json()
    assert len(ph["observed"]) == 4
    assert c.get(f"{API}/pedigree/{pid}/overview", headers=H).status_code == 200
    dx = c.get(f"{API}/dx/case/{pid}", headers=H).json()
    assert dx["available"] is True and any("Wilson" in d["disease_name"] for d in dx["differential"][:5])
    for path in (f"/pgx/case/{pid}", f"/repro/case/{pid}", f"/digital-twin/{pid}"):
        assert c.get(API + path, headers=H).status_code == 200, path
    # idempotent
    assert c.post(f"{API}/demo/seed", headers=H).json()["created"] is False


def test_demo_report_and_pdf_are_labelled_synthetic(env):
    c, hdr = env
    H = hdr("doc")
    pid = c.post(f"{API}/demo/seed", headers=H).json()["case_id"]
    rep = c.post(f"{API}/reports/case/{pid}", json={}, headers=H).json()
    body = c.get(f"{API}/reports/{rep['report_id']}/json", headers=H).json()
    content = body.get("content", body)
    assert "SAMPLE CASE" in content["title"] and content["synthetic"] is True
    assert "SAMPLE CASE" in content["disclaimer"]
    pdf = c.get(f"{API}/reports/{rep['report_id']}/pdf", headers=H)
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"
    assert c.get(f"{API}/demo/status", headers=H).json()["steps"][-1]["done"] is True


def test_reset_only_removes_own_demo_data(env):
    c, hdr = env
    H, H2 = hdr("doc"), hdr("doc2")
    real = c.post(f"{API}/patients", json={"age_years": 5, "sex": "M", "state": "Kerala"}, headers=H).json()["patient_id"]
    own = c.post(f"{API}/demo/seed", headers=H).json()["case_id"]
    other = c.post(f"{API}/demo/seed", headers=H2).json()["case_id"]
    r = c.post(f"{API}/demo/reset", headers=H).json()
    assert r["cases_removed"] == [own]
    assert store.get_patient(own) is None and store.get_patient(other) is not None and store.get_patient(real) is not None
    assert c.get(f"{API}/demo/status", headers=H).json()["exists"] is False
    assert c.get(f"{API}/demo/status", headers=H2).json()["exists"] is True
    assert any(a["action"] == "demo.reset" for a in store.recent_audit(20))      # audit history kept
    # re-seed works after reset
    assert c.post(f"{API}/demo/seed", headers=H).json()["created"] is True


def test_non_demo_record_with_demo_id_is_never_deleted_or_overwritten(env):
    c, hdr = env
    H = hdr("doc")
    pid = demo.case_id_for("doc")
    store.create_patient({"patient_id": pid, "age_years": 40, "sex": "M", "state": "Kerala"}, "doc")   # real record, no demo flag
    assert c.post(f"{API}/demo/seed", headers=H).status_code == 409
    c.post(f"{API}/demo/reset", headers=H)
    assert store.get_patient(pid) is not None


def test_no_default_credentials_in_production_bundle_or_app_shell():
    from pathlib import Path
    web = Path(__file__).resolve().parents[1] / "web"
    app = (web / "src" / "App.jsx").read_text(encoding="utf-8")
    assert "changeme" not in app and "login(" not in app                       # the landing page never signs anyone in
    login = (web / "src" / "components" / "LoginModal.jsx").read_text(encoding="utf-8")
    assert "DEV_LOGINS ? 'changeme' : ''" in login                             # prefill exists only for the dev server
    dist = web / "dist" / "assets"
    if dist.exists():                                                          # present after `npm run build`
        shipped = " ".join(p.read_text(encoding="utf-8", errors="ignore") for p in dist.glob("*.js"))
        assert "changeme" not in shipped and "admin-password-change-me" not in shipped


def test_assistant_context_is_grounded_in_the_demo_case(env):
    c, hdr = env
    H = hdr("doc")
    pid = c.post(f"{API}/demo/seed", headers=H).json()["case_id"]
    ctx = c.get(f"{API}/assistant/context", params={"patient_id": pid}, headers=H).json()
    assert ctx["has_sufficient_context"] is True
    from backend.app.services import registry
    r = registry.assistant.retriever.retrieve(query="Explain the primary finding in this demo case.", patient_id=pid,
                                              analysis_id=[a for a in registry.variants.list_analyses() if a["patient_id"] == pid][0]["analysis_id"])
    assert "SAMPLE CASE" in r.patient_context_text
    assert "Consanguinity=Yes" in r.patient_context_text and "ATP7B" in str(r.context_summary) + str(r.__dict__)


def test_status_reports_the_real_variant_count(env):
    c, hdr = env
    H = hdr("doc")
    c.post(f"{API}/demo/seed", headers=H)
    steps = {s["id"]: s for s in c.get(f"{API}/demo/status", headers=H).json()["steps"]}
    assert steps["variants"]["detail"] == "1 analysis, 3 variants"
    assert steps["phenotypes"]["detail"] == "4 HPO terms" and steps["pedigree"]["detail"] == "3 family members"
