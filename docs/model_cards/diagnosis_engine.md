# Model card: diagnosis_engine

- Version: resnik-bayes-deterministic
- Status: active
- On by default: True
- Reproducible across two runs: True
- Intended use: decision support for clinicians; not a diagnostic device.

## Measured metrics (generated 2026-10-05T22:48:37Z)

```
{
  "synthetic_400": {
    "n_cases": 400,
    "hits@1": 0.9525,
    "hits@3": 0.995,
    "hits@5": 1.0,
    "hits@10": 1.0,
    "mrr": 0.9737
  },
  "curated_seed_12": {
    "n_cases": 12,
    "hits@1": 0.9167,
    "hits@3": 1.0,
    "hits@5": 1.0,
    "hits@10": 1.0,
    "mrr": 0.9583
  }
}
```

## Limitations

See docs/ML_BENCHMARK.md for caveats: synthetic cases are circular, no real outcome data.
