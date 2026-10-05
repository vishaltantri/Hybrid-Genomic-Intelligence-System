# Genomera database architecture (Phase 18)

**Engine:** the standard-library `sqlite3` module through `backend/app/store.py` (raw SQL, no ORM, no SQLAlchemy).
**File:** `data/genomind_dev.sqlite3`, or whatever `DATABASE_URL` points at (`sqlite:///relative.db`, `sqlite:////absolute/path.db`).
Any other scheme (for example `postgresql://`) raises a clear error at start-up; PostgreSQL is **not** implemented.

## Connection settings (every connection)
`foreign_keys=ON`, `busy_timeout=10000`, `journal_mode=WAL`, `synchronous=NORMAL`. WAL lets readers proceed while one writer
commits; the busy timeout makes competing writers wait instead of failing (verified by a concurrent-writer test).

## Transactions
Each `store` function is a single statement group inside one connection and commits atomically. For multi-step work use
`with store.transaction() as conn:` (BEGIN IMMEDIATE, commit on success, full rollback on any exception). `save_analysis` uses it.

## Migrations
`backend/app/migrations.py`: ordered, additive, idempotent steps recorded in `schema_migrations`; `store.init_db()` runs the baseline
schema then applies anything pending. Each step runs in its own transaction and rolls back if it fails. Existing data is never
dropped or rewritten (tested against a legacy database). `python -m backend.app.migrations status` shows applied/pending.

| # | Step |
|---|------|
| 1 | baseline schema |
| 2 | `variant_analyses` table (VCF analyses persisted) + indexes |
| 3 | lookup indexes on patient/case columns |

## Tables
users, patients, clinical_events, twin_records, pedigree_* (4), case_evidence, case_reports, referrals, notifications, case_workflow,
workflow_history, audit_log, variant_analyses, schema_migrations.

## VCF analyses
Held in a memory cache for speed and persisted to `variant_analyses` (JSON payload plus queryable columns). After a restart they are
reloaded on demand. If persistence fails the error is logged and the analysis stays available in memory only.

## Measured index effect (synthetic: 20k patients, 100k events, 100k audit rows; median of 15 runs; `python -m scripts.db_benchmark`)
| Query | Without indexes | With indexes |
|---|---|---|
| events of one patient | 15.9 ms | 0.007 ms |
| hpo_profile events in a month | 16.0 ms | 0.145 ms |
| audit count by action in range | 14.7 ms | 0.355 ms |
| patients created in range | 2.1 ms | 0.093 ms |

## Known limits
- Foreign keys are not declared on legacy tables (adding them needs table rebuilds; deferred to avoid data risk). `foreign_keys=ON` is set so new FKs will be enforced.
- There is no background-job queue: VCF analysis runs inside the request (bounded by the 25 MB upload cap and 20 uploads/min).
- Single-node sqlite: not suited to multiple writer processes at scale. Moving to PostgreSQL needs a driver swap in `_connect`, `?` to `%s` placeholders, and a data copy.
