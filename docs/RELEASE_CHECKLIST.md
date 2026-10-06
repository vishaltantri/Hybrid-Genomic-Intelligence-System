# GENOMERA release checklist (Phase 30)

Status words: **PASS** = implemented and verified by an automated test or a live run recorded in PLAN.md; **PARTIAL** = works but with
a stated gap; **BLOCKED** = cannot be completed here; **NOT APPLICABLE**. Clinical validity is outside the scope of every item (no
clinical validation has been performed) and is never implied by PASS.

| Item | Status | Evidence / gap |
|---|---|---|
| Authentication | PASS | JWT, DB-backed user check, login throttling; production seeds no users; default login 401 in a production-mode server |
| RBAC | PASS | `ROLE_PERMISSIONS`; every route requires auth (`test_final_audit`); role matrix tests |
| Patient isolation | PARTIAL | Patient role sees only own record; analyses private to uploader unless attached to a case. Case access is clinician-wide (no care-team model) |
| Case management | PASS | Create/open/associate verified across modules (`test_phase26_integration`) |
| HPO | PARTIAL | Storage, assertions, normalisation PASS; mapper top-1 0.386 on 57 phrases; ontology is seed-scale (67 terms) |
| Diagnosis | PARTIAL | Engine works and is labelled a model ranking; clinician confirmation separate; evaluated only on circular synthetic cases |
| VCF | PASS | Upload validation, gzip, limits, persistence, unknown-case handling |
| Variant Intelligence | PASS | Normalisation, annotation, prioritisation; deterministic |
| ACMG | PARTIAL | Rule-based engine, calculated classifications; not a laboratory classification |
| Evidence | PASS | Live PubMed retrieval verified; source, date, retrieval time kept; no invented grades |
| NLP | PARTIAL | Lexical backend active; F1 0.88 on 25 non-held-out sentences |
| Knowledge Graph | PARTIAL | Explorer, search, filtering work; graph is seed-scale (362 nodes, 19 diseases) |
| Pedigree | PASS | Members, relationships, genotypes from VCF, inheritance/segregation, tested |
| Digital Twin | PASS | Built from stored case data; scenarios recompute engines; no outcome validation |
| AI Assistant | PARTIAL | Orchestration, grounding, guardrails, authorisation tested (34 scripted checks; live 8/8). Prose can still be wrong; voice depends on browser APIs and was not verified end to end |
| PGx | PASS | From VCF genotypes and bundled tables; live answer used CYP2C19 *2/*2 from the case |
| Reproductive Genetics | PASS | Calculated from pedigree/genotypes; arithmetic unit-tested |
| National View | PARTIAL | Real India map and detail panel; data is simulated and labelled as such; no real registry |
| Clinical Reports | PASS | JSON+PDF from one stored version; provenance, quality and versions included; synthetic labelling |
| FHIR / EMR | PARTIAL | Case export validates structurally and keeps ids consistent; no live EMR/ABDM connection exists |
| ASHA | PARTIAL | Web triage/referral flows tested; the Flutter app was not built or tested |
| Workflow | PASS | Assign, status, review, finalise with real notifications |
| Notifications | PASS | Only for real events; honest empty state |
| Global Search | PASS | Results open the real entity (cases, reports, variants, diseases) |
| Analytics | PASS | Aggregates from stored data, exports, honest empty states |
| Security | PARTIAL | See PLAN.md section on the final audit. Remaining: bearer tokens in browser storage, no per-token revocation, per-process rate limits |
| Database | PARTIAL | WAL, versioned migrations, indexes, integrity check, backup/restore verified; no foreign-key constraints (app-enforced); legacy orphan rows exist in the developer database (see db_audit) |
| ML Benchmarking | PASS | Real measured numbers, caveats, "Not evaluated" where no ground truth |
| Testing | PARTIAL | 458 backend + 128 frontend pass; no automated browser E2E or contrast/screen-reader audit |
| Performance | PASS | Measured (docs/perf); initial JS 282 KB; endpoints under 30 ms except report create about 110 ms and PDF about 230 ms |
| Accessibility | PARTIAL | Labels, landmarks, keyboard, focus, 0 unlabelled controls on 21 routes at 3 widths; no automated contrast or screen-reader testing |
| Responsive UI | PASS | 21 routes at 375/768/1280: no horizontal overflow, no alerts |
| Demo Mode | PASS | Real services, labelled, resettable, disabled in production by default |
| Deployment | PARTIAL | Production-mode uvicorn verified (readiness, smoke 14/14, no default credentials, docs hidden); Docker/nginx files untested; no TLS provided |
| Observability | PASS | `/readiness`, `/metrics`, JSON logs, request ids, safe 500s |
| Documentation | PASS | README, ARCHITECTURE, DEPLOYMENT, DATABASE, TESTING, MODELS, this checklist; stale claims in PROJECT_REPORT.md flagged |

## Release decision
**RELEASE CANDIDATE — BLOCKED** for production clinical use. Blockers:
1. No clinical validation of any model or of the diagnosis ranking; evaluation is synthetic and circular.
2. The knowledge graph and phenotype data are seed-scale here; documented full-scale numbers were not reproduced.
3. Docker/compose deployment files were never built or run (no daemon); no TLS termination is provided.
4. Case access is clinician-wide; bearer tokens live in browser storage; rate limits/metrics are per process.
5. No automated browser E2E, accessibility contrast/screen-reader audit, or Flutter app verification.
