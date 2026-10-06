"""Phase 25: readiness reflects real state, request ids/logging/metrics work, 500s leak nothing, backup/restore round-trips."""
import json
import logging
import os
import sqlite3

os.environ.setdefault("GENOMIND_EMBED_MODEL", "none")

import pytest
from fastapi.testclient import TestClient

from backend.app import observability, store
from backend.app.main import app
from backend.app.security import hash_password
from scripts import backup_db

API = "/api/v1"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "prod.sqlite3")
    store.init_db()
    store.create_user("adm", "admin", hash_password("changeme"))
    store.create_user("doc", "doctor", hash_password("changeme"))
    observability.metrics.reset()
    c = TestClient(app)

    def hdr(u):
        t = c.post(f"{API}/auth/token", data={"username": u, "password": "changeme"}).json()["access_token"]
        return {"Authorization": f"Bearer {t}"}
    return c, hdr, tmp_path


def test_health_is_liveness_and_unchanged(env):
    c, _, _ = env
    r = c.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["graph_nodes"] > 0


def test_readiness_ready_then_not_ready_when_database_is_unavailable(env, monkeypatch):
    c, _, tmp = env
    r = c.get("/readiness")
    assert r.status_code == 200 and r.json()["status"] == "ready"
    assert r.json()["checks"]["database"]["ok"] and r.json()["checks"]["migrations"]["pending"] == []
    monkeypatch.setattr(store, "DB_PATH", tmp)        # a directory cannot be opened as a database
    r = c.get("/readiness")
    assert r.status_code == 503 and r.json()["status"] == "not_ready" and r.json()["checks"]["database"]["ok"] is False


def test_readiness_reports_pending_migrations(env, monkeypatch):
    c, _, _ = env
    from backend.app import migrations
    monkeypatch.setattr(migrations, "MIGRATIONS", [*migrations.MIGRATIONS, (99, "later", lambda conn: None)])
    r = c.get("/readiness")
    assert r.status_code == 503 and r.json()["checks"]["migrations"]["pending"] == [99]


def test_request_id_generated_propagated_and_sanitised(env):
    c, _, _ = env
    assert len(c.get("/health").headers["x-request-id"]) == 32
    assert c.get("/health", headers={"X-Request-ID": "trace-12345678"}).headers["x-request-id"] == "trace-12345678"
    assert c.get("/health", headers={"X-Request-ID": "bad id\twith spaces"}).headers["x-request-id"] != "bad id\twith spaces"


def test_metrics_require_admin_and_reflect_real_traffic(env):
    c, hdr, _ = env
    assert c.get("/metrics").status_code == 401
    assert c.get("/metrics", headers=hdr("doc")).status_code == 403
    for _ in range(3):
        c.get(f"{API}/patients", headers=hdr("doc"))
    c.get(f"{API}/patients/DOES-NOT-EXIST", headers=hdr("doc"))
    text = c.get("/metrics", headers=hdr("adm")).text
    assert 'genomera_http_requests_total{method="GET",route="/api/v1/patients",status="200"} 3' in text
    assert 'route="/api/v1/patients/{patient_id}",status="404"' in text          # templates, not raw ids
    assert "DOES-NOT-EXIST" not in text
    assert "genomera_database_up 1" in text and "genomera_http_request_duration_seconds_count" in text
    snap = c.get(f"{API}/ops/status", headers=hdr("adm")).json()
    assert snap["metrics"]["requests_total"] >= 4 and snap["ready"]["status"] == "ready"
    assert c.get(f"{API}/ops/status", headers=hdr("doc")).status_code == 403


def test_unhandled_error_returns_generic_500_and_logs_stack_server_side(env, caplog):
    c, hdr, _ = env
    from fastapi import APIRouter
    r = APIRouter()

    @r.get("/_boom")
    def boom():
        raise RuntimeError("secret internal path C:\\prod\\db.py password=hunter2")

    app.include_router(r)
    try:
        with caplog.at_level(logging.ERROR, logger="genomera.error"):
            resp = TestClient(app, raise_server_exceptions=False).get("/_boom")
    finally:
        app.router.routes[:] = [x for x in app.router.routes if getattr(x, "path", "") != "/_boom"]
    assert resp.status_code == 500
    body = resp.json()
    assert body["detail"] == "Internal server error" and body["request_id"] == resp.headers["x-request-id"]
    assert "hunter2" not in resp.text and "db.py" not in resp.text
    assert any(rec.exc_info for rec in caplog.records)                            # the stack is in the server log
    assert observability.metrics.snapshot()["server_errors_total"] >= 1


def test_logs_are_structured_without_secrets():
    rec = logging.LogRecord("t", logging.INFO, "f", 1, "login password=hunter2 Authorization: Bearer abc.def.ghi", (), None)
    assert observability.RedactingFilter().filter(rec) and "hunter2" not in rec.msg and "abc.def" not in rec.msg
    rec2 = logging.LogRecord("genomera.access", logging.INFO, "f", 1, "GET /x 200", (), None)
    rec2.fields = {"request_id": "r1", "status": 200}
    out = json.loads(observability.JsonFormatter().format(rec2))
    assert out["request_id"] == "r1" and out["status"] == 200 and out["level"] == "INFO" and out["ts"].endswith("Z")


def test_access_log_has_no_query_string_or_ids(env, caplog):
    c, hdr, _ = env
    with caplog.at_level(logging.INFO, logger="genomera.access"):
        c.get(f"{API}/search", params={"q": "Rajesh Kumar 9876543210"}, headers=hdr("doc"))
    lines = [r.getMessage() for r in caplog.records if r.name == "genomera.access"]
    assert lines and not any("Rajesh" in x or "9876543210" in x for x in lines)


# ----------------------------------------------------------------------------- backup / restore

def test_backup_restore_round_trip_and_app_starts_on_restored_db(env, monkeypatch):
    c, hdr, tmp = env
    H = hdr("doc")
    pid = c.post(f"{API}/patients", json={"age_years": 9, "sex": "F", "state": "Kerala"}, headers=H).json()["patient_id"]
    bak = backup_db.backup(store.DB_PATH, tmp / "bk")
    assert backup_db.verify(bak)["ok"] is True
    # lose the live database, restore, point the app at it and read the data back through the API
    restored = tmp / "restored.sqlite3"
    res = backup_db.restore(bak, restored)
    assert res["rows"] > 0
    monkeypatch.setattr(store, "DB_PATH", restored)
    store.init_db()
    assert c.get("/readiness").status_code == 200
    H2 = hdr("doc")                                                               # users restored too
    assert c.get(f"{API}/patients/{pid}", headers=H2).status_code == 200


def test_restore_refuses_overwrite_and_keeps_old_file_with_force(env):
    _, _, tmp = env
    bak = backup_db.backup(store.DB_PATH, tmp / "bk")
    with pytest.raises(backup_db.BackupError, match="exists"):
        backup_db.restore(bak, store.DB_PATH)
    target = tmp / "t.sqlite3"
    old = sqlite3.connect(target)
    old.executescript("CREATE TABLE old(x); INSERT INTO old VALUES (1);")
    old.close()
    out = backup_db.restore(bak, target, force=True)
    assert out["previous_kept_as"] and (tmp / out["previous_kept_as"].split(os.sep)[-1]).exists()


def test_tampered_backup_fails_verification_and_is_not_restored(env):
    _, _, tmp = env
    bak = backup_db.backup(store.DB_PATH, tmp / "bk")
    with bak.open("r+b") as f:
        f.seek(2000)
        f.write(b"CORRUPT")
    with pytest.raises(backup_db.BackupError):
        backup_db.verify(bak)
    with pytest.raises(backup_db.BackupError):
        backup_db.restore(bak, tmp / "never.sqlite3")
    assert not (tmp / "never.sqlite3").exists()


def test_demo_is_disabled_in_production_unless_enabled(env, monkeypatch):
    c, hdr, _ = env
    monkeypatch.setenv("GENOMERA_ENV", "production")
    H = hdr("doc")
    s = c.get(f"{API}/demo/status", headers=H).json()
    assert s["enabled"] is False and s["exists"] is False
    assert c.post(f"{API}/demo/seed", headers=H).status_code == 403
    monkeypatch.setenv("GENOMERA_ENABLE_DEMO", "1")
    assert c.get(f"{API}/demo/status", headers=H).json().get("enabled", True) is True
