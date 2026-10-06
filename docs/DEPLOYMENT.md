# Genomera — Production deployment

Status of each path below, as tested on 2026-10-06 (Windows 11, Python 3.13, Node 22.18.0):

| Path | Status |
|---|---|
| Backend started with `GENOMERA_ENV=production` via uvicorn | Verified: 14/14 smoke steps, readiness, JSON logs, metrics |
| Frontend `npm run build` | Verified |
| Backup, verify, restore (`scripts/backup_db.py`) | Verified, including restoring into a fresh file and starting the app on it (tests) |
| `Dockerfile`, `web/Dockerfile`, `docker-compose.prod.yml` | Written but NOT built or run: no Docker daemon was available. Treat as untested. |
| TLS / reverse proxy | Not provided. Terminate HTTPS in front of the app (see "HTTPS"). |

## Prerequisites
Python 3.12+ with `pip install -r requirements.txt` (add `psutil` for resource metrics), Node 20+ for the web build, and the knowledge graph file `data/processed/kg.json` (generated from the committed seeds by `python -m ml_services.etl.kg_build`; it is not versioned).

## Environment variables
Copy `.env.production.example`; every value is explicit. Key variables:

| Variable | Purpose |
|---|---|
| `GENOMERA_ENV=production` | Refuses to start with a default or short JWT secret; seeds no demo users; disables demo mode unless `GENOMERA_ENABLE_DEMO=1`; no localhost CORS default |
| `GENOMIND_JWT_SECRET` | 32+ random characters (`python -c "import secrets; print(secrets.token_urlsafe(48))"`) |
| `GENOMERA_BOOTSTRAP_ADMIN_PASSWORD` | 12+ chars; creates the first `admin` only when no users exist. Remove after first start |
| `DATABASE_URL` | `sqlite:///relative/path.db` or `sqlite:////absolute/path.db` (four slashes for an absolute POSIX path; a bare path is rejected) |
| `GENOMERA_CORS_ORIGINS` | Exact https origins; empty = no cross-origin access (use this when a proxy serves web and API on one origin) |
| `GENOMERA_LOG_FORMAT` / `GENOMERA_LOG_LEVEL` | `json` or `text`; level |

## Database and migrations
SQLite with WAL. Migrations run automatically on startup and are additive and idempotent: `python -m backend.app.migrations status`.

## Start the backend
```bash
GENOMERA_ENV=production GENOMIND_JWT_SECRET=... GENOMERA_BOOTSTRAP_ADMIN_PASSWORD=... \
DATABASE_URL=sqlite:////var/lib/genomera/genomera.sqlite3 GENOMERA_LOG_FORMAT=json \
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```
Use `--no-access-log`: uvicorn's access log records full URLs including search text; Genomera writes its own structured access log with route templates only. Run a single worker unless you move rate limiting and metrics to a shared store (both are per process).

## Build and serve the frontend
```bash
cd web && npm ci && npm run build      # output in web/dist
```
Serve `web/dist` from any static server and proxy `/api/` (and optionally `/health`, `/readiness`) to the backend. `web/nginx.conf` is a starting point. Do not expose `/metrics` publicly.
The development quick-fill accounts on the sign-in screen exist only in the Vite dev server; the production bundle contains no default credentials (checked by a test).

## HTTPS
The app does not terminate TLS. Put it behind a TLS-terminating proxy, pass `X-Forwarded-*`, and set `GENOMERA_CORS_ORIGINS` to the https origin only if the web app is on a different origin. Tokens are bearer JWTs kept in browser storage; there are no cookies.

## Health, readiness, metrics, logs
- `GET /health` — liveness: the process is up and the graph is loaded.
- `GET /readiness` — 200 only when the database answers, all migrations are applied and the knowledge graph is loaded; otherwise 503 with the failing check.
- `GET /metrics` (admin token) — Prometheus text: request counts and latency histograms by route template, errors, in-flight, AI requests, report generations, database up/ping, process memory/CPU (with psutil). Per process; reset on restart. There is no background job system, so there are no job metrics.
- `GET /api/v1/ops/status` (admin) — the same plus security posture (default-password accounts, secret strength, CORS).
- Logs: one JSON line per request (`ts, level, request_id, method, route, status, duration_ms`) and server-side stack traces for unhandled errors. Clients get `{"detail":"Internal server error","request_id":...}`; search the logs for that id. Credentials are masked by a log filter and request bodies, headers and query strings are never logged.

## Backups and restore
```bash
python -m scripts.backup_db backup --out /var/backups/genomera     # online-consistent copy + manifest, verified after writing
python -m scripts.backup_db verify /var/backups/genomera/genomera-<stamp>.sqlite3
python -m scripts.backup_db restore /var/backups/genomera/genomera-<stamp>.sqlite3 --db /var/lib/genomera/genomera.sqlite3 --force
```
Backups are not scheduled by the application; run the first command from cron or a task scheduler and copy the files off the host. Success is only printed after the file is re-opened, its SHA-256 and `PRAGMA integrity_check` are checked and row counts match the manifest. Restore verifies first, refuses to overwrite without `--force`, and keeps the replaced file as `*.pre-restore-<stamp>`. Stop the API before restoring over a live database.

## Rollback
Code: redeploy the previous version. Data: migrations only add objects, so an older build runs against a newer schema; if you must undo data changes, restore the last verified backup as above.

## Smoke test
```bash
SMOKE_USER=admin SMOKE_PASSWORD=... python -m scripts.smoke_test --base http://127.0.0.1:8000
```
Covers health, readiness, login, patient, phenotypes, VCF analysis, diagnosis, PGx, reproductive, Digital Twin, report and PDF, search, AI Assistant and metrics. It creates one test patient, so run it against staging or a fresh deployment.

## Troubleshooting
- Refuses to start: read the first log line; the usual causes are a short `GENOMIND_JWT_SECRET` or an invalid `DATABASE_URL`.
- `DATABASE_URL scheme not supported: 'C'`: use `sqlite:///C:/path/db.sqlite3`, not a bare path.
- `/readiness` 503: the body names the failing check (database unreachable, pending migrations, graph missing).
- 429 responses: per-process rate limits (see `/api/v1/ops/status`).
- Nobody can sign in on a fresh production start: set `GENOMERA_BOOTSTRAP_ADMIN_PASSWORD` and restart.

---

# Deployment — Running Genomind-India

## Quickest run (no Docker)

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
make etl          # parse real datasets in data/raw -> data/processed
make kg-build     # build the knowledge graph
make api          # FastAPI dev server on http://localhost:8000
```

Interactive docs: `http://localhost:8000/docs`

## Full stack (Docker)

```bash
make docker-up    # Postgres + Redis + Neo4j + MLflow + Label Studio + API
make docker-down  # stop everything
```

Services:

| Service | Port | Purpose |
|---|---|---|
| API (FastAPI) | 8000 | All endpoints below |
| Postgres | 5432 | Users, audit, clinician feedback |
| Redis | 6379 | Caching, job queue |
| Neo4j | 7474 / 7687 | Optional graph store (JSON fallback is default) |
| MLflow | 5000 | Model registry / experiment tracking |
| Label Studio | 8080 | Clinician correction UI for the NER loop |

## Key API endpoints

| Endpoint | What it does |
|---|---|
| `POST /api/v1/auth/token` | OAuth2 login (form) → JWT. Dev users: `admin`/`admin-password-change-me`, `clinician`/`changeme`, `asha1`/`changeme` |
| `POST /api/v1/diagnosis` | Symptoms (text or hpo_ids, + state/community/sex) → ranked differential with uncertainty and explanations |
| `POST /api/v1/clinical/extract` | Text → structured findings (Hindi/Hinglish/English) |
| `POST /api/v1/pgx/check` | Prescription (drugs[], known_genotypes, state/community) → drug–gene alerts with Indian allele frequencies |
| `POST /api/v1/reproductive/couple-risk` | Two partners (community, state, relation) → carrier risk table + multilingual report |
| `GET  /api/v1/triage/questionnaire` | ASHA questionnaire (cached by the Flutter app for offline use) |
| `POST /api/v1/triage/answers` / `/text` | Questionnaire answers or ASR transcript → red/amber/green referral |
| `POST /api/v1/triage/sync` | Batched offline ASHA records → community alerts |
| `GET  /api/v1/dashboard/national` | State-wise cases, access gaps, consanguinity rates (labelled simulated) |
| `GET  /api/v1/learning/queue` · `/drift` | Active-learning queue and model-drift status |
| `POST /api/v1/federated/simulate?rounds=N` | Multi-hospital federated training simulation |
| `POST /api/v1/emr/fhir` | FHIR bundle → engine input |
| `GET  /health` | Service + module status |

## Health checks

```bash
curl localhost:8000/health              # service + module status
.venv/bin/python -m pytest tests/       # 124 tests, ~80 s
.venv/bin/python demo/run_demo.py       # end-to-end: NER → diagnosis → PGx → counseling → triage → reports
```

Frontends: `web/` is the clinician React console (`npm install && npm run dev`, port 5173, proxies /api to :8000). `asha_app/` is the Flutter ASHA app (`flutter run`, API_URL build flag for the backend address; questionnaire caching + SQLite queue make it offline-first).

## Production notes (honest list)

- **Secrets**: JWT keys, DB passwords via environment (`.env`); never commit them. `.env.example` documents the variables.
- **Data**: `data/raw/` holds ~66 MB of third-party downloads — re-fetchable, git-ignored. The built graph (`data/processed/kg.json`) regenerates with `make etl && make kg-build`.
- **Models**: big weights (~2 GB) re-download/retrain from `docs/TRAINING_RECIPES.md`; the 428 KB GNN checkpoint is tracked in git.
- **Scale**: one engine call scores all 12,880 diseases in ~5 ms warm (vectorized); a single uvicorn worker handles clinical demo load comfortably; scale horizontally behind a proxy for real hospital traffic.
- **Compliance**: patient data never leaves the deployment in federated mode (DP noise + aggregation only). The national dashboard uses simulated data and says so on-screen. Not a certified medical device — decision-support positioning, clinician-in-the-loop by design.
- **Offline ASHA use**: the Flutter app bundles the triage checklist and queues API syncs for when connectivity returns.
