"""Phase 18: DATABASE_URL, migrations (no data loss, idempotent), analysis persistence, transactions, concurrency, OpenAPI."""
import sqlite3
import threading

import pytest
from fastapi.testclient import TestClient

from backend.app import migrations, store
from backend.app.main import app
from backend.app.security import create_access_token
from backend.app.services import registry
from ml_services.config import SEEDS_DIR

VCF = (SEEDS_DIR / "clinical_sample_trio.vcf").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "db.sqlite3")
    store.init_db()


def test_database_url_resolution(tmp_path):
    assert store.resolve_database_url(None).name == "genomind_dev.sqlite3"
    assert store.resolve_database_url("sqlite:///data/x.db").name == "x.db"
    abs_p = tmp_path / "abs.db"
    assert store.resolve_database_url("sqlite:///" + str(abs_p).replace("\\", "/")).name == "abs.db"
    with pytest.raises(RuntimeError, match="not supported"):
        store.resolve_database_url("postgresql://u:p@h/db")


def test_migrations_apply_in_order_and_are_idempotent():
    with store._connect() as conn:
        st = migrations.status(conn)
        assert st["pending"] == [] and st["applied"] == [v for v, _, _ in migrations.MIGRATIONS]
        assert migrations.apply_pending(conn) == []
    store.init_db()    # re-running is harmless


def test_upgrade_from_legacy_database_keeps_data(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy.sqlite3"
    monkeypatch.setattr(store, "DB_PATH", legacy)
    c = sqlite3.connect(legacy)                       # a pre-Phase-18 db: baseline tables, no schema_migrations
    c.executescript(store.SCHEMA)
    c.execute("INSERT INTO users (username, role, password_hash) VALUES ('keep','doctor','h')")
    c.execute("INSERT INTO patients (patient_id, created_utc) VALUES ('P-LEGACY','2025-01-01T00:00:00Z')")
    c.commit(); c.close()
    store.init_db()
    assert store.get_user("keep")["role"] == "doctor"
    assert store.get_patient("P-LEGACY") is not None
    with store._connect() as conn:
        assert "variant_analyses" in {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_failed_migration_rolls_back(monkeypatch):
    def boom(conn):
        conn.execute("CREATE TABLE half_done (x)")
        raise RuntimeError("boom")
    monkeypatch.setattr(migrations, "MIGRATIONS", [*migrations.MIGRATIONS, (99, "bad", boom)])
    with store._connect() as conn:
        with pytest.raises(RuntimeError):
            migrations.apply_pending(conn)
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='half_done'").fetchone()
        assert 99 not in migrations.applied(conn)


def test_transaction_rolls_back_all_steps():
    with pytest.raises(ValueError):
        with store.transaction() as conn:
            conn.execute("INSERT INTO users (username, role, password_hash) VALUES ('tx1','doctor','h')")
            raise ValueError("fail after first write")
    assert store.get_user("tx1") is None
    with store.transaction() as conn:
        conn.execute("INSERT INTO users (username, role, password_hash) VALUES ('tx2','doctor','h')")
    assert store.get_user("tx2")


def test_wal_and_foreign_keys_enabled():
    with store._connect() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_analysis_survives_memory_loss():
    rec = registry.variants.analyze_vcf(VCF, filename="p.vcf", created_by="u1")
    aid = rec["analysis_id"]
    registry.variants._analyses.pop(aid)               # simulates a server restart
    again = registry.variants.get_analysis(aid)
    assert again and again["analysis_id"] == aid and len(again["variants"]) == len(rec["variants"])
    registry.variants._analyses.pop(aid, None)
    assert aid in [a["analysis_id"] for a in registry.variants.list_analyses()]


def test_persisted_analysis_served_by_api_after_restart():
    c = TestClient(app)
    store.create_user("persist1", "doctor", "x")
    h = {"Authorization": f"Bearer {create_access_token('persist1', 'doctor')}"}
    aid = registry.variants.analyze_vcf(VCF, filename="p.vcf", created_by="persist1")["analysis_id"]
    registry.variants._analyses.clear()
    r = c.get(f"/api/v1/variants/analyses/{aid}", headers=h)
    assert r.status_code == 200 and r.json()["analysis_id"] == aid


def test_concurrent_writers_do_not_lock_or_lose_rows():
    errors = []

    def work(i):
        try:
            for j in range(10):
                store.audit(f"w{i}", "concurrency.test", f"{i}-{j}", "x")
        except Exception as ex:  # pragma: no cover
            errors.append(ex)
    ts = [threading.Thread(target=work, args=(i,)) for i in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert not errors
    with store._connect() as conn:
        assert conn.execute("SELECT count(*) FROM audit_log WHERE action='concurrency.test'").fetchone()[0] == 80


def test_openapi_is_valid_and_complete():
    spec = TestClient(app).get("/openapi.json").json()
    assert spec["openapi"].startswith("3.")
    ids, untagged = set(), []
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            assert op["operationId"] not in ids, f"duplicate operationId {op['operationId']}"
            ids.add(op["operationId"])
            if not op.get("tags"):
                untagged.append(f"{method} {path}")
    assert not untagged
    assert "/api/v1/analytics/overview" in spec["paths"] and "/api/v1/variants/upload" in spec["paths"]
