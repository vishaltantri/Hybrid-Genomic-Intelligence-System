# Patent Claim → Implementation Map

*Where each claimed idea actually lives in the code, with the evidence for it.*

| # | Claim (in plain words) | Implementation | Evidence |
|---|---|---|---|
| 1 | India-specific rare disease **knowledge graph** (multilingual, multi-source) | `ml_services/etl/` (parsers, `kg_build.py`), `ml_services/etl/graph_store.py` | Real HPO 20,482 terms + Orphanet + ClinVar + PharmGKB + Indian allele-frequency and consanguinity seeds; 0 dangling refs; `SAME_AS` entity resolution |
| 2 | Code-mixed **clinical NER** for Indian languages with negation/duration handling | `ml_services/nlp/clinical_ner.py`, `train_clinical_ner.py`, `augment_ner_corpus.py` | Trained MuRIL (F1 0.986 holdout), hybrid lexical+model backend, Hinglish seed corpus built from scratch |
| 3 | Multilingual **HPO mapper** with Indian symptom dictionary | `ml_services/nlp/hpo_mapper.py`, `train_hpo_mapper.py` | Bi-encoder over all 20,482 terms — R@1 0.797 / R@5 0.92 / MRR 0.854; FAISS similarity |
| 4 | Published **p-value phenotype ranking** (Phenomizer-family) adapted to the India graph | `ml_services/graph_ai/resnik.py` | Köhler 2009 term-generation null implemented + vectorized (5 ms / 12.9k diseases, 0 mismatch vs scalar) |
| 5 | **Population-aware priors** in differential diagnosis (the core India novelty) | `ml_services/graph_ai/gnn_diagnosis.py::population_prior` | Consanguinity × founder × sex × prevalence multipliers, gated re-ranking; dedicated tests prove community-dependent outputs |
| 6 | **GNN differential diagnosis** over the heterogeneous graph | `ml_services/graph_ai/han_model.py` | Trained HAN checkpoint shipped; honest negative A/B result documented in-module (default off — see TRAINING_RECIPES) |
| 7 | **Bayesian uncertainty** on every diagnosis | `ml_services/graph_ai/bayesian.py` | Beta CIs + jackknife stability per result entry |
| 8 | **Explainability layer** (which finding drove what, what's missing) | `ml_services/xai/`, engine `attribute_symptoms` / `missing_terms` | Per-candidate contribution weights (%), specificity scores, FAISS nearest-case lookup |
| 9 | **Pharmacogenomics engine** with Indian allele frequencies | `ml_services/pharmacogenomics/`, seed `pgx_indian_frequencies.csv` | PharmGKB/CPIC pairs × IndiGenomes frequencies (novel merge); G6PD/CYP2C19 alerts in demo |
| 10 | **Reproductive risk counselor** with community carrier rates | `ml_services/reproductive/` | Punnett-style couple simulator, carrier lookup by community, reports in Hindi/English/Tamil |
| 11 | **Federated learning** across hospitals without data sharing | `ml_services/federated/` | Non-IID partitioning, local training rounds, differential-privacy noise, secure-aggregation simulation |
| 12 | **Continuous learning** from new literature | `ml_services/learning_pipeline/` | PubMed E-utilities fetch → extraction → KG update proposals with review state (`kg_updates.jsonl`, `clinician_feedback.json`) |
| 13 | **ASHA triage + voice interface** for rural use | `ml_services/asha/`, `backend/app/routers/triage.py` | Red/amber/green triage, ASR wiring, offline-tolerant design |
| 14 | **FHIR/EMR integration** | `backend/app/routers/emr.py`, `fhir.py` | FHIR bundle parsing into engine inputs; JWT + role-based access |

**Positioning summary (one line each):**
- vs **Phenomizer/Exomiser**: they rank by phenotype only; this engine adds Indian population context, native-language input, counseling, PGx, and referral — end to end.
- vs **general medical LLMs**: this is verifiable (ontology-grounded, p-values, uncertainty) and explainable, not generative guesswork.
- The **defensible core** is claims 1+2+5 together: an Indian KG + code-mixed NER + population priors. Each alone is improvable; the integrated system on Indian data is the moat.
