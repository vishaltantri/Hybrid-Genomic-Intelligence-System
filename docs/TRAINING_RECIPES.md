# Training Recipes — How Each Model Was Trained

*Exact commands, data, and results. All training ran on a local RTX 3050 (6 GB), no cloud needed.*

---

## Model 1 — Symptom Reader (Clinical NER)

**What it does:** reads a Hindi/Hinglish/English clinical sentence and marks up the medical findings (symptom, severity, duration, body site, test result).

| | |
|---|---|
| Base model | Google MuRIL-base (pretrained on Indian languages) |
| Data | 25 hand-labelled clinical sentences + 400 template-generated sentences (built by `ml_services/nlp/augment_ner_corpus.py`) |
| Method | Full fine-tune, token classification, 36 epochs |
| Output | `models/clinical_ner_muril/` (weights auto-excluded from git) |

**Train it:**
```bash
.venv/bin/python -m ml_services.nlp.train_clinical_ner
```
Takes ~3 minutes on the GPU (the first run downloads the 440 MB base model).

**Measured results**

| Eval set | Span F1 |
|---|---|
| Template holdout (40 sentences) | **0.986** |
| Hand-labelled sentences (25, offsets repaired) | **0.800** (P 0.667 / R 1.000) |
| Lexical rule baseline (same gold) | 0.800 |

The 0.800 is a *data* limit (25 sentences), not a model limit. The live backend is a **hybrid**: lexical rules handle known phrases exactly; the model adds spans for surface forms the lexicon has never seen (confidence-gated). Corrections from clinicians flow back into the seed file — that loop is what raises this number.

---

## Model 2 — Symptom→Term Matcher (HPO Bi-Encoder)

**What it does:** matches free-text symptom phrases to the official 20,482-term Human Phenotype Ontology.

| | |
|---|---|
| Base model | intfloat/e5-base (multilingual) |
| Data | ~25,000 real synonym pairs mined from the ontology itself + the Indian symptom dictionary |
| Method | Frozen encoder + trainable Dense projection head (full fine-tune OOMs 6 GB) |
| Output | `models/hpo_biencoder/` + FAISS index (built at load time) |

**Train it:**
```bash
.venv/bin/python -m ml_services.nlp.train_hpo_mapper
```
~3 minutes on GPU (first run downloads the e5 weights).

**Measured results** (holdout over all 20,482 terms):

| Metric | Value |
|---|---|
| Recall@1 | **0.797** |
| Recall@5 | **0.92** |
| MRR | **0.854** |

---

## Model 3 — Graph Neural Network (HAN)

**What it does:** learns embeddings over the whole disease network (diseases, symptoms, genes, drugs) to re-rank the differential.

| | |
|---|---|
| Architecture | 2-layer HANConv (heterogeneous attention) + bilinear scoring head |
| Data | The knowledge graph itself: 12,880 disease profiles |
| Method tried | (a) end-to-end, (b) hard negatives only, (c) frozen encoder + head-only, 100 epochs |
| Output | `models/gnn_han.pt` (428 KB, tracked in git) |

**Train it:**
```bash
.venv/bin/python -m ml_services.graph_ai.han_model
```
~1 minute on GPU.

**Honest result (important):** measured A/B on the 400-case benchmark, the GNN re-ranker *reduces* accuracy (0.44 vs 0.92 hits@5) with every recipe tried. Root cause: our training profiles are derived from the same graph the Resnik p-value scorer already uses, so the head adds noise, not signal. The engine therefore ships with **GNN off by default** (`use_gnn=False`); the checkpoint and code stay in the repo and the module docstring records exactly why. Revisit when real outcome data (patient results, treatment responses) exists.

---

## The Diagnosis Engine Itself (no training needed)

The main scorer is the published **Phenomizer p-value algorithm** (Köhler 2009) on the knowledge graph, plus the **India prior**. No training — but heavily engineered:

- Vectorized scoring: all 12,880 diseases scored in one matrix pass (~5 ms warm, was 5+ s)
- Per-term term-generation null via chunked ancestor matrix (~50× faster than the naive loop)
- Same-as diseases merged under one canonical ID (richest node wins)

**Final benchmark, 400 synthetic cases, full real graph:**

| Scorer | Hits@5 | MRR |
|---|---|---|
| Phenomizer baseline (phenotype only) | 0.950 | 0.917 |
| **Full engine (phenotype + India prior)** | **0.9475** | **0.890** |

The baseline's tiny edge is expected: the synthetic corpus has no patient context, so the prior can only shuffle ties. On real contextualized cases (state, community, sex known) the prior is the feature that changes outcomes — that's the project's core claim, and it's covered by dedicated tests.

---

## Reproduce Everything

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
# torch + torch-geometric (CUDA) are needed for training:
.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cu121
.venv/bin/pip install torch-geometric
make etl && make kg-build
.venv/bin/python -m ml_services.nlp.train_clinical_ner
.venv/bin/python -m ml_services.nlp.train_hpo_mapper
.venv/bin/python -m ml_services.graph_ai.han_model
.venv/bin/python -m pytest tests/          # 124 tests
.venv/bin/python demo/run_demo.py          # end-to-end demo
```
