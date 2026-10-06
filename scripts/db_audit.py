"""Database audit (Phase 30): integrity, schema/migrations, indexes, journal mode, foreign-key declarations and orphaned rows.

  python -m scripts.db_audit [--db PATH]

Genomera's SQLite schema declares no FOREIGN KEY constraints (referential integrity is enforced by the application), so this
audit checks for orphans explicitly instead of relying on PRAGMA foreign_key_check, and reports what it found without
scoring. Exit code 1 if any integrity problem or orphan is found."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

CASE_TABLES = [("clinical_events", "patient_id"), ("twin_records", "patient_id"), ("case_evidence", "case_id"), ("case_reports", "case_id"),
               ("case_workflow", "case_id"), ("workflow_history", "case_id"), ("pedigree_members", "case_id"),
               ("pedigree_relationships", "case_id"), ("pedigree_variants", "case_id"), ("pedigree_genotypes", "case_id"),
               ("variant_analyses", "patient_id")]


def audit(db: Path) -> dict:
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        out = {"database": str(db), "integrity_check": conn.execute("PRAGMA integrity_check").fetchone()[0],
               "journal_mode": conn.execute("PRAGMA journal_mode").fetchone()[0], "tables": len(tables),
               "migrations": [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version")] if "schema_migrations" in tables else [],
               "foreign_keys_declared": sum(len(conn.execute(f'PRAGMA foreign_key_list("{t}")').fetchall()) for t in tables),
               "foreign_key_violations": len(conn.execute("PRAGMA foreign_key_check").fetchall()),
               "indexes": sorted(r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'")),
               "orphans": {}}
        for table, col in CASE_TABLES:
            if table in tables:
                # triage / ASHA sync events are keyed by the field worker or local record id, not a patient id (by design)
                extra = " AND kind NOT IN ('triage','triage_text','asha_sync')" if table == "clinical_events" else ""
                n = conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE "{col}" IS NOT NULL AND "{col}" NOT IN (SELECT patient_id FROM patients){extra}').fetchone()[0]
                if n:
                    out["orphans"][table] = n
        if "pedigree_genotypes" in tables:
            n = conn.execute("SELECT COUNT(*) FROM pedigree_genotypes WHERE member_id NOT IN (SELECT member_id FROM pedigree_members)").fetchone()[0]
            if n:
                out["orphans"]["pedigree_genotypes(member)"] = n
        if "referral_followups" in tables:
            n = conn.execute("SELECT COUNT(*) FROM referral_followups WHERE referral_id NOT IN (SELECT referral_id FROM referrals)").fetchone()[0]
            if n:
                out["orphans"]["referral_followups"] = n
        out["row_counts"] = {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
        out["ok"] = out["integrity_check"] == "ok" and not out["orphans"] and out["foreign_key_violations"] == 0
        return out
    finally:
        conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db")
    a = ap.parse_args()
    if a.db:
        path = Path(a.db)
    else:
        from backend.app import store
        path = Path(store.DB_PATH)
    res = audit(path)
    print(json.dumps(res, indent=2))
    sys.exit(0 if res["ok"] else 1)
