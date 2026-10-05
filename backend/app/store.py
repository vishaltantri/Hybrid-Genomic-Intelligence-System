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

from contextlib import contextmanager
import os

from ml_services.config import REPO_ROOT


def resolve_database_url(url: Optional[str]) -> Path:
    """`DATABASE_URL` abstraction. Only sqlite is implemented (sqlite:///relative.db, sqlite:////abs/path.db).
    Any other scheme (postgresql://...) fails loudly instead of silently using the wrong database; see docs/DATABASE.md."""
    if not url:
        return REPO_ROOT / "data" / "genomind_dev.sqlite3"
    if not url.startswith("sqlite:///"):
        raise RuntimeError(f"DATABASE_URL scheme not supported: {url.split(':', 1)[0]!r}. Only sqlite:/// is implemented "
                           "(PostgreSQL migration path is documented in docs/DATABASE.md).")
    raw = url[len("sqlite:///"):]
    path = Path(raw)
    return path if path.is_absolute() or raw.startswith("/") else REPO_ROOT / path


DB_PATH = resolve_database_url(os.environ.get("DATABASE_URL"))

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
CREATE TABLE IF NOT EXISTS twin_records (
    record_id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_utc TEXT,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_twin_records_lookup ON twin_records (patient_id, kind, created_by);
CREATE TABLE IF NOT EXISTS pedigree_members (
    member_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    label TEXT NOT NULL,
    sex TEXT NOT NULL DEFAULT 'U',
    age_years INTEGER,
    deceased INTEGER NOT NULL DEFAULT 0,
    affected TEXT NOT NULL DEFAULT 'unknown',
    is_proband INTEGER NOT NULL DEFAULT 0,
    vcf_sample TEXT,
    hpo_ids TEXT NOT NULL DEFAULT '[]',
    notes TEXT,
    synthetic INTEGER NOT NULL DEFAULT 0,
    layout_x REAL,
    layout_y REAL,
    created_by TEXT,
    created_utc TEXT,
    updated_utc TEXT
);
CREATE INDEX IF NOT EXISTS idx_ped_members_case ON pedigree_members (case_id);
CREATE TABLE IF NOT EXISTS pedigree_relationships (
    rel_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    rel_type TEXT NOT NULL,
    member_a TEXT NOT NULL,
    member_b TEXT NOT NULL,
    created_by TEXT,
    created_utc TEXT,
    UNIQUE (case_id, rel_type, member_a, member_b)
);
CREATE TABLE IF NOT EXISTS pedigree_variants (
    case_id TEXT NOT NULL,
    variant_key TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (case_id, variant_key)
);
CREATE TABLE IF NOT EXISTS pedigree_genotypes (
    case_id TEXT NOT NULL,
    member_id TEXT NOT NULL,
    variant_key TEXT NOT NULL,
    genotype TEXT NOT NULL,
    source TEXT NOT NULL,
    updated_by TEXT,
    updated_utc TEXT,
    PRIMARY KEY (member_id, variant_key)
);
CREATE TABLE IF NOT EXISTS case_evidence (
    evidence_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    variant_id TEXT,
    note TEXT,
    in_report INTEGER NOT NULL DEFAULT 0,
    added_by TEXT NOT NULL,
    added_utc TEXT,
    payload TEXT,
    UNIQUE (case_id, source, source_id, variant_id)
);
CREATE INDEX IF NOT EXISTS idx_case_evidence_case ON case_evidence (case_id);
CREATE TABLE IF NOT EXISTS case_reports (
    report_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created_by TEXT NOT NULL,
    created_utc TEXT,
    finalized_by TEXT,
    finalized_utc TEXT,
    content_sha256 TEXT NOT NULL,
    content TEXT NOT NULL,
    UNIQUE (case_id, version)
);
CREATE INDEX IF NOT EXISTS idx_case_reports_case ON case_reports (case_id);
CREATE TABLE IF NOT EXISTS referrals (
    referral_id TEXT PRIMARY KEY,
    created_by TEXT NOT NULL,
    created_utc TEXT,
    triage_color TEXT NOT NULL,
    source TEXT,
    age REAL,
    village TEXT,
    district TEXT,
    state TEXT,
    facility TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    follow_up_due TEXT,
    needs_review INTEGER NOT NULL DEFAULT 0,
    case_id TEXT,
    handoff_by TEXT,
    handoff_utc TEXT,
    triage TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_referrals_by ON referrals (created_by);
CREATE TABLE IF NOT EXISTS referral_followups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referral_id TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_utc TEXT,
    outcome TEXT NOT NULL,
    note TEXT
);
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    recipient TEXT,
    recipient_role TEXT,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    case_id TEXT,
    created_by TEXT,
    created_utc TEXT
);
CREATE INDEX IF NOT EXISTS idx_notif_recipient ON notifications (recipient, recipient_role);
CREATE TABLE IF NOT EXISTS notification_reads (
    notification_id TEXT NOT NULL,
    username TEXT NOT NULL,
    read_utc TEXT,
    PRIMARY KEY (notification_id, username)
);
CREATE TABLE IF NOT EXISTS case_workflow (
    case_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'new',
    assignee TEXT,
    updated_by TEXT,
    updated_utc TEXT
);
CREATE TABLE IF NOT EXISTS workflow_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    utc TEXT,
    action TEXT NOT NULL,
    from_value TEXT,
    to_value TEXT,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_wf_hist_case ON workflow_history (case_id);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    actor TEXT,
    action TEXT,
    subject TEXT,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_action_ts ON audit_log (action, ts);
CREATE INDEX IF NOT EXISTS idx_events_kind_created ON clinical_events (kind, created_utc);
CREATE INDEX IF NOT EXISTS idx_patients_created ON patients (created_utc);
"""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")          # wait for a competing writer instead of failing immediately
    try:
        conn.execute("PRAGMA journal_mode=WAL")        # readers do not block the writer; persisted in the db file
        conn.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.DatabaseError:
        pass
    return conn


@contextmanager
def transaction():
    """One atomic unit across several statements: commits on success, rolls everything back on any exception."""
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def init_db() -> None:
    from backend.app import migrations
    with _connect() as conn:
        conn.executescript(SCHEMA)
        conn.commit()
        migrations.apply_pending(conn)


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


# ------------------------- digital twin scenarios / snapshots -------------------------
# Kept out of clinical_events on purpose: those rows are returned by GET /patients/{id} to every
# clinician, whereas scenarios and saved snapshots are private to the user who created them.

def add_twin_record(record_id: str, patient_id: str, kind: str, created_by: str, payload: dict) -> dict:
    created = _now()
    with _connect() as conn:
        conn.execute("INSERT INTO twin_records (record_id, patient_id, kind, created_by, created_utc, payload) "
                     "VALUES (?,?,?,?,?,?)",
                     (record_id, patient_id, kind, created_by, created, json.dumps(payload, ensure_ascii=False)))
    return {"record_id": record_id, "patient_id": patient_id, "kind": kind, "created_by": created_by,
            "created_utc": created, "payload": payload}


def _twin_row(row) -> dict:
    d = dict(row)
    d["payload"] = json.loads(d["payload"] or "{}")
    return d


def list_twin_records(patient_id: str, kind: str, created_by: str, limit: int = 50) -> List[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM twin_records WHERE patient_id = ? AND kind = ? AND created_by = ? "
                            "ORDER BY created_utc DESC, rowid DESC LIMIT ?",
                            (patient_id, kind, created_by, limit)).fetchall()
    return [_twin_row(r) for r in rows]


def get_twin_record(record_id: str, patient_id: str, created_by: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM twin_records WHERE record_id = ? AND patient_id = ? AND created_by = ?",
                           (record_id, patient_id, created_by)).fetchone()
    return _twin_row(row) if row else None


def delete_twin_record(record_id: str, patient_id: str, created_by: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM twin_records WHERE record_id = ? AND patient_id = ? AND created_by = ?",
                           (record_id, patient_id, created_by))
    return cur.rowcount > 0


# ------------------------------- pedigree (Phase 3E) -------------------------------
# One pedigree per case (case_id == patient_id). Only canonical edges are stored (parent_of, partner);
# child / sibling / grandparent / ... are derived, so relationships can never be inconsistent.

_MEMBER_COLS = ("label", "sex", "age_years", "deceased", "affected", "is_proband", "vcf_sample", "hpo_ids", "notes",
                "synthetic", "layout_x", "layout_y")


def _member_row(row) -> dict:
    d = dict(row)
    d["deceased"] = bool(d["deceased"])
    d["is_proband"] = bool(d["is_proband"])
    d["synthetic"] = bool(d["synthetic"])
    d["hpo_ids"] = json.loads(d.get("hpo_ids") or "[]")
    return d


def ped_list_members(case_id: str) -> List[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM pedigree_members WHERE case_id = ? ORDER BY created_utc, rowid", (case_id,)).fetchall()
    return [_member_row(r) for r in rows]


def ped_get_member(case_id: str, member_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM pedigree_members WHERE case_id = ? AND member_id = ?", (case_id, member_id)).fetchone()
    return _member_row(row) if row else None


def ped_add_member(case_id: str, data: dict, created_by: str) -> dict:
    mid = f"MEM-{uuid.uuid4().hex[:8].upper()}"
    now = _now()
    vals = {k: data.get(k) for k in _MEMBER_COLS}
    vals["hpo_ids"] = json.dumps(data.get("hpo_ids") or [])
    vals["deceased"] = 1 if data.get("deceased") else 0
    vals["is_proband"] = 1 if data.get("is_proband") else 0
    vals["synthetic"] = 1 if data.get("synthetic") else 0
    vals["sex"] = data.get("sex") or "U"
    vals["affected"] = data.get("affected") or "unknown"
    with _connect() as conn:
        conn.execute(
            "INSERT INTO pedigree_members (member_id, case_id, " + ", ".join(_MEMBER_COLS) +
            ", created_by, created_utc, updated_utc) VALUES (?, ?, " + ", ".join("?" for _ in _MEMBER_COLS) + ", ?, ?, ?)",
            (mid, case_id, *[vals[k] for k in _MEMBER_COLS], created_by, now, now))
    return ped_get_member(case_id, mid)


def ped_update_member(case_id: str, member_id: str, fields: dict) -> Optional[dict]:
    sets, vals = [], []
    for k, v in fields.items():
        if k not in _MEMBER_COLS:
            continue
        if k == "hpo_ids":
            v = json.dumps(v or [])
        elif k in ("deceased", "is_proband", "synthetic"):
            v = 1 if v else 0
        sets.append(f"{k} = ?")
        vals.append(v)
    if sets:
        sets.append("updated_utc = ?")
        vals.append(_now())
        with _connect() as conn:
            conn.execute(f"UPDATE pedigree_members SET {', '.join(sets)} WHERE case_id = ? AND member_id = ?", (*vals, case_id, member_id))
    return ped_get_member(case_id, member_id)


def ped_set_proband(case_id: str, member_id: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE pedigree_members SET is_proband = 0 WHERE case_id = ?", (case_id,))
        conn.execute("UPDATE pedigree_members SET is_proband = 1, updated_utc = ? WHERE case_id = ? AND member_id = ?", (_now(), case_id, member_id))


def ped_delete_member(case_id: str, member_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM pedigree_genotypes WHERE case_id = ? AND member_id = ?", (case_id, member_id))
        conn.execute("DELETE FROM pedigree_relationships WHERE case_id = ? AND (member_a = ? OR member_b = ?)", (case_id, member_id, member_id))
        conn.execute("DELETE FROM pedigree_members WHERE case_id = ? AND member_id = ?", (case_id, member_id))


def ped_list_relationships(case_id: str) -> List[dict]:
    with _connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM pedigree_relationships WHERE case_id = ? ORDER BY rowid", (case_id,)).fetchall()]


def ped_add_relationship(case_id: str, rel_type: str, a: str, b: str, created_by: str) -> dict:
    rid = f"REL-{uuid.uuid4().hex[:8].upper()}"
    with _connect() as conn:
        conn.execute("INSERT INTO pedigree_relationships (rel_id, case_id, rel_type, member_a, member_b, created_by, created_utc) VALUES (?,?,?,?,?,?,?)",
                     (rid, case_id, rel_type, a, b, created_by, _now()))
    return {"rel_id": rid, "case_id": case_id, "rel_type": rel_type, "member_a": a, "member_b": b}


def ped_delete_relationship(case_id: str, rel_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM pedigree_relationships WHERE case_id = ? AND rel_id = ?", (case_id, rel_id))
    return cur.rowcount > 0


def ped_upsert_variant(case_id: str, variant_key: str, payload: dict) -> None:
    with _connect() as conn:
        conn.execute("INSERT OR REPLACE INTO pedigree_variants (case_id, variant_key, payload) VALUES (?,?,?)",
                     (case_id, variant_key, json.dumps(payload, ensure_ascii=False)))


def ped_list_variants(case_id: str) -> List[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT variant_key, payload FROM pedigree_variants WHERE case_id = ? ORDER BY rowid", (case_id,)).fetchall()
    return [{**json.loads(r["payload"]), "variant_key": r["variant_key"]} for r in rows]


def ped_set_genotype(case_id: str, member_id: str, variant_key: str, genotype: str, source: str, updated_by: str) -> None:
    with _connect() as conn:
        conn.execute("INSERT OR REPLACE INTO pedigree_genotypes (case_id, member_id, variant_key, genotype, source, updated_by, updated_utc) VALUES (?,?,?,?,?,?,?)",
                     (case_id, member_id, variant_key, genotype, source, updated_by, _now()))


def ped_delete_genotype(case_id: str, member_id: str, variant_key: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM pedigree_genotypes WHERE case_id = ? AND member_id = ? AND variant_key = ?", (case_id, member_id, variant_key))
    return cur.rowcount > 0


def ped_list_genotypes(case_id: str) -> List[dict]:
    with _connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM pedigree_genotypes WHERE case_id = ?", (case_id,)).fetchall()]


# --------------------------------- audit ---------------------------------

# ------------------------------- case evidence (Phase 4) -------------------------------

def _ev_row(r) -> dict:
    d = dict(r)
    d["payload"] = json.loads(d.get("payload") or "{}")
    d["in_report"] = bool(d["in_report"])
    return d


def evidence_save(case_id: str, record: dict, added_by: str, variant_id: Optional[str] = None, note: str = "",
                  in_report: bool = False) -> dict:
    """Idempotent: saving the same source record for the same case/variant updates note/report flag."""
    key = (case_id, record["source"], str(record.get("pmid") or record["source_id"]), variant_id or "")
    with _connect() as conn:
        row = conn.execute("SELECT evidence_id FROM case_evidence WHERE case_id=? AND source=? AND source_id=? AND COALESCE(variant_id,'')=?",
                           key).fetchone()
        if row:
            conn.execute("UPDATE case_evidence SET note=?, in_report=MAX(in_report, ?) WHERE evidence_id=?",
                         (note, int(in_report), row["evidence_id"]))
            eid = row["evidence_id"]
        else:
            eid = f"EVD-{uuid.uuid4().hex[:10]}"
            conn.execute("INSERT INTO case_evidence (evidence_id, case_id, source, source_id, variant_id, note, in_report, "
                         "added_by, added_utc, payload) VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (eid, case_id, key[1], key[2], variant_id or "", note, int(in_report), added_by, _now(),
                          json.dumps(record, ensure_ascii=False)))
        return _ev_row(conn.execute("SELECT * FROM case_evidence WHERE evidence_id=?", (eid,)).fetchone())


def evidence_list(case_id: str) -> List[dict]:
    with _connect() as conn:
        return [_ev_row(r) for r in conn.execute("SELECT * FROM case_evidence WHERE case_id=? ORDER BY added_utc DESC, rowid DESC", (case_id,))]


def evidence_update(case_id: str, evidence_id: str, note: Optional[str] = None, in_report: Optional[bool] = None) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM case_evidence WHERE evidence_id=? AND case_id=?", (evidence_id, case_id)).fetchone()
        if not row:
            return None
        conn.execute("UPDATE case_evidence SET note=?, in_report=? WHERE evidence_id=?",
                     (row["note"] if note is None else note, int(row["in_report"] if in_report is None else in_report), evidence_id))
        return _ev_row(conn.execute("SELECT * FROM case_evidence WHERE evidence_id=?", (evidence_id,)).fetchone())


def evidence_delete(case_id: str, evidence_id: str) -> bool:
    with _connect() as conn:
        return conn.execute("DELETE FROM case_evidence WHERE evidence_id=? AND case_id=?", (evidence_id, case_id)).rowcount > 0


def audit(actor: str, action: str, subject: str = "", detail: str = "") -> None:
    """Append-only audit entry. Fields are bounded so free text (notes, queries, filenames) cannot flood or leak."""
    clip = lambda v, n: str(v if v is not None else "")[:n].replace("\n", " ").replace("\r", " ")
    with _connect() as conn:
        conn.execute("INSERT INTO audit_log (ts, actor, action, subject, detail) VALUES (?,?,?,?,?)",
                     (_now(), clip(actor, 64), clip(action, 64), clip(subject, 96), clip(detail, 300)))


def recent_audit(limit: int = 50) -> List[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


init_db()


# ----------------------------- case reports (Phase 11) -----------------------------

def _report_row(r) -> dict:
    d = dict(r)
    d["content"] = json.loads(d["content"])
    return d


def content_sha(content: dict) -> str:
    import hashlib
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def report_create(case_id: str, created_by: str, content: dict) -> dict:
    with _connect() as conn:
        v = (conn.execute("SELECT MAX(version) FROM case_reports WHERE case_id=?", (case_id,)).fetchone()[0] or 0) + 1
        rid = f"RPT-{uuid.uuid4().hex[:10].upper()}"
        content = {**content, "report_id": rid, "version": v}
        sha = content_sha(content)
        conn.execute("INSERT INTO case_reports (report_id, case_id, version, status, created_by, created_utc, content_sha256, content) "
                     "VALUES (?,?,?,?,?,?,?,?)", (rid, case_id, v, "draft", created_by, _now(), sha, json.dumps(content, ensure_ascii=False)))
    return report_get(rid)


def report_get(report_id: str) -> Optional[dict]:
    with _connect() as conn:
        r = conn.execute("SELECT * FROM case_reports WHERE report_id=?", (report_id,)).fetchone()
    return _report_row(r) if r else None


def report_list(case_id: str) -> List[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT report_id, case_id, version, status, created_by, created_utc, finalized_by, finalized_utc, content_sha256 "
                            "FROM case_reports WHERE case_id=? ORDER BY version DESC", (case_id,)).fetchall()
    return [dict(r) for r in rows]


def report_update_content(report_id: str, content: dict, sha: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE case_reports SET content=?, content_sha256=? WHERE report_id=? AND status='draft'",
                     (json.dumps(content, ensure_ascii=False), sha, report_id))


def report_finalize(report_id: str, user: str) -> Optional[dict]:
    with _connect() as conn:
        conn.execute("UPDATE case_reports SET status='final', finalized_by=?, finalized_utc=? WHERE report_id=? AND status='draft'",
                     (user, _now(), report_id))
    return report_get(report_id)


# ---- Phase 13: ASHA referrals ----

def _ref_row(r) -> dict:
    d = dict(r)
    d["triage"] = json.loads(d["triage"])
    d["needs_review"] = bool(d["needs_review"])
    return d


def referral_create(created_by: str, triage: dict, follow_up_due: str) -> dict:
    rid = f"REF-{uuid.uuid4().hex[:10].upper()}"
    with _connect() as conn:
        conn.execute("INSERT INTO referrals (referral_id, created_by, created_utc, triage_color, source, age, village, district, state, "
                     "facility, follow_up_due, triage) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                     (rid, created_by, _now(), triage["triage_color"], triage.get("source"), triage.get("age"), triage.get("village"),
                      triage.get("district"), triage.get("state"), triage.get("referral_facility"), follow_up_due,
                      json.dumps(triage, ensure_ascii=False)))
    return referral_get(rid)


def referral_get(rid: str) -> Optional[dict]:
    with _connect() as conn:
        r = conn.execute("SELECT * FROM referrals WHERE referral_id=?", (rid,)).fetchone()
        if not r:
            return None
        d = _ref_row(r)
        d["followups"] = [dict(x) for x in conn.execute("SELECT * FROM referral_followups WHERE referral_id=? ORDER BY id", (rid,)).fetchall()]
    return d


def referral_list(created_by: Optional[str] = None, status: Optional[str] = None, color: Optional[str] = None) -> List[dict]:
    q, a = "SELECT * FROM referrals WHERE 1=1", []
    for col, val in (("created_by", created_by), ("status", status), ("triage_color", color)):
        if val:
            q += f" AND {col}=?"
            a.append(val)
    with _connect() as conn:
        return [_ref_row(r) for r in conn.execute(q + " ORDER BY created_utc DESC", a).fetchall()]


def referral_followup(rid: str, by: str, outcome: str, note: str, status: str, needs_review: bool) -> None:
    with _connect() as conn:
        conn.execute("INSERT INTO referral_followups (referral_id, created_by, created_utc, outcome, note) VALUES (?,?,?,?,?)",
                     (rid, by, _now(), outcome, note))
        conn.execute("UPDATE referrals SET status=?, needs_review=? WHERE referral_id=?", (status, 1 if needs_review else 0, rid))


def referral_handoff(rid: str, case_id: str, by: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE referrals SET case_id=?, handoff_by=?, handoff_utc=?, status='handed_off' WHERE referral_id=?", (case_id, by, _now(), rid))


# ---- Phase 14: notifications and case workflow ----

def notify(kind: str, title: str, body: str = "", case_id: str = "", recipient: Optional[str] = None,
           recipient_role: Optional[str] = None, created_by: str = "system") -> str:
    nid = f"NTF-{uuid.uuid4().hex[:10].upper()}"
    with _connect() as conn:
        conn.execute("INSERT INTO notifications (id, recipient, recipient_role, kind, title, body, case_id, created_by, created_utc) "
                     "VALUES (?,?,?,?,?,?,?,?,?)", (nid, recipient, recipient_role, kind, title, body, case_id or None, created_by, _now()))
    return nid


def notification_list(username: str, role: str, unread_only: bool = False, limit: int = 100) -> List[dict]:
    q = ("SELECT n.*, r.read_utc FROM notifications n LEFT JOIN notification_reads r "
         "ON r.notification_id = n.id AND r.username = ? "
         "WHERE (n.recipient = ? OR n.recipient_role = ?)")
    if unread_only:
        q += " AND r.read_utc IS NULL"
    q += " ORDER BY n.created_utc DESC, n.rowid DESC LIMIT ?"
    with _connect() as conn:
        return [dict(r) for r in conn.execute(q, (username, username, role, limit)).fetchall()]


def notification_mark_read(nid: str, username: str, role: str) -> bool:
    with _connect() as conn:
        ok = conn.execute("SELECT 1 FROM notifications WHERE id=? AND (recipient=? OR recipient_role=?)", (nid, username, role)).fetchone()
        if not ok:
            return False
        conn.execute("INSERT OR IGNORE INTO notification_reads (notification_id, username, read_utc) VALUES (?,?,?)", (nid, username, _now()))
    return True


def notification_mark_all(username: str, role: str) -> int:
    ids = [n["id"] for n in notification_list(username, role, unread_only=True, limit=10000)]
    with _connect() as conn:
        for i in ids:
            conn.execute("INSERT OR IGNORE INTO notification_reads (notification_id, username, read_utc) VALUES (?,?,?)", (i, username, _now()))
    return len(ids)


def workflow_get(case_id: str) -> dict:
    with _connect() as conn:
        r = conn.execute("SELECT * FROM case_workflow WHERE case_id=?", (case_id,)).fetchone()
        hist = [dict(x) for x in conn.execute("SELECT * FROM workflow_history WHERE case_id=? ORDER BY id", (case_id,)).fetchall()]
    base = dict(r) if r else {"case_id": case_id, "status": "new", "assignee": None, "updated_by": None, "updated_utc": None}
    return {**base, "history": hist}


def workflow_set(case_id: str, actor: str, *, status: Optional[str] = None, assignee: Optional[str] = None, note: str = "") -> dict:
    cur = workflow_get(case_id)
    with _connect() as conn:
        conn.execute("INSERT OR IGNORE INTO case_workflow (case_id, status, updated_by, updated_utc) VALUES (?, 'new', ?, ?)", (case_id, actor, _now()))
        if status is not None and status != cur["status"]:
            conn.execute("UPDATE case_workflow SET status=? WHERE case_id=?", (status, case_id))
            conn.execute("INSERT INTO workflow_history (case_id, actor, utc, action, from_value, to_value, note) VALUES (?,?,?,?,?,?,?)",
                         (case_id, actor, _now(), "status", cur["status"], status, note))
        if assignee is not None and assignee != cur["assignee"]:
            conn.execute("UPDATE case_workflow SET assignee=? WHERE case_id=?", (assignee, case_id))
            conn.execute("INSERT INTO workflow_history (case_id, actor, utc, action, from_value, to_value, note) VALUES (?,?,?,?,?,?,?)",
                         (case_id, actor, _now(), "assign", cur["assignee"], assignee, note))
        conn.execute("UPDATE case_workflow SET updated_by=?, updated_utc=? WHERE case_id=?", (actor, _now(), case_id))
    return workflow_get(case_id)


def workflow_queue(assignee: Optional[str] = None, status: Optional[str] = None) -> List[dict]:
    q, a = "SELECT * FROM case_workflow WHERE 1=1", []
    for col, val in (("assignee", assignee), ("status", status)):
        if val:
            q += f" AND {col}=?"
            a.append(val)
    with _connect() as conn:
        return [dict(r) for r in conn.execute(q + " ORDER BY updated_utc DESC", a).fetchall()]


# --------------------------------- VCF analyses (repository) ---------------------------------

def save_analysis(record: dict) -> None:
    """Persist one analysis atomically (insert or replace by analysis_id)."""
    with transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO variant_analyses (analysis_id, filename, patient_id, created_by, timestamp, variant_count, qc_metrics, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (record["analysis_id"], record.get("filename"), record.get("patient_id"), record.get("created_by"),
             record.get("timestamp") or time.time(), len(record.get("variants", [])),
             json.dumps(record.get("qc_metrics", {})), json.dumps(record)))


def load_analysis(analysis_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT payload FROM variant_analyses WHERE analysis_id=?", (analysis_id,)).fetchone()
    return json.loads(row["payload"]) if row else None


def list_analysis_summaries(limit: int = 500) -> List[dict]:
    """Summaries without loading the (large) payload column."""
    with _connect() as conn:
        rows = conn.execute("SELECT analysis_id, filename, patient_id, created_by, timestamp, qc_metrics FROM variant_analyses "
                            "ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
    return [{"analysis_id": r["analysis_id"], "filename": r["filename"], "patient_id": r["patient_id"], "timestamp": r["timestamp"],
             "qc_metrics": json.loads(r["qc_metrics"] or "{}"), "created_by": r["created_by"]} for r in rows]
