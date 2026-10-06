"""Ordered, idempotent schema migrations for the sqlite3 store (Phase 18).

`store.init_db()` runs the baseline SCHEMA (all `CREATE ... IF NOT EXISTS`) and then `apply_pending()`, which records each
applied step in `schema_migrations`. Steps only ever ADD (tables, columns, indexes); none drops or rewrites data, so an
existing database upgrades in place without loss. Re-running is a no-op.

  python -m backend.app.migrations status     # applied and pending
  python -m backend.app.migrations up         # apply pending
"""
from __future__ import annotations

import sqlite3
import sys
import time
from typing import Callable, List, Tuple

Migration = Tuple[int, str, Callable[[sqlite3.Connection], None]]


def _m1_baseline(conn: sqlite3.Connection) -> None:
    """Baseline = the SCHEMA string already executed by init_db. Recorded so history starts at a known point."""


def _m2_variant_analyses(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS variant_analyses (
        analysis_id TEXT PRIMARY KEY,
        filename TEXT,
        patient_id TEXT,
        created_by TEXT,
        timestamp REAL NOT NULL,
        variant_count INTEGER DEFAULT 0,
        qc_metrics TEXT,
        payload TEXT NOT NULL
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_va_created_by ON variant_analyses (created_by, timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_va_patient ON variant_analyses (patient_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_va_time ON variant_analyses (timestamp)")


def _m3_lookup_indexes(conn: sqlite3.Connection) -> None:
    """Indexes for the hottest foreign-key-style lookups (patient_id / case_id). Skips tables that do not exist."""
    wanted = [
        ("clinical_events", "idx_events_patient", "patient_id, created_utc"),
        ("case_reports", "idx_reports_patient", "patient_id"),
        ("referrals", "idx_referrals_created", "created_utc"),
        ("case_evidence", "idx_evidence_patient", "patient_id"),
        ("notifications", "idx_notif_user", "username"),
    ]
    for table, name, cols in wanted:
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        needed = {c.strip() for c in cols.split(",")}
        if have and needed <= have:
            conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({cols})")


def _m4_patient_listing_index(conn: sqlite3.Connection) -> None:
    """Patient list = filter by state, order by created_utc DESC; avoids a scan + sort on large registries."""
    have = {r[1] for r in conn.execute("PRAGMA table_info(patients)")}
    if {"state", "created_utc"} <= have:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_patients_state_created ON patients (state, created_utc DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_patients_created ON patients (created_utc DESC)")


MIGRATIONS: List[Migration] = [
    (1, "baseline schema", _m1_baseline),
    (2, "persist VCF analyses (variant_analyses)", _m2_variant_analyses),
    (3, "lookup indexes on patient/case columns", _m3_lookup_indexes),
    (4, "patient listing indexes (state, created_utc)", _m4_patient_listing_index),
]


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT, applied_utc TEXT)")


def applied(conn: sqlite3.Connection) -> List[int]:
    _ensure_table(conn)
    return [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]


def apply_pending(conn: sqlite3.Connection) -> List[int]:
    """Apply every unapplied migration in order, each in its own transaction. Returns the versions applied."""
    done = set(applied(conn))
    ran: List[int] = []
    for version, name, fn in MIGRATIONS:
        if version in done:
            continue
        conn.execute("BEGIN")
        try:
            fn(conn)
            conn.execute("INSERT INTO schema_migrations (version, name, applied_utc) VALUES (?, ?, ?)",
                         (version, name, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        ran.append(version)
    return ran


def status(conn: sqlite3.Connection) -> dict:
    done = set(applied(conn))
    return {"applied": sorted(done), "pending": [v for v, _, _ in MIGRATIONS if v not in done],
            "latest": MIGRATIONS[-1][0]}


if __name__ == "__main__":
    from backend.app import store
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    store.init_db()                     # applies pending as part of init
    with store._connect() as c:
        print(status(c))
    if cmd not in ("status", "up"):
        raise SystemExit("usage: python -m backend.app.migrations [status|up]")
