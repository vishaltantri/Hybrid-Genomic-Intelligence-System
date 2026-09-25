# GENOMIND-INDIA

AI decision-support platform for **rare genetic disease diagnosis in India**. Clinicians and ASHA
health workers enter symptoms in Hindi, Hinglish, Tamil or English; the system maps them to HPO
terms, ranks differentials over a 12,880-disease knowledge network, adjusts the ranking with
**Indian population genetics** (state consanguinity, community founder effects, sex-linked
inheritance), and explains every answer. Also covers pharmacogenomics safety, reproductive/carrier
counselling, federated learning, and a national dashboard.

**Status:** all 11 modules functional · **124/124 automated tests passing** · dockerized ·
web dashboard + offline-first Android APK for ASHA workers. See [PROJECT_REPORT.md](PROJECT_REPORT.md)
for metrics (NER F1, HPO retrieval, 400-case diagnosis benchmark) and honest limitations.

---

## Repository map

```
ml_services/          11 AI/ML modules (nlp, etl, graph_ai, pharmacogenomics,
                      reproductive, xai, federated, asha, learning_pipeline)
backend/              FastAPI app: routers, JWT auth + RBAC, FHIR, services registry
web/                  React (Vite) clinician dashboard
asha_app/             Flutter offline-first ASHA app (Android/iOS)
data/raw              Third-party datasets (downloaded, not in git)
data/seeds/           Hand-built Indian datasets (committed)
data/processed/       Built knowledge graph (generated — NOT in git, must be built)
models/               Trained checkpoints (weights gitignored; gnn_han.pt tracked)
demo/run_demo.py      End-to-end 11-module demo
tests/                7 pytest files, 124 tests
docs/                 DEPLOYMENT, TRAINING_RECIPES, DATASETS, PATENT_CLAIM_MAP
```

## Prerequisites

| Tool | Version | Needed for |
|---|---|---|
| Docker + Compose | any recent | Backend stack (recommended path) |
| Python | 3.11+ | Bare-metal API, ETL, tests (developed on 3.12/3.14) |
| Node.js | 18+ | Web dashboard |
| Flutter | 3.24+ | Mobile app (optional) |
| JDK 17 + Android SDK | — | Android APK builds (optional) |

~6 GB free disk for a full data + model rebuild.

## Quickstart A — Docker (recommended)

```bash
git clone https://github.com/vishaltantri/Hybrid-Genomic-Intelligence-System.git
cd Hybrid-Genomic-Intelligence-System

# build the API image, then start Postgres + Redis + Neo4j + API
docker compose build api
docker compose up -d postgres redis neo4j api

# wait for startup (first boot loads the 33k-node graph; check until it answers)
curl http://localhost:8000/health
# → {"status":"ok","graph_nodes":33632,"graph_edges":311290,"modules":["M1",...,"M11"]}
```

The Docker API mounts `data/processed` from the host (read-only). If the repo was cloned fresh,
`data/processed` does not exist yet — either build it once via the bare-metal path below
(`make etl && make kg-build`) and restart the api container, or run everything bare-metal.

API docs: http://localhost:8000/docs · Neo4j browser: http://localhost:7474 (neo4j / genomind_dev_password)

### Demo accounts (development only — change before any real deployment)

| User | Password | Role |
|---|---|---|
| `admin` | `admin-password-change-me` | admin |
| `clinician` | `changeme` | doctor |
| `asha1` | `changeme` | asha |

```bash
# get a token (OAuth2 password form)
curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -d "username=clinician&password=changeme"
```

## Quickstart B — bare metal

```bash
git clone https://github.com/vishaltantri/Hybrid-Genomic-Intelligence-System.git
cd Hybrid-Genomic-Intelligence-System

make venv          # creates .venv
make install       # installs requirements.txt (core deps; CPU-friendly)

# REQUIRED for a fresh clone: build the knowledge graph
# (data/processed/ is generated and gitignored)
make etl           # parse third-party datasets → data/processed
make kg-build      # build the 33k-node / 311k-edge graph (uses Neo4j if up, else JSON)

# environment: copy the template and edit; defaults match the Docker stack ports
cp .env.example .env
#   GENOMIND_JWT_SECRET   – change for anything non-local
#   NEO4J_*, POSTGRES_DSN, REDIS_URL – only needed if you run those services

make api           # FastAPI on http://localhost:8000 (/docs for Swagger UI)

# verify
.venv/bin/python -m pytest -q        # 124 tests, ~2 min
.venv/bin/python -m demo.run_demo    # end-to-end 11-module walkthrough
```

### Web dashboard (clinician)

```bash
cd web
npm install
npm run dev        # http://localhost:5173 — proxies /api → localhost:8000
```

Log in with a demo account above. Views: Diagnosis (with state/community dropdowns and
live HPO mapping), XAI, PGx, Reproductive, Knowledge Graph, National, Learning, Reference.

### Mobile app (ASHA, optional)

```bash
cd asha_app
flutter pub get
flutter run                       # emulator: API defaults to http://10.0.2.2:8000

# release APK pointing at a LAN API server:
flutter build apk --release \
  --dart-define=API_URL=http://<your-lan-ip>:8000
# output: build/app/outputs/flutter-apk/app-release.apk
```

Android builds need JDK 17 (`flutter config --jdk-dir <path>`) — Gradle 8.7 fails on JDK 21.
The release manifest allows cleartext HTTP so field workers can sync to a plain-HTTP LAN
server; switch to HTTPS + `networkSecurityConfig` for production.

## Default ports

| Service | Port |
|---|---|
| FastAPI | 8000 (`/health`, `/docs`) |
| Vite dashboard | 5173 |
| Postgres | 5432 |
| Redis | 6379 |
| Neo4j | 7474 (HTTP) / 7687 (Bolt) |
| MLflow / Label Studio / Adminer | 5000 / 8080 / 8081 (optional extras) |

## Training the ML models (optional, GPU recommended)

The API and demo run without model weights (lexical fallbacks). To retrain:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install torch-geometric
make etl && make kg-build
.venv/bin/python -m ml_services.nlp.train_clinical_ner
.venv/bin/python -m ml_services.nlp.train_hpo_mapper
.venv/bin/python -m ml_services.graph_ai.han_model
```

Recipes and expected metrics: [docs/TRAINING_RECIPES.md](docs/TRAINING_RECIPES.md),
[PROJECT_REPORT.md](PROJECT_REPORT.md).

## Troubleshooting

- **Health check is `/health`**, not `/api/health`.
- **First API start takes ~30 s** — it loads the full knowledge graph before answering.
- **Backend code changes require `docker compose build api`** (the image copies the code;
  only `data/seeds` and `data/processed` are volume-mounted, so seed CSV edits are live
  after an api restart with no rebuild).
- **Port 5173 busy** → Vite will pick 5174; stop the other process to keep the canonical port.
- **`make demo` fails after a fresh clone** → run `make etl && make kg-build` first.

## More documentation

- [PROJECT_REPORT.md](PROJECT_REPORT.md) — full build report: data, models, benchmarks, limitations
- [AGENT_CONTEXT.md](AGENT_CONTEXT.md) — handoff/runbook for developers and AI agent sessions
- [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) — module-by-module tour
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — API endpoint reference and deployment guide
- [docs/PATENT_CLAIM_MAP.md](docs/PATENT_CLAIM_MAP.md) — claimed innovations → implementations
