# ML benchmark (generated 2026-10-05T22:48:37Z)

Produced by `python -m scripts.ml_benchmark`. All numbers measured on repo data. Caveats matter more than the numbers.

## Differential diagnosis (default: GNN off)

| Set | n | hits@1 | hits@3 | hits@5 | hits@10 | MRR |
|---|---|---|---|---|---|---|
| synthetic regenerated from current graph (circular) | 400 | 0.9525 | 0.995 | 1.0 | 1.0 | 0.9737 |
| curated seed | 12 | 0.9167 | 1.0 | 1.0 | 1.0 | 0.9583 |
| synthetic, GNN enabled | - | Not evaluated - the GNN could not be loaded in this environment (checkpoint present but load_han failed, e.g. torch_geometric not installed); enabling it falls back to the deterministic path, so no GNN-specific number exists. |

Shipped `synthetic_cases.jsonl`: 6 of 400 cases have their gold disease in the current graph (graph: 362 nodes). data/seeds/synthetic_cases.jsonl was generated against a larger graph; most of its diseases and phenotypes do not exist in the current graph, so it cannot be used to score it.

Reproducible across two runs: **True**.

- synthetic_400 is regenerated from the current graph (seed 42) using the same disease annotations the scorer uses: circular, an upper bound, not clinical accuracy.
- The documented 'hits@5 0.92 on 400 cases' (docs/TRAINING_RECIPES.md) was measured on a larger graph and cannot be reproduced on this checkout's graph (see shipped_synthetic_file).
- curated_seed_12 has 12 cases: far too few for confidence intervals; indicative only.
- No real patient outcome data exists: real-world accuracy is NOT evaluated.

## HPO mapper
top-1 0.386, top-5 0.386 on 57 canonical labels. Phrases are exact HPO labels from the seed cases: this measures lookup of canonical names, not free-text or Hinglish robustness.

## Clinical NER (SYMPTOM spans)
backend LexicalRuleNER: precision 0.8462, recall 0.9167, F1 0.88 on 25 sentences. The seed set is also the lexicon/training source: this is NOT a held-out evaluation and overstates generalisation.

## Variant prioritisation
One verified trio (n=1): a smoke test and determinism check, NOT an accuracy estimate. Sensitivity/specificity: not evaluated - no labelled variant benchmark. Top-5 genes: BRCA1, VHL, PAH, ATP7B, HBB; deterministic: True.

## Not evaluated (no ground truth)
- **digital_twin**: Rule/derivation based; scenario outputs are recomputations of the diagnosis and variant engines. No outcome ground truth: not evaluated.
- **reproductive_risk**: Deterministic Mendelian/Bayesian arithmetic validated by unit tests against known ratios; no outcome data: not evaluated.
- **pharmacogenomics**: CPIC rule lookup (deterministic); concordance with a lab gold standard unavailable: not evaluated.
- **hpo_embeddings**: Optional sentence embedding re-ranker; disabled in this run (GENOMIND_EMBED_MODEL=none), so not evaluated.
- **kg_models**: Knowledge-graph build is ETL, not a trained model; graph size reported by /platform/status.
