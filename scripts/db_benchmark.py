"""Measure query timings on a synthetic sqlite database with and without the Phase 16-18 indexes.
Run: python scripts/db_benchmark.py   (uses a temp file; never touches the real database)"""
import json, random, sqlite3, statistics, tempfile, time
from pathlib import Path

from backend.app import migrations, store

N_PAT, N_EVT, N_AUDIT = 20_000, 100_000, 100_000
random.seed(7)
tmp = Path(tempfile.mkdtemp()) / "bench.sqlite3"
store.DB_PATH = tmp
store.init_db()
conn = sqlite3.connect(tmp)
INDEXES = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%' AND name NOT LIKE 'idx_wf_%'")]
defs = {r[0]: r[1] for r in conn.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL")}
conn.execute("BEGIN")
conn.executemany("INSERT INTO patients (patient_id, created_utc, created_by, payload) VALUES (?,?,?,'{}')",
                 [(f"P{i}", f"2026-{1 + i % 12:02d}-{1 + i % 28:02d}T00:00:00Z", "u") for i in range(N_PAT)])
kinds = ["hpo_profile", "diagnosis", "vcf_analysis", "phenotype_assertions"]
conn.executemany("INSERT INTO clinical_events (event_id, patient_id, kind, created_utc, payload) VALUES (?,?,?,?,'{}')",
                 [(f"E{i}", f"P{random.randrange(N_PAT)}", random.choice(kinds), f"2026-{1 + i % 12:02d}-{1 + i % 28:02d}T00:00:00Z") for i in range(N_EVT)])
acts = ["auth.login", "pgx.case_view", "repro.analysis", "assistant.chat", "variants.upload"]
conn.executemany("INSERT INTO audit_log (ts, actor, action, subject, detail) VALUES (?,?,?,?,'')",
                 [(f"2026-{1 + i % 12:02d}-{1 + i % 28:02d}T00:00:00Z", "u", random.choice(acts), "", ) for i in range(N_AUDIT)])
conn.commit()

QUERIES = {
    "events of one patient": "SELECT count(*) FROM clinical_events WHERE patient_id='P4242'",
    "hpo_profile events in a month": "SELECT count(*) FROM clinical_events WHERE kind='hpo_profile' AND created_utc >= '2026-03-01' AND created_utc < '2026-04-01'",
    "audit count by action in range": "SELECT count(*) FROM audit_log WHERE action='pgx.case_view' AND ts >= '2026-03-01' AND ts < '2026-06-01'",
    "patients created in range": "SELECT count(*) FROM patients WHERE created_utc >= '2026-03-01' AND created_utc < '2026-04-01'",
}


def timeit(sql, n=15):
    ts = []
    for _ in range(n):
        t = time.perf_counter(); conn.execute(sql).fetchall(); ts.append((time.perf_counter() - t) * 1000)
    return statistics.median(ts)


for name in INDEXES:
    conn.execute(f"DROP INDEX {name}")
before = {k: timeit(q) for k, q in QUERIES.items()}
for name in INDEXES:
    conn.execute(defs[name])
conn.execute("ANALYZE")
after = {k: timeit(q) for k, q in QUERIES.items()}
print(json.dumps({"rows": {"patients": N_PAT, "clinical_events": N_EVT, "audit_log": N_AUDIT},
                  "median_ms": {k: {"without_indexes": round(before[k], 3), "with_indexes": round(after[k], 3)} for k in QUERIES}}, indent=2))
