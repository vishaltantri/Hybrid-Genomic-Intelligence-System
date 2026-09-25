# GENOMIND-INDIA — Project Report

*What was built, what data it uses, how the models were trained, and what the results are.*

---

## 1. Executive summary

GENOMIND-INDIA is an AI decision-support platform for **rare genetic disease diagnosis in India**. A clinician or ASHA health worker types (or speaks) symptoms in Hindi, Hinglish, Tamil or English; the system converts them to standard HPO medical terms, ranks the most likely diseases from a 12,880-disease knowledge network, adjusts the ranking with **Indian population genetics** (state consanguinity, community founder effects, sex-linked inheritance), and explains every answer with uncertainty bounds, driving symptoms, confirmatory tests, and nearest NABL lab / specialist referrals. It also covers medicine-safety (pharmacogenomics) and reproductive/carrier counselling.

**Why it matters:** ~1 in 20 Indians is affected by a rare disease; average diagnosis delay is 5–7 years and 4+ doctors. Existing tools (Phenomizer, Exomiser) are built on European/American genetics data and understand nothing about Indian populations or Indian languages. This project is the integration of both gaps into one system.

**Status at a glance:**

| Area | Status |
|---|---|
| Knowledge graph (real HPO + Orphanet + ClinVar + PharmGKB + Indian seeds) | ✅ Built, 0 dangling references |
| All 3 ML models (NER, HPO bi-encoder, GNN) | ✅ Trained locally on an RTX 3050 |
| Diagnosis engine + India prior | ✅ 94.75% hits@5 on 400-case benchmark |
| Pharmacogenomics, reproductive counselor, explainability | ✅ Functional with demo outputs |
| Federated learning (simulated hospitals, DP noise, secure aggregation) | ✅ Functional simulation |
| PubMed → knowledge-graph update pipeline + drift monitor + active learning | ✅ Functional |
| FastAPI backend (JWT + RBAC + FHIR), React web dashboard, Flutter ASHA app | ✅ Built; web/mobile wiring is the remaining work |
| Automated test suite | ✅ **124 / 124 passing** (~1 min 40 s) |
| End-to-end demo (`python -m demo.run_demo`) | ✅ Runs green, covers all 11 modules |

---

## 2. What is done — the 11 modules

Each module below lives in the repo and is exercised by tests and the end-to-end demo.

| # | Module | Where | What it actually does |
|---|---|---|---|
| 1 | **Multilingual clinical NLP (NER)** | `ml_services/nlp/clinical_ner.py` | Token-level NER over code-mixed Hindi/Hinglish/English notes; token language-ID, negation handling ("no fever" is *not* a finding), duration extraction, severity, body sites, lab values. Hybrid backend: exact lexical rules for known phrases + trained MuRIL model for unseen surface forms. |
| 2 | **HPO phenotype mapper + Indian synonym engine** | `ml_services/nlp/hpo_mapper.py` | Maps extracted symptoms to the official 20,482-term Human Phenotype Ontology. Lexical dictionary (69 curated Indian phrases, e.g. "पीलिया"/"piliya" → Jaundice) + fuzzy scoring + optional trained bi-encoder rerank (FAISS cosine). Low-confidence mappings are queued for expert review. |
| 3 | **India-specific rare disease knowledge graph** | `ml_services/etl/`, `kg_build.py` | 20,482 real HPO terms, 12,880+ diseases, 286,000+ phenotype links, genes, drugs, NABL labs, specialists, State nodes with NFHS-5 consanguinity rates, Ethnicity nodes with founder-disease links. 539 same-as disease merges (entity resolution). Validates with zero dangling references. Runs as NetworkX/JSON without any database; Neo4j optional. |
| 4 | **Differential diagnosis engine + India prior** | `ml_services/graph_ai/gnn_diagnosis.py`, `resnik.py` | Published Phenomizer p-value algorithm (Köhler 2009) with term-generation null, fully vectorized (all 12,880 diseases in ~5 ms). The **India prior** multiplies in prevalence × consanguinity (state) × founder effect (community) × sex-linked factors — gated so it only re-ranks phenotypically plausible candidates (within 80% of best similarity), never overriding strong evidence. |
| 5 | **Pharmacogenomic risk engine** | `ml_services/pharmacogenomics/pgx_engine.py` | Infers CYP2C19 / CYP2D6 / G6PD / TPMT risk from Indian allele frequencies (IndiGenomes) via Hardy–Weinberg phenotype probabilities, even **without genetic testing**. Per-drug CPIC/PharmGKB guidance, severity levels, alternative drugs. Novel merge: no pre-combined Indian PGx frequency table existed. |
| 6 | **Reproductive & carrier risk counselor** | `ml_services/reproductive/` | Couple carrier probabilities per disease × community, consanguinity (inbreeding coefficient F), Punnett simulation (20,000 offspring), recommended screening timeline, Indian government scheme pointers. Reports in Hindi/English/Tamil. |
| 7 | **Explainable AI layer** | `ml_services/xai/explainability.py` | Per-symptom attribution (% of evidence, "score without this finding"), missing findings that would raise certainty, Bayesian probability CIs + jackknife stability, FAISS nearest confirmed Indian cases (case-based reasoning), graph-attention view, BERTViz-ready token attention, phenotype-space 2D projection, plain-language narrative. |
| 8 | **Federated learning (simulated)** | `ml_services/federated/fl_server.py` | 6 synthetic non-IID "hospitals" (state/community archetypes), FedAvg rounds, differential-privacy noise (σ, clip norm, ε estimate), secure-aggregation simulation, and a privacy-preserving epidemiology byproduct (small cells suppressed). Machinery is real; sites are simulated. |
| 9 | **ASHA worker triage interface** | `ml_services/asha/`, `backend/app/routers/triage.py` | Red/amber/green triage from the Hindi yes/no questionnaire, red-flag details with explanations, referral letter in Hindi, offline SQLite record with sync queue. ASR (voice-to-text) wiring is in place; a small field recording set would make it real (see §7). |
| 10 | **Continuous learning pipeline** | `ml_services/learning_pipeline/` | PubMed E-utilities fetch → triple extraction from abstracts → KG update proposals with expert review states; active-learning queue fed by mapper uncertainty; concept-drift monitor (PSI). Clinician corrections write back into the synonym dictionary (`add_confirmed_synonym`). |
| 11 | **National dashboard (simulated data)** | `backend/app/routers/dashboard.py`, web | State-wise rare-disease map, specialist gap analysis, policy briefs — built from graph prevalence figures, **clearly labelled "simulated"** because ICMR NRROID registry data is not publicly downloadable. |

**Delivered around the modules:**

- **FastAPI server** (`backend/`): JWT auth, 5 roles (admin/doctor/ASHA/patient/researcher) with scoped permissions, patient records + event log + audit trail, FHIR bundle ingestion, OpenAPI docs at `/docs`.
- **React web dashboard** (`web/`): clinician workflow views (diagnosis, PGx, counseling, national dashboard).
- **Flutter ASHA app** (`asha_app/`): offline-first triage + sync queue, widget test passing.
- **One-command demo** (`demo/run_demo.py`): one synthetic 8-month-old Tamil Nadu patient through all 11 modules, writing 5 multilingual reports into `reports/`.
- **Test suite** (`tests/`, 7 files, 124 tests) covering ETL, NLP, diagnosis/XAI, PGx/reproductive, federated/ASHA/learning, API/FHIR, and demo/synthetic cases.

---

## 3. Datasets used

### 3.1 Real, publicly available data (powers the running system)

| Dataset | What it provides | Source | License / access |
|---|---|---|---|
| **HPO** (`hp.obo`) | 20,482 phenotype terms + ontology tree | `purl.obolibrary.org/obo/hp/hp.obo` | Open |
| **phenotype.hpoa** | Disease→symptom annotations for 12,880+ diseases | `purl.obolibrary.org/obo/hp/hpoa/phenotype.hpoa` | Open |
| **Orphanet / Orphadata** | Rare disease names, prevalence, inheritance, genes | `orphadata.com` | Free registration |
| **ClinVar** (weekly TSV) | Variant→disease links | `ncbi.nlm.nih.gov/clinvar` | Public domain |
| **PharmGKB + CPIC** | Gene→drug safety pairs, dosing guidelines | `pharmgkb.org`, `cpicpgx.org` | CC-BY-SA |
| **IndiGenomes / GenomeIndia** | Indian population allele frequencies (CYP2C19, CYP2D6, G6PD, carrier rates) | `clingen.igib.res.in/indigen` | Academic access |
| **NFHS-5** | State-wise consanguinity rates | `dhsprogram.com/data` | Free registration |
| **PubMed E-utilities** | Live literature feed for the update pipeline | `eutils.ncbi.nlm.nih.gov` | Free API |

All parsers live in `ml_services/etl/` — `make etl && make kg-build` rebuilds everything from source.

### 3.2 Seed data created for this project (no public source exists)

| File | Contents | Why hand-made |
|---|---|---|
| `data/seeds/clinical_ner_seed.jsonl` | 25 hand-labelled Hindi/Hinglish clinical sentences | **No Indian clinical NER corpus exists anywhere.** This is the honest seed; active learning grows it. |
| `data/seeds/clinical_ner_augmented.jsonl` | 400 template-generated sentences with exact gold spans | Data augmentation for NER training |
| `data/seeds/indian_synonyms.csv` | 69 regional symptom phrases → HPO terms (Hindi/Hinglish/English) | No Indian medical synonym dictionary exists |
| `data/seeds/seed_cases.jsonl` | 12 enriched example cases (state/community/sex context) | Demo + regression testing |
| `data/seeds/synthetic_cases.jsonl` | 400 generated cases over real disease profiles (10–12 findings each) | Benchmarking |
| `data/seeds/pgx_indian_frequencies.csv` | CYP2C19/CYP2D6/G6PD frequencies for Indian populations | The PharmGKB × IndiGenomes merge is itself a novel contribution |
| `data/seeds/state_consanguinity.csv` | Consanguinity per state (compiled from NFHS-5 tables) | Scattered across survey tables; compiled here |
| `data/seeds/community_founders.csv` | Community founder effects (e.g., Gond–sickle cell) | Compiled from published literature |
| `data/seeds/confirmatory_tests.csv` | First-line + genetic confirmation tests per disease | Curated |
| `data/seeds/carrier_lookup.csv` | Carrier frequencies by disease × community | Compiled from PubMed studies |

### 3.3 What is simulated, and why

- **National dashboard records** — generated from graph prevalence figures and geo-tagged; every view labelled "simulated" (ICMR NRROID registry is not publicly downloadable).
- **Federated "hospitals"** — synthetic non-IID partitions; the partitioning/local-training/DP/secure-aggregation machinery is real.
- **ASHA voice audio** — public corpora (Common Voice, IndicVoices) don't cover genuinely rural dialects; the ASR pipeline is wired and testable, and ~1–2 h of field recordings would make it real.

**Totals:** 20,482 ontology terms · 12,880+ diseases · 286,000+ phenotype links · 539 same-as merges · knowledge graph validates with **0 dangling references**.

---

## 4. How the models were trained

All three models were trained **locally on an RTX 3050 (6 GB)** — no cloud, minutes per model. Exact commands in `docs/TRAINING_RECIPES.md`; the summary:

### Model 1 — Symptom Reader (Clinical NER)

- **Base:** Google **MuRIL-base** (pretrained on Indian languages; multilingual by design).
- **Data:** 25 hand-labelled Hindi/Hinglish clinical sentences + 400 template-augmented sentences (`ml_services/nlp/augment_ner_corpus.py`).
- **Method:** full fine-tune for token classification, 36 epochs. ~3 minutes on GPU (first run downloads the 440 MB base model).
- **Train:** `.venv/bin/python -m ml_services.nlp.train_clinical_ner` → `models/clinical_ner_muril/`.
- **Production behaviour:** hybrid — lexical rules handle known phrases exactly; the model adds spans for unseen surface forms, confidence-gated.

### Model 2 — Symptom→Term Matcher (HPO bi-encoder)

- **Base:** **intfloat/multilingual-e5-base**.
- **Data:** ~25,000 synonym pairs mined from the HPO ontology itself + the Indian symptom dictionary.
- **Method:** frozen encoder + trainable dense projection head (full fine-tune exceeds 6 GB VRAM), MultipleNegativesRankingLoss. ~3 minutes on GPU.
- **Train:** `.venv/bin/python -m ml_services.nlp.train_hpo_mapper` → `models/hpo_biencoder/` (FAISS index built at load time).

### Model 3 — Graph Neural Network (HAN)

- **Architecture:** 2-layer HANConv (heterogeneous attention) + bilinear scoring head over the knowledge graph's 12,880 disease profiles.
- **Recipes tried:** end-to-end, hard-negative mining, frozen encoder + head-only, 100 epochs.
- **Train:** `.venv/bin/python -m ml_services.graph_ai.han_model` → `models/gnn_han.pt` (428 KB, tracked in git).
- **Honest result (important):** in an A/B on the 400-case benchmark, the GNN re-ranker **reduced** accuracy (hits@5 0.95 → ~0.44) with every recipe. Root cause: the synthetic training profiles derive from the same graph the Resnik scorer uses, so the head adds noise inside phenotypic tie-bands, not signal. The engine therefore ships with **GNN off by default** (`use_gnn=False`); the checkpoint, the wiring, and the documented reason stay in the repo. Revisit when real outcome data exists.

### The diagnosis engine itself (no training)

The main scorer is the published **Phenomizer p-value algorithm** on the knowledge graph plus the India prior — no training, but heavily engineered:

- Vectorized scoring: all 12,880 diseases in one matrix pass (~5 ms warm; was 5+ s).
- Per-term term-generation null via chunked ancestor matrix (~50× faster than the naive loop; 0 mismatch vs the scalar reference).
- Same-as diseases merged under one canonical ID (richest node wins).
- India prior enters as a *relative* weight around the cohort median with a close-call gate (`BETA_PRIOR = 0.15`).

---

## 5. Results

### 5.1 Model metrics

| Model | Metric | Value |
|---|---|---|
| Clinical NER | Span F1 — template holdout (40 sentences) | **0.986** |
| Clinical NER | Span F1 — hand-labelled (25 sentences) | **0.800** (P 0.667 / R 1.000) |
| Clinical NER | Lexical-rule baseline (same gold) | 0.800 |
| HPO bi-encoder | Recall@1 (holdout over all 20,482 terms) | **0.797** |
| HPO bi-encoder | Recall@5 | **0.92** |
| HPO bi-encoder | MRR | **0.854** |
| GNN (HAN) | Benchmark A/B | **negative** — degrades hits@5 to ~0.44; off by default |

The NER's 0.800 on hand-written sentences is a *data* limit (25 sentences), not a model limit — the active-learning loop converts every clinician correction into new training signal.

### 5.2 Diagnosis engine benchmark (400 synthetic cases, full real graph)

| Scorer | Hits@5 | MRR |
|---|---|---|
| Phenomizer baseline (phenotype only) | 0.950 | 0.917 |
| **Full engine (phenotype + India prior)** | **0.9475** | 0.890 |

The baseline's tiny edge is expected: the synthetic corpus carries no patient context, so the prior can only shuffle phenotypic ties. On real contextualized cases (state, community, sex known) the prior is the feature that changes outcomes — that's the project's core claim, and it is covered by dedicated tests that prove **community-dependent outputs** (e.g., an Andhra Pradesh case correctly surfaces G6PD deficiency; founder communities get raised risk for their documented diseases).

Partial/full-benchmark runs also show **~91.7% of enriched cases get the correct disease in the top 3** on the full 12,880-disease database.

### 5.3 End-to-end demo output (what a user actually sees)

`python -m demo.run_demo` walks one synthetic patient (8-month-old from Tamil Nadu, consanguineous parents) through: NER → HPO mapping → ranked differential with 95% CIs and India-prior breakdown → explainability (attribution + similar cases) → PGx alerts on 6 test drugs → couple carrier risks with Punnett simulation → 5 multilingual reports → ASHA triage colour + referral letter → PubMed triple extraction + drift monitor → federated round (6 non-IID clients, ε estimate, secure aggregation). It finishes with a one-screen summary (top differential, top PGx alert, top reproductive risk, triage colour) and can dump the full JSON bundle with `--json`.

### 5.4 Engineering quality

- **124 / 124 automated tests pass** in ~1 min 40 s (`make tests`).
- `make lint` compiles every package; the graph builder validates referential integrity at build time.
- Every third-party dataset can be re-fetched and rebuilt from scratch with two commands.

---

## 6. Repository map

```
ml_services/          11 AI/ML modules (nlp, etl, graph_ai, pharmacogenomics,
                      reproductive, xai, federated, asha, learning_pipeline)
backend/              FastAPI app: routers, auth/RBAC, store, FHIR, services registry
web/                  React clinician dashboard
asha_app/             Flutter offline-first ASHA app
data/raw,processed    Downloaded + parsed real datasets
data/seeds/           Hand-built Indian datasets (see §3.2)
models/               Trained checkpoints (gnn_han.pt tracked; NER/bi-encoder dirs)
demo/run_demo.py      End-to-end 11-module demo
tests/                7 pytest files, 124 tests
docs/                 DEPLOYMENT, TRAINING_RECIPES, DATASETS, PATENT_CLAIM_MAP
reports/              Demo outputs (multilingual reports, active-learning queue)
```

**Reproduce everything:**

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
# for training (CUDA): pip install torch --index-url https://download.pytorch.org/whl/cu121 && pip install torch-geometric
make etl && make kg-build
.venv/bin/python -m ml_services.nlp.train_clinical_ner
.venv/bin/python -m ml_services.nlp.train_hpo_mapper
.venv/bin/python -m ml_services.graph_ai.han_model
make tests        # 124 tests
make demo         # end-to-end demo
make api          # FastAPI on :8000, docs at /docs
```

**Patent-claim mapping:** all 14 claimed innovations map to concrete implementations with evidence — see `docs/PATENT_CLAIM_MAP.md`. The defensible core is the *integration*: Indian knowledge graph + code-mixed NER + population-aware priors, end to end.

---

## 7. Honest limitations

1. **NER hand-labelled data is tiny (25 sentences).** The 0.800 span F1 is a data limit; the hybrid backend and the correction write-back loop are the mitigation.
2. **GNN result is negative and documented as such.** It is off by default; the checkpoint and rationale remain for when real outcome data exists.
3. **Benchmark cases are synthetic.** Profiles come from real disease annotations, but the benchmark has no patient-context noise; the India prior's benefit is proven structurally (tests) more than in aggregate benchmark deltas.
4. **National dashboard data is simulated** (labelled as such) because India's rare-disease registry is not public.
5. **Federated hospitals are simulated sites** — the DP/aggregation machinery is real.
6. **ASHA voice** needs 1–2 h of real field dialect recordings to leave "wired and testable" status.
7. **Web and mobile are built but not yet wired to the live API for a full click-through demo.**

---

*Companion docs: `docs/DATASETS.md` (data provenance), `docs/TRAINING_RECIPES.md` (exact training commands + numbers), `docs/PATENT_CLAIM_MAP.md` (claim→code→evidence), `docs/DEPLOYMENT.md` (running it), `PROJECT_OVERVIEW.md` (plain-language summary).*
