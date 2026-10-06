# Testing

| Layer | Command | What it covers |
|---|---|---|
| Backend | `GENOMIND_EMBED_MODEL=none python -m pytest -q` | Unit, API, integration, security, production, AI evaluation, audits (458 tests) |
| Frontend | `cd web && npx vitest run` | Component and view tests, accessibility, error wording, demo and provenance UI (128 tests) |
| Build | `cd web && npm run build` | Production bundle |
| Smoke | `SMOKE_USER=.. SMOKE_PASSWORD=.. python -m scripts.smoke_test --base URL` | 14-step workflow against a running server |
| Performance | `python -m scripts.perf_baseline <label>` | Timed endpoints, writes `docs/perf/<label>.json` |
| ML | `python -m scripts.ml_benchmark` | Regenerates `models/registry.json`, `benchmark.json`, `docs/ML_BENCHMARK.md` |
| AI (live) | `python -m scripts.ai_eval` | 8 live questions through the real model; writes `docs/ai_eval.json` |
| Database | `python -m scripts.db_audit` | Integrity, journal mode, migrations, indexes, orphan rows |

Key suites: `test_master_e2e.py` (Phases 1-15 workflow), `test_phase26_integration.py` (two patients through every module, isolation),
`test_phase27_quality.py` (provenance/conflicts/confirmation), `test_ai_eval.py` (scripted-model evaluation: grounding, citations,
hallucination, injection, authorisation, Hindi/patient-friendly), `test_security.py`, `test_production.py` (readiness, logs, backup/restore),
`test_final_audit.py` (every route requires auth, no debug routes, audit trail, orphan prevention, production config).

Every test gets its own temporary database (`tests/conftest.py`); nothing writes to `data/genomind_dev.sqlite3`.

Not covered: browser-driven automated E2E (the full UI workflow was walked manually in the Vite dev server; see PLAN.md), automated
contrast/screen-reader audits, load testing, the Flutter app, Docker builds.
