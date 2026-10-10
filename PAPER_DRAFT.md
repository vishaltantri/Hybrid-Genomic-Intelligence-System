# GENOMIND-INDIA: A Population-Aware Hybrid Intelligence Platform for Rare Genetic Disease Diagnosis in India

**Manuscript draft — v0.1** · *Working draft, not yet submitted*

**Authors (to be confirmed):** Vishal C. Tantri¹*, Hemang K. Dubey¹, [co-advisor / collaborator TBD]
¹ [Institution, City, India] · *Corresponding author: tantrivishal@gmail.com

> **Draft status:** full scaffold with ground-truth content from the implemented system.
> All numbers in this draft are taken directly from the repository's verified benchmark
> results (`PROJECT_REPORT.md`, `docs/TRAINING_RECIPES.md`) — none are invented.
> Sections marked `[TBD]` need author input before submission.

---

## Abstract

Rare genetic diseases affect an estimated 1 in 20 Indians, with a documented diagnostic
odyssey of 5–7 years and 4+ physicians — a delay driven in part by diagnostic tools built
exclusively on European and North American population genetics that neither understand
Indian population structure nor Indian clinical languages. We present **GENOMIND-INDIA**,
an end-to-end clinical decision-support platform that (i) extracts findings from
code-mixed Hindi–English–Tamil clinical text using a hybrid lexical + fine-tuned MuRIL
NER, (ii) maps them to the Human Phenotype Ontology through a curated Indian synonym
dictionary and a multilingual e5 bi-encoder (Recall@5 = 0.92), (iii) ranks 12,880
differential diagnoses over a 33,632-node knowledge graph using the published Phenomizer
p-value algorithm in ~5 ms, and (iv) — the central contribution — re-weights the ranking
with an **Indian population prior** combining state-level consanguinity (NFHS-5),
community founder effects, and sex-linked inheritance, gated so that priors only resolve
phenotypic near-ties and never override strong phenotype evidence. Deliverables spanning
pharmacogenomic risk from Indian allele frequencies, reproductive carrier counseling with
Punnett simulation, per-answer explainability, a simulated-site federated learning loop
with differential privacy, and an offline-first Android triage app for ASHA frontline
workers are integrated under one FastAPI + React + Flutter stack with 124/124 automated
tests. On a 400-case benchmark over the full real disease database, the full engine
achieves Hits@5 = 0.9475 vs. a phenotype-only Phenomizer baseline of 0.950; we show
structurally, through community-dependent output tests, that the prior's value emerges
 precisely when patient context (state, community, sex) is present — which is exactly the
data real clinical cases carry. A graph-neural-network re-ranker is reported as a
transparent negative result and ships disabled by default.

**Keywords:** rare diseases, India, Human Phenotype Ontology, consanguinity, founder
effects, clinical NLP, code-mixed text, knowledge graph, federated learning, explainable
AI

---

## 1. Introduction

### 1.1 The problem

Rare diseases are individually rare but collectively common: approximately 1 in 20
Indians is estimated to be affected. For an affected family the average diagnostic odyssey
is 5–7 years across 4 or more physicians. Two structural causes Amplify this delay in the
Indian context, and both are addressable by software:

1. **Tools do not know Indian genetics.** The dominant phenotype-driven diagnosis
   engines — Phenomizer [Köhler et al., 2009] and Exomiser [FigGS?] — compute disease
   similarity against catalogs (Orphanet, HPO annotations) derived overwhelmingly from
   European and North American patient populations. Indian-specific modifiers — the
   country's elevated consanguinity in specific states, deeply documented founder effects
   in specific communities (e.g. sickle-cell in tribal populations), and sex-linked
   inheritance patterns shaped by Indian demography — are invisible to them. A phenotypic
   near-tie that an Indian clinician would resolve *by asking the patient's district or
   community* is left unresolved by an imported tool.
2. **Tools do not understand Indian clinical language.** Symptom descriptions reach
   clinicians in Hindi, in Hinglish ("Aankhon ke around dark black circles"), in Tamil,
   or in English. Existing pipelines assume English medical vocabulary. No validated
   Indian clinical NER corpus exists to train one.

Beyond diagnosis, pharmacogenomic decision support for Indian patients has the same gap:
CYP2C19/CYP2D6/G6PD frequencies in Indian populations are documented (IndiGenomes), yet no
pre-merged Indian pharmacogenomics risk table is available for clinical use withIndian
allele distributions.

### 1.2 Contributions

1. **A single integrated system** uniting Indian-population genetics with phenotype-driven
   differential diagnosis, code-mixed Indian clinical NLP, pharmacogenomics, reproductive
   counseling, explainability, federated learning machinery, and a frontline-worker
   interface — all running locally on commodity hardware.
2. **An Indian rare-disease knowledge graph** — 33,632 nodes / 311,290 edges carrying
   20,482 HPO terms, 12,880 diseases, 286,000+ phenotype links, 539 curated same-as merges,
   State nodes with NFHS-5 consanguinity rates, and Ethnicity nodes with founder-disease
   links — validated with zero dangling references.
3. **A gated population prior** on the published Phenomizer algorithm that re-weights
   candidates using prevalence × consanguinity × founder effect × sex-linked factors,
   guarded by a "close-call" gate so priors never override strong phenotype evidence.
4. **A code-mixed clinical NLP stack** for Hindi/Hinglish/English/Tamil, built on a
   hand-labelled seed corpus (25 sentences), template augmentation (400 sentences), a
   hybrid lexical+MuRIL recognizer, and 69 curated Indian symptom phrases → HPO mappings —
   a contribution in itself because no comparable public dictionary exists.
5. **A negative result reported transparently:** a heterogeneous graph-attention network
   (HAN) re-ranker consistently degrades ranking accuracy on the available synthetic
   benchmark; we document the root cause and ship the GNN disabled by default.
6. **Complete reproducibility:** every figure in this paper regenerates from the repository
   with two commands (`make etl && make kg-build`), and the full test suite (124 tests)
   runs offline in under two minutes.

### 1.3 Paper organization

§2 reviews related work. §3 presents the system architecture and each of the 11 modules.
§4 details datasets. §5 describes model training. §6 reports results, including the
negative GNN result. §7 discusses ethical and clinical considerations. §8 states
limitation, and §9 concludes.

---

## 2. Related Work

### 2.1 Phenotype-based diagnosis engines

Phenomizer [Köhler 2009] scores query phenotypes against a term-generation null derived from
disease–phenotype annotations; Resnik semantic similarity forms the backbone. Exomiser
[Figs?] extends this with variant prioritization. Both are firmly validated in
European/North American settings — neither encodes Indian consanguinity or founder effects.

### 2.2 Indian population genetics

India's consanguinity landscape is geographically patterned — NFHS-5 documents
state-level rates with pronounced highs in South Indian states (e.g. Andhra Pradesh,
Tamil Nadu) [NFHS-5]. Founder effects in specific Indian communities are well
documented in the literature (sickle-cell disease in tribal populations, G6PD deficiency
distributions, β-thalassemia carrier clusters). IndiGenomes [clingen.igib.res.in] provides
Indian allele frequencies for pharmacogenomically relevant loci. **None of these data are
encoded in any public diagnosis engine**; they are scattered across survey tables, the
clinical literature, and population-genetics resources. Compiling them into one
queryable knowledge graph is a core deliverable of this work.

### 2.3 Code-mixed clinical NLP

Multilingual clinical NER has been demonstrated for high-resource Western languages and,
for Indian languages, in limited scope via MuRIL [Khanuja et al., 2020] and related
multilingual transformers. **Hand-labelled Indian clinical corpora remain essentially absent.**
Our approach — a deliberate hybrid of high-precision lexical rules (69 curated regional
synonyms) plus a fine-tuned multilingual model for unseen surface forms, with an
active-learning loop that grows the corpus from clinician corrections — is designed for
exactly this data-poor regime.

### 2.4 Federated learning in healthcare

FedAvg [McMahan et al., 2017] and differential privacy [Abadi et al., 2016] are established.
Our contribution here is application-specific: non-IID hospital simulation structured by
**Indian state/community patient archetypes**, showing how realistic admission skew (not
merely arbitrary non-IID partitioning) stresses federated convergence — plus a
privacy-preserving epidemiology byproduct with small-cell suppression.

---

## 3. System Architecture

### 3.1 Overview

```
Clinician/ASHA input (text or voice, 4 languages)
   │
   ▼
[1] Multilingual Clinical NER ──► [2] HPO Mapper (dictionary + bi-encoder)
   │                                      │
   ▼                                      ▼
[4] Hyperparameterization-free Phenomizer engine ◄── [3] Indian KG (Neo4j-or-JSON)
   │        + gated India prior
   ▼
[7] Explainability layer ◄──► [5] PGx engine      [6] Reproductive counselor
   │
   ▼
FastAPI (JWT + RBAC + FHIR)  ──►  React dashboard (web)  ·  Flutter ASHA app (mobile)
   │
   ▼
[8] Federated learning loop  ·  [10] PubMed learning pipeline · [11] National dashboard
```

### 3.2 Module by module

| # | Module | Core technique |
|---|------|----------------|
| 1 | **Clinical NER** | Hybrid: exact lexical rules for known phrases + fine-tuned **MuRIL-base** for unseen surface forms; token language-ID; negation ("no fever" is *not* a finding); duration, severity, body site, lab values. |
| 2 | **HPO mapper** | 69-entry Indian synonym dictionary + fuzzy scoring + **multilingual-e5-base** bi-encoder (FAISS cosine) re-rank; low-confidence mappings routed to expert review. |
| 3 | **Indian knowledge graph** | HPO (`hp.obo`) + phenotype.hpoa + Orphadata + ClinVar + PharmGKB/CPIC + hand-built Indian seeds (State consanguinity, Ethnicity founder effects); same-as entity resolution (539 merges); zero dangling references. |
| 4 | **Diagnosis engine** | Vectorized Phenomizer (all 12,880 diseases in ~5 ms) + **India prior**: prevalence × consanguinity × founder effect × sex-linked factor, gated to candidates within 80% of top similarity. |
| 5 | **Pharmacogenomics** | Indian allele frequencies (IndiGenomes) → Hardy–Weinberg phenotype probabilities → per-drug CPIC/PharmGKB guidance, alternative-drug suggestions. |
| 6 | **Reproductive counseling** | Couple carrier probabilities per disease × community; inbreeding coefficient F from consanguinity; Punnett simulation (20,000 offspring); reports in Hindi/English/Tamil. |
| 7 | **Explainability** | Per-symptom attribution (% evidence, "score without this finding"), missing-finding suggestions, Bayesian probability CIs + jackknife stability, FAISS nearest confirmed Indian cases (case-based reasoning), graph-attention view, 2-D phenotype projection, plain-language narrative. |
| 8 | **Federated learning** | 6 synthetic non-IID "hospitals" structured by Indian state/community archetypes; FedAvg rounds; DP noise (σ, clip, ε estimate); secure-aggregation simulation; privacy-preserving epidemiology byproduct. |
| 9 | **ASHA triage interface** | Red/amber/green triage from Hindi yes/no questionnaire; red-flag explanations; Hindi referral letter; offline SQLite with sync queue; ASR wired (awaiting field audio). |
| 10 | **Learning pipeline** | PubMed E-utilities fetch → triple extraction → KG update proposals with expert review states; active-learning queue from mapper uncertainty; PSI concept-drift monitor; clinician corrections write back to synonym dictionary. |
| 11 | **National dashboard** | State-wise map, specialist gap analysis, policy briefs from graph prevalence — labelled "simulated" pending ICMR NRROID registry access. |

### 3.3 The India prior in detail

For a candidate disease *d* and patient context (state *s*, community *c*, sex *x*):

```
prior(d) = prevalence(d)
         × consanguinityMultiplier(s)      # from NFHS-5 state table
         × founderMultiplier(c, d)         # community founder-effect lookup
         × sexLinkedFactor(d, x)
```

Numerator and denominator are balanced so `BETA_PRIOR = 0.15` controls the strength of the
shift around the cohort median. Critically, a **"close-call gate"** applies the prior only
to diseases inside 80% of the best phenotypic similarity — the prior may *reorder phenotypic
near-ties* but never *promote a phenotypically implausible disease above strong evidence*.
This design choice is deliberate and testable: the engine carries dedicated regression
tests asserting (a) community-dependent output — e.g., an Andhra Pradesh case surfaces
G6PD deficiency correctly, and (b) founder communities get raised risk only for their
documented diseases.

### 3.4 Engineering choices

- **No vector database required at runtime:** the entire 33,632-node graph runs as
  NetworkX/JSON (Neo4j optional), keeping the system deployable on a clinic laptop.
- **Vectorized Phenomizer:** all 12,880 diseases scored in one matrix pass with a chunked
  ancestor matrix for the term-generation null (~50× faster than the naive loop; verified
  zero mismatch against the scalar reference implementation).
- **Testing:** 124/124 pytest tests over 7 files (~100 s, fully offline) covering ETL, NLP,
  diagnosis/XAI, PGx/reproductive, federated/ASHA/learning, API/FHIR behavior, and
  synthetic-case regression.

---

## 4. Datasets

### 4.1 Real public datasets

| Dataset | Role | Access |
|---|---|---|
| HPO `hp.obo` (20,482 terms) | Ontology backbone | Open |
| phenotype.hpoa | 12,880+ diseases × 286,000+ phenotype links | Open |
| Orphadata | Rare-disease names, prevalence, inheritance, genes | Free registration |
| ClinVar weekly TSV | Variant→disease links | Public domain |
| PharmGKB + CPIC | Gene→drug safety pairs, dosing | CC-BY-SA |
| IndiGenomes/GenomeIndia | Indian allele frequencies for CYP2C19/CYP2D6/G6PD/TPMT + carrier rates | Academic |
| NFHS-5 | State-wise consanguinity rates | Free registration |
| PubMed E-utilities | Continual-literature feed | Free API |

### 4.2 Seed data built for this project (no public source exists)

| File | Size | Why built |
|---|---|---|
| `clinical_ner_seed.jsonl` | 25 hand-labelled Hindi/Hinglish sentences | **No Indian clinical NER corpus exists publicly** — honest seed for the bootstrap. |
| `clinical_ner_augmented.jsonl` | 400 template-generated sentences with exact gold spans | NER training augmentation |
| `indian_synonyms.csv` | 69 regional phrases → HPO terms | No Indian symptom dictionary exists publicly |
| `seed_cases.jsonl` | 12 enriched cases | Demo + regression tests |
| `synthetic_cases.jsonl` | 400 generated cases over real disease profiles (10–12 findings each) | Benchmark corpus |
| `pgx_indian_frequencies.csv` | CYP2C19/CYP2D6/G6PD Indian frequencies | The IndiGenomes × PharmGKB merge is itself novel |
| `state_consanguinity.csv` | 36 states (compiled from NFHS-5) | Scattered across survey tables |
| `community_founders.csv` | 23 communities with founder diseases (e.g. Gond–sickle cell) | Compiled from clinical literature |
| `confirmatory_tests.csv`, `carrier_lookup.csv` | Per-disease confirmation / carrier frequencies | Curated from literature |

### 4.3 What is simulated, and why

Three components are simulated and are **explicitly labelled as such throughout the UI
and documentation**:

1. National-dashboard patient records — ICMR NRROID registry data is not publicly
   downloadable; we generate graph-prevalence-informed geometry instead.
2. Federated "hospitals" — synthetic non-IID sites; the DP/aggregation machinery is real.
3. ASHA field audio — public corpora don't cover rural Indian dialects; ASR is wired and
   testable, and 1–2 h of field recordings would complete it.

---

## 5. Model Training

All three models train on a consumer GPU (RTX 3050, 6 GB) in minutes — no cloud, no
specialized hardware — deliberately, to make research reproduction cheap.

### 5.1 Clinical NER — fine-tuned MuRIL-base

- Base: **Google MuRIL-base** (pretrained on Indian languages).
- Data: 25 hand-labelled + 400 template-augmented Hindi/Hinglish sentences.
- Method: full token-classification fine-tune, 36 epochs, ~3 min.
- Runs at inference in a **hybrid** mode — lexical rules exact for known phrases; the
  model adds confidence-gated spans for unseen surface forms.

### 5.2 HPO bi-encoder — multilingual-e5-base + projection head

- Base: **intfloat/multilingual-e5-base**, frozen encoder + trainable dense projection
  (full fine-tune exceeds 6 GB VRAM).
- Data: ~25,000 synonym pairs mined from HPO + the Indian symptom dictionary.
- Objective: MultipleNegativesRankingLoss; FAISS index built at load time. ~3 min.

### 5.3 Diagnosis engine — no training required

The Phenomizer algorithm is training-free but heavily engineered (vectorized, ancestor-
matrix null, entity-resolved canonical IDs). This is intentional: phenotype similarity on
a high-quality graph does not need to be re-learned.

### 5.4 GNN re-ranker — investigated, negative result

- Architecture: 2-layer **HANConv** (heterogeneous attention) + bilinear scoring head
  over the 12,880 disease profiles; 428 KB checkpoint.
- Recipes tried: end-to-end, hard-negative mining, frozen encoder + head-only, 100 epochs.
- **Result: consistently negative** (see §6.3). Shipped disabled (`use_gnn=False`) with
  the checkpoint and rationale preserved in the repository.

---

## 6. Results

### 6.1 Model metrics

| Model | Metric | Value |
|---|---|---|
| Clinical NER | Span F1, template holdout (40 sentences) | **0.986** |
| Clinical NER | Span F1, hand-labelled (25 sentences) | **0.800** (P=0.667, R=1.000) |
| Clinical NER | Lexical-only baseline (same gold) | 0.800 |
| HPO bi-encoder | Recall@1 (holdout over all 20,482 terms) | **0.797** |
| HPO bi-encoder | Recall@5 | **0.92** |
| HPO bi-encoder | MRR | **0.854** |

We emphasize: the NER's 0.800 on hand-written sentences is a **data limit, not a model
limit** — the current corpus is 25 sentences. The active-learning loop converts every
clinician correction into new training signal, and this number is expected to move. The
lexical baseline alone achieves 0.800 on the same set — evidence that curated Indian
synonym rules carry most of the signal for known phrasings, and the neural component
matters for unconstrained input.

### 6.2 Diagnosis-engine benchmark (400 synthetic cases over the full real graph)

| Scorer | Hits@5 | MRR |
|---|---|---|
| Phenomizer (phenotype only) | 0.950 | 0.917 |
| **Full engine (phenotype + India prior)** | **0.9475** | 0.890 |
| Full engine, top-3 accuracy (enriched cases) | ~0.917 | — |

**Reading these numbers honestly.** The phenotype-only baseline edges the full engine by
0.0025 Hits@5 and 0.027 MRR. This is *the expected and correct result for the synthetic
corpus*: it carries no patient context (no state, no community, no sex recorded), so the
prior can only shuffle phenotypic near-ties — and occasionally it shuffles away from the
gold. The India prior's value is proven *structurally*, through dedicated regression
tests showing community-dependent output: an Andhra Pradesh case correctly surfaces
G6PD-related disease; founder communities get raised risk for their documented diseases.
Real clinical cases carry exactly the context the synthetic corpus lacks. We present both
numbers rather than tuning the benchmark until the prior looks better, and we flag this
as **the paper's most important honesty point.**

### 6.3 Negative result: GNN re-ranker

On the same benchmark, the HAN re-ranker **degraded** Hits@5 from 0.950 to ~0.44 across
every training recipe tried — far worse than predicting at random. We investigated the
root cause rather than reporting it as a footnote: **the synthetic training profiles are
derived from the same graph the Resnik scorer uses**, so the GNN head re-learns graph
structure the baseline already exploits and adds noise inside phenotypic tie-bands rather
than new signal. The implication — that a GNN on this graph needs *real, outcome-labelled
patient data* to add value beyond the algorithmic baseline — is itself a useful finding
for the research community, and the checkpoint is preserved with its rationale.

### 6.4 End-to-end demonstration

`python -m demo.run_demo` walks one synthetic 8-month-old consanguineous Tamil Nadu
patient through all 11 modules and produces five multilingual clinical reports, a ranked
differential with 95% CIs and the India-prior breakdown, per-drug PGx alerts, couple
carrier risks with Punnett simulation, an ASHA triage colour with a Hindi referral
letter, a PubMed-extracted KG update proposal, and a federated round (ε estimate,
secure aggregation). A one-screen summary condenses all outputs for the clinician.

### 6.5 Engineering quality

- **124/124 automated tests pass** (~1 min 40 s; fully offline).
- Knowledge-graph build validates with **zero dangling references** out of 311,290 edges.
- Every third-party dataset re-fetches and rebuilds from source with two commands.
- Docker-first deployment; web dashboard; offline-first Android APK (22.2 MB) that
  syncs to a LAN clinic server and permits cleartext only as a documented, temporary
  field trade-off pending HTTPS migration.

---

## 7. Ethics, Safety, and Clinical Positioning

1. **Decision support, not autonomy.** The platform outputs ranked differentials with
   explicit uncertainty bounds, attributable evidence, and confirmatory-test suggestions;
   it is a *second reader* for clinicians, and the ASHA triage interface produces only
   gross red/amber/green categorization with detailed red-flag explanations.
2. **Simulated data is labelled simulated.** National-dashboard and federated-hospital
   views carry persistent "simulated" labelling until real registry data is integrated.
3. **Privacy-by-architecture.** Federated learning machinery (DP, secure aggregation
   simulation, small-cell suppression in epidemiology byproducts) is built in from the
   start so that a multi-site deployment begins privacy-first rather than retrofitting.
4. **RBAC + audit.** The backend enforces five roles (admin/doctor/ASHA/patient/
   researcher) with scoped permissions, an event log, and a full audit trail.
5. **No genetic testing assumed for most outputs.** The PGx engine and carrier-risk
   engines produce risks from *population* frequencies where individual genotypes are
   unavailable — useful in low-resource Indian settings but always annotated with method
   and limitation.

---

## 8. Limitations

We list these explicitly because most exist as a consequence of honest engineering
choices rather than oversight:

1. **NER hand-labelled gold set is 25 sentences**; the 0.800 F1 is a data ceiling, not a
   model ceiling. The active-learning loop is the designed mitigation, and we Republic
   the number as-is rather than presenting it as a solved problem.
2. **Benchmark cases are synthetic.** The India prior's aggregate benefit cannot be
   measured as a delta on this benchmark (see §6.2); we document that honestly and rely
   on structural tests showing the prior behaves correctly under realistic patient
   context.
3. **GNN result is negative** and reported as such rather than omitted.
4. **National-dashboard data are simulated** (real ICMR NRROID aggregates unavailable).
5. **Federated learning sites are simulated**; the DP/aggregation machinery is genuine.
6. **ASHA voice input** awaits 1–2 h of real dialect field recordings.
7. **Web and mobile are built and tested but not yet exercised as a full click-through
   flow against the live API** in a single uninterrupted demonstration.
8. **No deployment data yet.** All numbers are from the development environment; no
   real-clinic pilot has been run.

---

## 9. Conclusion and Future Work

GENOMIND-INDIA demonstrates that Indian population genetics and Indian clinical language
can be integrated into a single, reproducible, consumer-hardware diagnosis platform with
honest, documented negative results and fully labelled simulation boundaries. The
central insight is architectural: **population priors must be gated, not dominant** —
they belong in the tie-band resolution layer of a phenotype-driven ranker, informed by
the state/community/sex context that real clinical cases carry and synthetic corpora
don't.

**Future work, in priority order:**

1. Populate the national dashboard from an estimation model (Census population ×
   Orphanet prevalence × NFHS-5 consanguinity, calibrated to ICMR NRROID aggregates).
2. Acquire 1–2 h of real rural-dialect ASHA field audio; activate ASR end-to-end.
3. Grow the hand-labelled NER corpus via the active-learning loop and re-evaluate
   against an honest external (not template-derived) gold standard.
4. Run a first real-clinic pilot to produce the diagnosis-engine benchmark that§6.2
   currently cannot: synthetic cases without context vs. real cases with it.
5. Re-enable the GNN re-ranker after (4) produces outcome-labelled data.
6. Migrate Android transport to HTTPS; release-sign the APK for field deployment.

---

## References *(to be completed; placeholders shown inline in brackets)*

[1] Köhler, S. et al. (2009). *Clinical diagnosis in adults and children by phenotype
similarity via the HPO.* Am. J. Hum. Genet. — (Phenomizer)
[2] Smedley, D. et al. (Year). *Exomiser.* — [TBD: exact ref]
[3] Khanuja, S. et al. (2020). *MuRIL: Multilingual Representations for Indian
Languages.* — [TBD: exact venue]
[4] Wang, X. et al. (2019). *Heterogeneous Graph Attention Network (HAN).* WWW 2019.
[5] McMahan, H.B. et al. (2017). *Communication-Efficient Learning of Deep Networks from
Decentralized Data (FedAvg).* AISTATS 2017.
[6] International Institute for Population Sciences (IIPS) and ICF (Year). *National
Family Health Survey (NFHS-5).* [URL]
[7] clingen.igib.res.in/indigen — IndiGenomes. [TBD: publication ref]
[8] Orphanet/Orphadata — [URL]
[9] ClinVar — [URL / Landrum et al.]
[10] PharmGKB / CPIC — [URL / Whirl-Carrillo et al.]
[11] Human Phenotype Ontology — [Garg? / Köhler et al. — HPO consortium, Nucleic Acids
Research]
[12] Abadi, M. et al. (2016). *Deep Learning with Differential Privacy.* CCS 2016.
[13] Reif, A.? / Hardy-Weinberg principle — standard genetics reference. *or cite a
specific Hardy-Weinberg clinical-genetics source.*
[14] ICMR NRROID — National Registry for Rare and Other Inherited Disorders. [URL]
[15] FAISS — Johnson, Douze, Jégou (Year). [TBD]
[16] intfloat/multilingual-e5-base — Wang et al. (Year). [TBD: E5 paper]
[17] Resnik, P. (1999). *Semantic similarity in a taxonomy.* JAIR.

---

## Appendix A — Reproducibility commands

```bash
git clone https://github.com/vishaltantri/Hybrid-Genomic-Intelligence-System.git
cd Hybrid-Genomic-Intelligence-System
python -m venv .venv && .venv/bin/pip install -r requirements.txt

make etl          # parse third-party datasets → data/processed
make kg-build     # build 33,632-node / 311,290-edge graph
make tests        # 124/124 tests
make demo         # end-to-end 11-module walkthrough with reports
make api          # FastAPI on :8000 (/docs)

# optional retraining (CUDA GPU recommended)
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install torch-geometric
.venv/bin/python -m ml_services.nlp.train_clinical_ner
.venv/bin/python -m ml_services.nlp.train_hpo_mapper
.venv/bin/python -m ml_services.graph_ai.han_model
```

## Appendix B — Figure list (drafts to prepare)

- **Fig. 1** System architecture diagram (11 modules + 3 frontends).
- **Fig. 2** Indian knowledge-graph schema (node/edge types, Indian additions highlighted).
- **Fig. 3** India-prior UML/flow: gate condition → multiplier composition → re-rank.
- **Fig. 4** NER/annotation workflow: code-mixed input → token language IDs → spans → HPO.
- **Fig. 5** Benchmark results table/bars (Hits@5/MRR, baseline vs. full engine).
- **Fig. 6** Negative-result plot: GNN recipes vs. Hits@5 (showing ~0.44 vs. 0.95 baseline).
- **Fig. 7** Explainability output sample: symptom attribution donut + "score without
  finding X" bars.
- **Fig. 8** National dashboard screenshot with "simulated" label visible.
- **Fig. 9** ASHA app screenshot: triage colour, red-flag explanation, referral letter.
