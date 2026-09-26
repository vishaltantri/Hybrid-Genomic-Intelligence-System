# AGENT_CONTEXT.md — Developer & AI-Agent Handoff

> **Purpose:** everything a new developer (or a future AI agent session) needs to pick this
> project up cold: what recently changed and why, the environment's quirks, what is verified,
> and the exact next steps. Read this together with [README.md](README.md) (how to run) and
> [PROJECT_REPORT.md](PROJECT_REPORT.md) (what was built and measured).

---

## 1. Project snapshot

**GENOMIND-INDIA** — AI decision-support for rare genetic disease diagnosis in India.
Eleven modules: clinical NER (code-mixed Indian languages), HPO mapping, knowledge graph
(33,632 nodes / 311,290 edges), GNN diagnosis (off by default, documented negative result),
India-population priors, PGx, reproductive counselling, XAI, federated learning (simulated
sites), PubMed learning loop, national dashboard. Frontends: FastAPI backend (JWT + RBAC +
FHIR), React dashboard (`web/`), Flutter ASHA app (`asha_app/`).

**State:** implementation complete · 124/124 tests passing · dockerized and verified
end-to-end · release APK built · this document and README added in the current commit.

| Component | Where | Status |
|---|---|---|
| Backend API | `backend/` → :8000 | ✅ healthy, all 11 modules |
| Knowledge graph | `data/processed/kg.json` (gitignored, rebuild via `make etl && make kg-build`) | ✅ built on dev machine |
| React dashboard | `web/` → :5173 | ✅ live-tested, bugs fixed |
| Flutter ASHA app | `asha_app/` | ✅ release APK built (22.2 MB, debug-signed) |
| Test suite | `tests/` | ✅ 124/124 |
| Demo | `.venv/bin/python -m demo.run_demo` | ✅ green |

---

## 2. Overview of recent changes

### Earlier batch (commit `06fc9bd` — live-testing bug fixes)
Five dashboard bugs found by clicking through every view against the real API: XAI panel
rendering, doctor-role RBAC (added `kg:read`, `dashboard:read`), policy-brief is a **POST**
returning `{month, markdown}`, `ReproView` rendering objects as `[object Object]` (added
`prob()` unwrap helper), `KgView` learning-queue key mismatch. All re-verified in the browser.

### Current batch (in this commit)

**Backend / ML:**
- `ml_services/nlp/hpo_mapper.py` — `map_ner_result()` gained a **whole-phrase fuzzy
  fallback**: when NER extracts nothing, map the raw utterance (`ner_result["text"]`) with
  threshold 0.5, confidence ×0.9, `source="whole_phrase_fuzzy"`.
- `ml_services/graph_ai/gnn_diagnosis.py` — added `_match_state()`: case/space-insensitive
  state matching ("tamil nadu" → `tamil_nadu`) used by `diagnose()` so the consanguinity
  prior actually applies instead of silently falling back to 1.0.
- `backend/app/routers/clinical.py` — new **`GET /api/v1/reference`** endpoint (requires
  `clinical:read`): 36 states with consanguinity rates + 23 communities with founder
  diseases, read from the KG (`registry.graph.by_type("State"/"Ethnicity")`).
- `data/seeds/indian_synonyms.csv` — 5 rows mapping "dark circles around eyes" phrasings
  (incl. Hinglish "aankhon ke around dark circles") → `HP:0001106` Periorbital
  hyperpigmentation. Seeds are volume-mounted read-only into the api container, so this is
  live after an api restart (no rebuild).

**Web dashboard:**
- `web/src/api.js` — added `reference()`.
- `web/src/views/DiagnosisView.jsx` — state/community free-text fields replaced with
  **`<select>` dropdowns** populated from `/reference` (labels include consanguinity %, e.g.
  "Andhra Pradesh (26%)"), plus an **"Understood findings" strip** that calls
  `api.mapHpo({text})` and shows which symptoms mapped to HPO (with confidence %) and which
  did not — so clinicians see the pipeline's interpretation before diagnosing.

**Mobile / build:**
- `asha_app/android/gradle/wrapper/gradle-wrapper.properties` — Gradle **8.3 → 8.7**.
- `asha_app/android/app/src/main/AndroidManifest.xml` — added `INTERNET` permission and
  `android:usesCleartextTraffic="true"` (with a comment pointing to HTTPS +
  `networkSecurityConfig` for production).
- Built the release APK: `build/app/outputs/flutter-apk/app-release.apk` (22.2 MB).

**Docs (this commit):**
- `README.md` — created: prerequisites, both quickstart paths (Docker + bare metal), env
  vars, demo accounts, ports, training commands, troubleshooting.
- `AGENT_CONTEXT.md` — this file.
- `PROJECT_REPORT.md` — full build report (data, models, benchmarks, limitations) committed
  for the first time.

---

## 3. Problem & rationale (root causes → decisions)

1. **"Zero findings" for real colloquial input.** Root cause: NER sometimes returns no
   spans for code-mixed phrases ("Aankhon ke around dark black circles"), and the mapper
   only mapped NER output → the whole utterance was silently dropped. Fix: whole-phrase
   fuzzy fallback at a higher threshold (0.5 vs 0.35) with a 0.9 confidence penalty and an
   explicit `source` tag, so downstream consumers can distinguish it from NER-grounded
   mappings. Rationale: catches lay phrasing without polluting precision at equal threshold.
   Companion fix: 5 synonym seed rows give the most common phrasings a high-precision path.

2. **India prior silently ignored.** Root cause: `diagnose()` compared the user's state
   string to canonical ids with exact match; "Tamil nadu" ≠ `tamil_nadu` → consanguinity
   multiplier 1.0. Fix: `_match_state()` normalizes case/whitespace before lookup. Verified:
   "Tamil nadu" now resolves and applies cons 0.28 (multiplier 1.07).

3. **Dropdown data from the backend, not hardcoded in the UI.** `/reference` reads State /
   Ethnicity nodes from the same KG the engine uses — one source of truth, no drift between
   UI options and engine behavior, and consanguinity/founder metadata stays with the data.

4. **Gradle 8.3 → 8.7, not an AGP upgrade.** Root cause of build failure:
   `shared_preferences_android` (transitive of `shared_preferences 2.3.3`) pins its
   buildscript to **AGP 8.5.1**, which requires Gradle ≥ 8.7; the project's Gradle 8.3
   cannot even resolve it. Chose the least-risk path: bump the wrapper only (project AGP
   stays 8.1), verified compatible. Do not downgrade `shared_preferences` instead.

5. **Cleartext HTTP in the release manifest.** The app's field use case is an ASHA worker's
   phone syncing to a clinic/LAN server over `http://` (API_URL is a `--dart-define`, default
   `http://10.0.2.2:8000` for emulators). Without `usesCleartextTraffic`, Android 9+ blocks
   every request and the failure is a silent network error. Accepted trade-off, flagged in
   the manifest comment; production must move to HTTPS.

6. **Toolchain installed to `$HOME`, no sudo.** The build machine had Flutter 3.24.3 and
   Java 21 only. Installed: Android SDK cmdline-tools → `~/android-sdk` (platform 34,
   build-tools 34.0.0 + 33.0.1 auto-installed by AGP, licenses accepted); JDK 17 →
   `~/.jdks/jdk-17.0.20.1+1` because **Gradle 8.x cannot run on Java 21** (class-file major
   version). Wired via `flutter config --android-sdk ~/android-sdk` and
   `flutter config --jdk-dir ~/.jdks/jdk-17.0.20.1+1`; `android/local.properties` has
   `sdk.dir` (gitignored).

7. **Network resilience for heavy downloads.** Two builds died mid-download (Gradle dist
   zip; Maven poms) — the machine's connection drops long transfers. Mitigations: pre-
   downloaded `gradle-8.7-bin.zip` with `curl --retry 5 --retry-all-errors` into
   `~/.gradle/wrapper/dists/gradle-8.7-bin/<md5-of-url>/` so the wrapper skips its own
   fetch; cleared `~/.gradle/caches` once after the corrupted-resolution failure. First
   full build ≈ 12–20 min; warm rebuild ≈ 5 s.

8. **GNN stays off by default.** The HAN result is a documented negative (baseline
   Phenomizer 0.950/0.917 vs full engine 0.9475/0.890 hits@5/MRR on 400 synthetic cases);
   `use_gnn=False` default is deliberate — see PROJECT_REPORT §5.2/§7.

---

## 4. Environment runbook (facts an agent must know)

```bash
cd /home/vct/Desktop/cloud-opencode          # repo root, branch: master
export PATH="$HOME/flutter/bin:$PATH"        # flutter 3.24.3
export JAVA_HOME="$HOME/.jdks/jdk-17.0.20.1+1"   # needed for any gradle/flutter build
```

- **Backend stack:** `docker compose up -d postgres redis neo4j api` — API :8000.
  Health is **`GET /health`** (not `/api/health`); first boot takes ~30 s while the graph loads.
  **Backend code changes require `docker compose build api`**; `data/seeds/` +
  `data/processed/` are volume-mounted read-only, so seed edits are live after restart only.
- **Python:** `.venv` (3.14). Tests: `timeout 500 .venv/bin/python -m pytest tests/ -q`
  (~72 s, offline). Demo: `.venv/bin/python -m demo.run_demo`.
- **Web:** `cd web && npm run dev` → :5173 (Vite proxies `/api` → :8000). If 5173 is taken
  Vite bumps to 5174 — kill the squatter to keep the canonical port.
- **Auth (dev):** `POST /api/v1/auth/token` (OAuth2 form). Users: `admin` /
  `admin-password-change-me`, `clinician` / `changeme` (doctor; has `kg:read` +
  `dashboard:read`), `asha1` / `changeme` (asha).
- **Key API contracts:** `/diagnosis` (POST), `/xai/explain`, `/diseases/{id}`, `/kg/stats`,
  `/clinical/extract`, `/clinical/hpo-map`, `/pgx/check`, `/pgx/coverage`,
  `/reproductive/couple-risk` (⚠ `carrier_probability_partner_a/b` are **objects**
  `{probability,method,note}`), `/dashboard/national` (GET), `/dashboard/policy-brief`
  (**POST** → `{month, markdown}`), `/learning/queue`, `/learning/drift`, `/reference` (NEW).
- **Not in git:** `data/raw/`, `data/processed/` (built KG), model weights
  (`models/**/*.safetensors|bin|onnx|tokenizer.json`), `reports/`, `.env`, `node_modules/`.
  A fresh clone **must** run `make etl && make kg-build` before the bare-metal API works.
- **APK rebuild:**
  `flutter build apk --release --dart-define=API_URL=http://<lan-ip>:8000`
  (default API_URL is emulator-only `http://10.0.2.2:8000`). Output:
  `build/app/outputs/flutter-apk/app-release.apk`.
- **Session hygiene (agent-specific):** background processes die when the Freebuff session
  restarts — relaunch Docker/Vite rather than assuming they survived; a `&`-launched child
  is killed with its shell, so detach long builds with
  `setsid nohup … >/tmp/log 2>&1 &`. Watch disk (use `df -h`; `docker builder prune -f`
  reclaims ~10 GB).

---

## 5. Verification status (what was actually tested)

- ✅ 124/124 pytest pass with all current changes (re-run this session).
- ✅ `flutter analyze` — 0 errors/warnings (8 info lints); widget test passes.
- ✅ API healthy: `{"status":"ok","graph_nodes":33632,...,"modules":["M1"…"M11"]}`.
- ✅ Browser-verified against live API: XAI render, RBAC, policy brief, repro unwrap, KG
  view (earlier batch), dropdowns render + `/reference` returns 36 states / 23 communities,
  user's exact failing case ("Aankhon ke around dark black circles", "Tamil nadu", F) → 3
  results with consanguinity multiplier 1.07, mapper returns `HP:0001106`.
- ✅ APK: built, manifest verified via `aapt dump xmltree` (INTERNET + cleartext present).
- ⚠️ Not yet done: a full click-through of a **Diagnose** submission through the new
  dropdown UI in the browser (the underlying API path was verified via curl).

---

## 6. Current state & handoff

**Git:** branch `master`, history `368da91 → 16c7e2f → 80583e5 → 421ba1c → a54473d →
2d99987 → 06fc9bd → 9a030c5`. Everything is committed and pushed to
`https://github.com/vishaltantri/Hybrid-Genomic-Intelligence-System.git` (remote `origin`,
branch `master`).

**Open items, in priority order:**

1. **National dashboard data (highest value, user interested but not confirmed):** replace
   simulated counts in `NationalView` / `/dashboard/national` with an estimation model —
   Census population × Orphanet prevalence × NFHS-5 consanguinity adjustment, calibrated to
   published ICMR NRROID aggregates, with the estimation method surfaced in `data_note`.
2. **Browser click-through of the new dropdown UI** end-to-end (select state/community →
   diagnose → open XAI) to close the last verification gap.
3. **Release signing:** the APK is debug-signed. Generate a keystore, add
   `signingConfigs.release`, define `versionCode/versionName` policy before distributing.
4. **Transport security:** move the app+server to HTTPS (or at minimum
   `networkSecurityConfig` pinning the clinic host) and retire `usesCleartextTraffic`.
5. **Server hardening before any real deployment:** `GENOMIND_JWT_SECRET`, remove/rotate
   the three demo users, restrict CORS, put Postgres/Neo4j off the LAN.
6. **ASHA voice:** record 1–2 h of real dialect audio to move speech input from
   "wired and testable" to field quality.
7. **CI (optional):** GitHub Actions running `pytest` + `flutter analyze` on PRs.
8. **GNN:** re-enable only when real outcome-labeled data exists; the checkpoint and
   negative-result rationale are preserved (see PROJECT_REPORT §5.2, §7).

**Known limitations (do not "fix" blindly):** benchmark cases are synthetic; national
dashboard numbers are simulated and labelled as such; NER hand-gold set is 25 sentences
(0.800 span F1 is a data limit — feed clinician corrections back through the active-learning
queue); federated sites are simulated but the DP/secure-aggregation machinery is real.

**Gotchas that already bit once:** `/health` vs `/api/health` · policy-brief is POST ·
carrier probabilities are objects, not floats · Gradle needs JDK 17 not 21 ·
`shared_preferences_android` pins AGP 8.5.1 (don't downgrade the plugin) · big downloads
die on this connection (use `curl --retry`) · fresh clones must build the KG ·
`make demo` pointed at a non-existent `scripts/run_demo.py` and was corrected to
`python -m demo.run_demo`.
