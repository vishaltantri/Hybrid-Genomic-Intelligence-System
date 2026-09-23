"""Lightweight persistence for the API.

SQLite via the standard library keeps the prototype zero-install; the schema and DAO
methods map 1:1 onto the PostgreSQL tables in docker-compose for production migration
(swap `_connect` for SQLAlchemy/psycopg and the call sites stay the same).
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from ml_services.config import REPO_ROOT

DB_PATH = REPO_ROOT / "data" / "genomind_dev.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT,
    created_utc TEXT
);
CREATE TABLE IF NOT EXISTS patients (
    patient_id TEXT PRIMARY KEY,
    created_utc TEXT,
    created_by TEXT,
    age_years INTEGER,
    sex TEXT,
    state TEXT,
    district TEXT,
    community TEXT,
    consanguineous INTEGER DEFAULT 0,
    abha_id TEXT,
    payload TEXT
);
CREATE TABLE IF NOT EXISTS clinical_events (
    event_id TEXT PRIMARY KEY,
    patient_id TEXT,
    kind TEXT,
    created_utc TEXT,
    payload TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    actor TEXT,
    action TEXT,
    subject TEXT,
    detail TEXT
);
"""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# --------------------------------- users ---------------------------------

def create_user(username: str, role: str, password_hash: str, full_name: str = "") -> dict:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO users (username, role, password_hash, full_name, created_utc) "
            "VALUES (?, ?, ?, ?, ?)",
            (username, role, password_hash, full_name, _now()),
        )
    return {"username": username, "role": role, "full_name": full_name}


def get_user(username: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None


def list_users() -> List[dict]:
    with _connect() as conn:
        return [dict(r) for r in conn.execute("SELECT username, role, full_name FROM users").fetchall()]


# -------------------------------- patients --------------------------------

def create_patient(patient: dict, created_by: str) -> dict:
    pid = patient.get("patient_id") or f"PT-{uuid.uuid4().hex[:8].upper()}"
    record = {
        "patient_id": pid,
        "created_utc": _now(),
        "created_by": created_by,
        "age_years": patient.get("age_years"),
        "sex": patient.get("sex"),
        "state": patient.get("state"),
        "district": patient.get("district"),
        "community": patient.get("community"),
        "consanguineous": 1 if patient.get("consanguineous") else 0,
        "abha_id": patient.get("abha_id"),
        "payload": json.dumps({k: v for k, v in patient.items() if k not in
                              ("patient_id", "age_years", "sex", "state", "district",
                               "community", "consanguineous", "abha_id")}, ensure_ascii=False),
    }
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO patients (patient_id, created_utc, created_by, age_years, sex, state, "
            "district, community, consanguineous, abha_id, payload) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (record["patient_id"], record["created_utc"], record["created_by"], record["age_years"],
             record["sex"], record["state"], record["district"], record["community"],
             record["consanguineous"], record["abha_id"], record["payload"]),
        )
    audit(created_by, "patient.create", pid, "")
    return get_patient(pid) or record


def get_patient(patient_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM patients WHERE patient_id = ?", (patient_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["consanguineous"] = bool(d["consanguineous"])
    d["extra"] = json.loads(d.pop("payload") or "{}")
    return d


def list_patients(state: Optional[str] = None, limit: int = 100) -> List[dict]:
    query = "SELECT * FROM patients"
    params: tuple = ()
    if state:
        query += " WHERE state = ?"
        params = (state,)
    query += " ORDER BY created_utc DESC LIMIT ?"
    params = params + (limit,)
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        d["consanguineous"] = bool(d["consanguineous"])
        d["extra"] = json.loads(d.pop("payload") or "{}")
        out.append(d)
    return out


# ----------------------------- clinical events -----------------------------

def add_event(patient_id: str, kind: str, payload: dict) -> dict:
    event = {"event_id": f"EV-{uuid.uuid4().hex[:10]}", "patient_id": patient_id, "kind": kind,
             "created_utc": _now(), "payload": payload}
    with _connect() as conn:
        conn.execute("INSERT INTO clinical_events (event_id, patient_id, kind, created_utc, payload) "
                     "VALUES (?,?,?,?,?)",
                     (event["event_id"], patient_id, kind, event["created_utc"],
                      json.dumps(payload, ensure_ascii=False)))
    return event


def list_events(patient_id: str, kind: Optional[str] = None) -> List[dict]:
    query = "SELECT * FROM clinical_events WHERE patient_id = ?"
    params: tuple = (patient_id,)
    if kind:
        query += " AND kind = ?"
        params = params + (kind,)
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["payload"] = json.loads(d["payload"] or "{}")
        out.append(d)
    return out


# --------------------------------- audit ---------------------------------

def audit(actor: str, action: str, subject: str = "", detail: str = "") -> None:
    with _connect() as conn:
        conn.execute("INSERT INTO audit_log (ts, actor, action, subject, detail) VALUES (?,?,?,?,?)",
                     (_now(), actor, action, subject, detail))


def recent_audit(limit: int = 50) -> List[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


init_db()
