# GENOMERA architecture

## Components

```
Browser (React/Vite SPA, lazy-loaded views, bearer JWT in browser storage)
   |  /api/v1/*  (JSON, SSE for assistant streaming)
FastAPI app (backend/app/main.py)
   |-- middleware: RequestObservability (request id, access log, metrics, safe 500) -> Security (headers, body limits) -> CORS
   |-- routers (28): auth, clinical, phenotype, variants, evidence, diagnosis(+intel), pedigree, twin, pgx, repro, reports, emr(FHIR),
   |                 assistant, search, workflow, analytics, ml_registry, quality, demo, community(ASHA), triage, dashboard, ...
   |-- services registry (backend/app/services.py): lazily builds the engines below, shared per process
   |-- store.py: SQLite (WAL), versioned additive migrations (migrations.py), transactions
ml_services/ (domain logic, no web code)
   graph_ai (knowledge graph + diagnosis engine), variants (VCF, ACMG), phenotype, pedigree, twin, evidence (PubMed client),
   reports (JSON+PDF), quality (provenance/conflicts), assistant (retrieval, orchestrator, guardrails, LLM client), pgx, reproductive, nlp
data/processed/kg.json (knowledge graph, generated)   data/seeds/* (committed seed tables, demo VCFs)   models/* (registry, checkpoints)
```

## Request path and security model
1. Request id assigned; structured log line written on completion (route template only).
2. Body-size and header hardening, CORS (explicit origins), per-route rate limits.
3. `require("perm")` dependency: decodes the JWT, loads the user from the database (deleted users and role changes apply
   immediately), checks the role's permission (`ROLE_PERMISSIONS`). Every API route requires authentication except `/health`,
   `/readiness`, `/api/v1/auth/token` (asserted by `tests/test_final_audit.py`).
4. Object-level rules: patient-role users read only their own record; VCF analyses are private to the uploader unless attached to a
   case (case access is clinician-wide by design); the assistant refuses to use another user's private analysis.
5. Sensitive actions append to `audit_log` (identifiers only).

## Data flow for one case
Patient -> phenotype assertions (events) -> VCF analysis (variants + ACMG, persisted) -> pedigree (members, genotypes from the VCF)
-> diagnosis (engine over phenotypes+variants) -> PGx / reproductive / Digital Twin computed on request from those records ->
evidence (PubMed, saved per case) -> report (assembled server-side with provenance, data-quality and versions; PDF and JSON from the
same stored version) -> FHIR bundle export. Nothing is cached across cases; each module reads the case's stored records.

## Provenance and honesty layer (Phase 27)
`ml_services/quality/service.py` labels each domain's source (Clinician-entered, Laboratory-derived (uploaded VCF), Calculated,
Model-generated, Literature-derived, Synthetic), reports conflicts (same phenotype recorded with different assertions, patient vs
pedigree sex/age), staleness (report older than newer case data) and explicit missing states (Not provided / Not analyzed). The
diagnosis API labels every row "Model ranking"; a clinician confirmation is a separate audited event.

## AI Assistant pipeline (Phase 28)
1. Injection screen on the message (refuses without calling the model).
2. Authorisation (`assistant:chat`, `clinical:read` for case context, object-level analysis checks).
3. Orchestrator picks authorised sources from the question (diagnosis, PGx, reproductive, pedigree, Digital Twin, literature,
   knowledge-graph entity) and builds them with the same permission-checked builders as explicit requests.
4. Prompt with delimited untrusted data; model call through an internal client (provider names never reach the UI).
5. Output guardrail: unsupported variant notation, PMIDs, DOIs and ClinVar accessions are replaced; provider names scrubbed;
   "No supporting evidence was retrieved." added when requested literature is absent. Streaming sends a `correction` event.

## Deployment shape
Single uvicorn process (rate limits and metrics are per process) behind a TLS-terminating proxy that serves `web/dist` and forwards
`/api`. See DEPLOYMENT.md. Observability: `/health`, `/readiness`, `/metrics` (admin), JSON logs.
