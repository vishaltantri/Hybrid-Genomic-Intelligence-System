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
