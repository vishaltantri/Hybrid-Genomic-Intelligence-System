"""Phase 30 audit tests: route inventory, authentication on every route, no debug endpoints, consistent errors, audit trail,
production docs exposure."""
import os
import re
import subprocess
import sys

os.environ.setdefault("GENOMIND_EMBED_MODEL", "none")

import pytest
from fastapi.testclient import TestClient

from backend.app import store
from backend.app.main import app
from backend.app.security import hash_password

API = "/api/v1"
PUBLIC = {"/health", "/readiness", "/api/v1/auth/token", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _routes():
    out = []
    for r in app.routes:
        methods = getattr(r, "methods", None)
        path = getattr(r, "path", None)
        if not methods or not path:
            continue
        for m in methods - {"HEAD", "OPTIONS"}:
            out.append((m, path))
    return sorted(out)


def _fill(path):
    return re.sub(r"\{[^}:]+(:path)?\}", "x", path)


def test_route_inventory_is_substantial_and_stable():
    routes = _routes()
    assert len(routes) >= 170          # 179 method+path pairs at the Phase 30 audit
    paths = {p for _, p in routes}
    for must in ("/api/v1/patients", "/api/v1/variants/upload", "/api/v1/dx/case/{patient_id}", "/api/v1/reports/case/{pid}",
                 "/api/v1/emr/fhir/case/{pid}", "/api/v1/assistant/chat", "/api/v1/digital-twin/{patient_id}", "/api/v1/demo/status",
                 "/api/v1/quality/case/{pid}", "/api/v1/analytics/overview", "/api/v1/search", "/readiness", "/metrics"):
        assert must in paths, must


def test_every_api_route_rejects_unauthenticated_requests():
    c = TestClient(app, raise_server_exceptions=False)
    open_routes = []
    for method, path in _routes():
        if path in PUBLIC:
            continue
        r = c.request(method, _fill(path), json={} if method in ("POST", "PUT", "PATCH") else None)
        if r.status_code not in (401, 403):
            open_routes.append((method, path, r.status_code))
    assert open_routes == [], open_routes


def test_no_debug_or_internal_endpoints():
    bad = [p for _, p in _routes() if re.search(r"/(debug|test|_|internal|shell|exec|eval|dump|env)\b", p) and p not in PUBLIC]
    assert bad == [], bad


def test_unknown_routes_and_bad_methods_have_json_errors():
    c = TestClient(app)
    r = c.get("/api/v1/does-not-exist")
    assert r.status_code == 404 and "detail" in r.json()
    assert c.delete("/health").status_code == 405


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "audit.sqlite3")
    store.init_db()
    from backend.app.services import registry
    registry.variants._analyses.clear()
    store.create_user("doc", "doctor", hash_password("changeme"))
    c = TestClient(app)
    t = c.post(f"{API}/auth/token", data={"username": "doc", "password": "changeme"}).json()["access_token"]
    return c, {"Authorization": f"Bearer {t}"}


def test_sensitive_actions_leave_audit_entries(env):
    c, H = env
    pid = c.post(f"{API}/patients", json={"age_years": 5, "sex": "M", "state": "Kerala"}, headers=H).json()["patient_id"]
    from ml_services.config import SEEDS_DIR
    c.post(f"{API}/variants/upload", files={"file": ("t.vcf", (SEEDS_DIR / "demo_wilson_trio.vcf").read_text())}, data={"patient_id": pid}, headers=H)
    rid = c.post(f"{API}/reports/case/{pid}", json={}, headers=H).json()["report_id"]
    c.post(f"{API}/reports/{rid}/finalize", headers=H)
    c.get(f"{API}/emr/fhir/case/{pid}", headers=H)
    actions = {a["action"] for a in store.recent_audit(200)}
    for expected in ("patient.create", "variants.upload"):
        assert expected in actions, (expected, actions)
    assert any(a.startswith("report") for a in actions)
    # the audit log holds identifiers, never credentials or free-text clinical content
    blob = " ".join(str(a) for a in store.recent_audit(200))
    assert "changeme" not in blob and "Bearer" not in blob


def test_login_failures_do_not_reveal_which_part_was_wrong(env):
    c, _ = env
    a = c.post(f"{API}/auth/token", data={"username": "doc", "password": "wrong"})
    b = c.post(f"{API}/auth/token", data={"username": "nobody", "password": "wrong"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def _py(code, **env_over):
    env = {**os.environ, "GENOMIND_EMBED_MODEL": "none", "PYTHONUTF8": "1", **env_over}
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)


def test_production_refuses_weak_secret_and_hides_interactive_docs():
    weak = _py("import backend.app.main", GENOMERA_ENV="production", GENOMIND_JWT_SECRET="short")
    assert weak.returncode != 0 and "refusing to start" in weak.stderr
    ok = _py("from backend.app.main import app; print(app.docs_url, app.redoc_url, app.openapi_url)",
             GENOMERA_ENV="production", GENOMIND_JWT_SECRET="x" * 48, DATABASE_URL="sqlite:///" + os.path.join(ROOT, "data", "_audit_tmp.sqlite3").replace("\\", "/"))
    try:
        assert ok.returncode == 0, ok.stderr[-500:]
        assert ok.stdout.strip().splitlines()[-1] == "None None None"
    finally:
        for ext in ("", "-wal", "-shm"):
            p = os.path.join(ROOT, "data", "_audit_tmp.sqlite3" + ext)
            if os.path.exists(p):
                os.remove(p)


def test_upload_with_unknown_patient_id_creates_no_orphans(env, tmp_path):
    c, H = env
    from ml_services.config import SEEDS_DIR
    from scripts import db_audit
    r = c.post(f"{API}/variants/upload", files={"file": ("t.vcf", (SEEDS_DIR / "demo_wilson_trio.vcf").read_text())}, data={"patient_id": "P001"}, headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["patient_link"]["linked"] is False and "P001" in body["patient_link"]["requested"]
    assert body.get("patient_id") in (None, "")
    pid = c.post(f"{API}/patients", json={"age_years": 5, "sex": "M", "state": "Kerala"}, headers=H).json()["patient_id"]
    ok = c.post(f"{API}/variants/upload", files={"file": ("t.vcf", (SEEDS_DIR / "demo_wilson_trio.vcf").read_text())}, data={"patient_id": pid}, headers=H).json()
    assert ok["patient_id"] == pid and "patient_link" not in ok
    res = db_audit.audit(store.DB_PATH)
    assert res["ok"] and res["orphans"] == {} and res["integrity_check"] == "ok" and res["journal_mode"] == "wal"
    assert res["migrations"] == [1, 2, 3, 4]


def test_no_route_records_events_against_a_case_that_does_not_exist(env):
    c, H = env
    from scripts import db_audit
    ghost = "NO-SUCH-CASE"
    c.post(f"{API}/diagnosis", json={"hpo_ids": ["HP:0001337"], "patient_id": ghost}, headers=H)
    c.post(f"{API}/clinical/extract", json={"text": "bachche ko bukhaar hai", "patient_id": ghost}, headers=H)
    c.post(f"{API}/clinical/hpo-map", json={"text": "tremor and jaundice", "patient_id": ghost}, headers=H)
    c.post(f"{API}/reproductive/lab-report", json={"text": "Hb 9.1 g/dL HbA2 5.4 %", "patient_id": ghost}, headers=H)
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM clinical_events WHERE patient_id=?", (ghost,)).fetchone()[0] == 0
    assert db_audit.audit(store.DB_PATH)["orphans"] == {}
    # with a real case the same call is recorded
    pid = c.post(f"{API}/patients", json={"age_years": 5, "sex": "M", "state": "Kerala"}, headers=H).json()["patient_id"]
    c.post(f"{API}/clinical/hpo-map", json={"text": "tremor and jaundice", "patient_id": pid}, headers=H)
    assert any(e["kind"] == "hpo_profile" for e in store.list_events(pid))
