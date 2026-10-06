# GENOMERA

Genomic intelligence and clinical decision-support platform for rare-disease genetics in India. Clinicians, researchers and
ASHA field workers work on **cases**: phenotypes (HPO), VCF variants with ACMG/AMP classification, a ranked differential
diagnosis, pedigree and inheritance analysis, pharmacogenomics, reproductive risk, a Digital Twin with what-if scenarios,
literature evidence, an AI Assistant grounded in the case, clinical reports (PDF/JSON), FHIR export, workflow and
notifications, analytics, and a national view.

**GENOMERA is decision support, not a diagnostic device.** Every ranking is labelled as a model output; only a clinician
can record a confirmed diagnosis. See [Limitations](#limitations).

## What is in this checkout (measured, not aspirational)

| Item | Value |
|---|---|
| Backend | FastAPI, 179 method+path routes, JWT + role-based access, SQLite (WAL) with versioned migrations |
| Frontend | React 18 + Vite + Tailwind, 21 module screens, lazy-loaded (initial JS about 280 KB) |
| Knowledge graph | 362 nodes / 404 edges: 19 diseases, 67 HPO terms, 38 genes, 35 drugs (seed-scale; see Limitations) |
| Tests | 458 backend (pytest) + 128 frontend (Vitest); `npm run build` clean |
| ML | Deterministic Resnik/Bayes diagnosis engine (default), rule-based ACMG engine, lexical NER and HPO mapper; GNN checkpoint present but disabled |

## Quick start (verified commands)

Requirements: Python 3.12+, Node 20+. The knowledge graph file `data/processed/kg.json` must exist (it is generated, not versioned).

```bash
pip install -r requirements.txt psutil
python -m uvicorn backend.app.main:app --port 8000        # API; first start loads the graph (about 15-30 s)

cd web && npm ci && npm run dev                            # http://localhost:5173, proxies /api to :8000
```

Development mode seeds three accounts (`admin`, `clinician`, `asha1`; passwords are in `backend/app/main.py` and are offered by the
sign-in screen **only in the Vite dev server**). Production seeds nothing; see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

Run the checks:

```bash
GENOMIND_EMBED_MODEL=none python -m pytest -q       # backend, about 6 minutes
cd web && npx vitest run && npm run build           # frontend tests and production build
```

## Demo mode

Sign in as a doctor, open **Demo Case**, and create the synthetic case (Wilson disease trio). It is built by the real modules,
labelled "DEMO MODE - Synthetic Data" everywhere (banner, patient list, report, AI context), and resets without touching real
records. Guided steps open each module on the case. Disabled in production unless `GENOMERA_ENABLE_DEMO=1`.

## Documentation

| Document | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, data flow, security model, AI pipeline |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production configuration, health/metrics/logging, backups, smoke test |
| [docs/DATABASE.md](docs/DATABASE.md) | Schema, migrations, `DATABASE_URL`, indexes |
| [docs/TESTING.md](docs/TESTING.md) | Test layout, commands, audits, evaluations |
| [docs/MODELS.md](docs/MODELS.md) | Model inventory, measured metrics, model cards |
| [docs/ML_BENCHMARK.md](docs/ML_BENCHMARK.md) | Generated benchmark report |
| [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) | Final release checklist with verified status |
| [PLAN.md](PLAN.md) | Phase-by-phase build record, decisions and findings |

## Environment variables

See [.env.example](.env.example) (development) and [.env.production.example](.env.production.example). The important ones:
`GENOMERA_ENV`, `GENOMIND_JWT_SECRET`, `GENOMERA_BOOTSTRAP_ADMIN_PASSWORD`, `DATABASE_URL` (`sqlite:///...`),
`GENOMERA_CORS_ORIGINS`, `GENOMERA_LOG_FORMAT`, `GENOMERA_ENABLE_DEMO`, `GENOMERA_ENABLE_DOCS`. The AI Assistant needs a language-model
key in the environment (`GROQ_API_KEY` in `ml_services/config.py`); without one it runs in an explicit offline mode and says so.

## Repository map

```
backend/app/        FastAPI app: routers, security, hardening, store (SQLite), migrations, observability, demo
ml_services/        Domain logic: graph_ai (diagnosis), variants (VCF/ACMG), phenotype, pedigree, twin, evidence, assistant,
                    reports, quality, pharmacogenomics, reproductive, nlp, asha, federated (simulation)
web/                React frontend (src/views, src/components, src/__tests__)
data/seeds/         Committed seed datasets and demo VCFs
models/             Registry (registry.json), benchmark.json, checkpoints
scripts/            ml_benchmark, perf_baseline, db_benchmark, db_audit, backup_db, smoke_test, ai_eval
docs/               Documentation, model cards, performance results
tests/              pytest suites (unit, integration, security, production, AI evaluation, audits)
asha_app/           Flutter offline ASHA app (not built or tested in this repository audit)
```

## Limitations

- **Data scale.** The knowledge graph and phenotype data in this checkout are seed-scale (19 diseases). `PROJECT_REPORT.md` and
  older documents describe a build over the full public datasets (12,880 diseases, 33k-node graph); those raw datasets are not in this
  repository and those numbers were **not reproduced** here. The documented 0.92 hits@5 does not reproduce on this graph (see ML_BENCHMARK).
- **Diagnosis** is a ranking from phenotype similarity and priors, evaluated only on synthetic cases built from the same annotations
  (circular). No real-world outcome validation exists. Probabilities are relative scores, not calibrated confidence.
- **National View** shows simulated data (labelled), not a real registry.
- **AI Assistant** answers can still be wrong in prose. The server removes variant notation, PMIDs, DOIs and ClinVar accessions that
  are not in the case data or retrieved evidence, but it cannot verify clinical reasoning. Voice input/output uses the browser's
  speech APIs and works only where the browser provides them.
- **Access model:** case access is clinician-wide (no care-team model). Rate limiting and metrics are per process. SQLite is the only
  database; PostgreSQL is not implemented.
- **Docker files are untested** (no Docker daemon was available during the audit).
- Not a regulated medical device; no clinical validation has been performed.
