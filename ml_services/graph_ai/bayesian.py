"""Uncertainty quantification for diagnosis scores (Module 4 patent element).

Three layers:
  * Bootstrap/jackknife CI over phenotype subsets -> epistemic uncertainty from the input.
  * Beta posterior CI     -> sampling uncertainty for a probability estimate.
  * MC-dropout            -> used when the torch GNN backend is active.
"""
from __future__ import annotations

import math
import random
from typing import Callable, Dict, List, Optional, Sequence, Tuple


def bootstrap_ci(scores: Sequence[float], n_boot: int = 200, alpha: float = 0.05, seed: int = 13) -> Tuple[float, float]:
    """Percentile bootstrap CI for the mean of `scores`."""
    if not scores:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(scores)
    means = []
    for _ in range(n_boot):
        sample = [scores[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int((alpha / 2) * n_boot)]
    hi = means[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return (round(lo, 4), round(hi, 4))


def beta_ci(p: float, n_effective: float = 12.0, alpha: float = 0.05) -> Tuple[float, float]:
    """Credible interval for a probability under a Beta posterior (normal approx)."""
    p = min(max(p, 1e-6), 1 - 1e-6)
    a, b = p * n_effective, (1 - p) * n_effective
    mean = a / (a + b)
    sd = math.sqrt((a * b) / ((a + b) ** 2 * (a + b + 1)))
    z = 1.959963985 if abs(alpha - 0.05) < 1e-9 else 1.644853627
    return (round(max(0.0, mean - z * sd), 4), round(min(1.0, mean + z * sd), 4))


def jackknife_ci(terms: List[str], score_fn: Callable[[List[str]], float], alpha: float = 0.05) -> Tuple[float, float]:
    """Leave-one-symptom-out stability interval: how robust is the score to a missing finding?"""
    if len(terms) < 2:
        s = score_fn(terms)
        return (round(s, 4), round(s, 4))
    values = []
    full = score_fn(terms)
    for i in range(len(terms)):
        subset = terms[:i] + terms[i + 1:]
        values.append(score_fn(subset))
    values.sort()
    lo = values[int((alpha / 2) * len(values))]
    hi = values[min(len(values) - 1, int((1 - alpha / 2) * len(values)))]
    return (round(min(lo, full), 4), round(max(hi, full), 4))


def mc_dropout_predict(model, batch, n_samples: int = 20) -> Dict[str, List[float]]:
    """MC-dropout predictive distribution for a torch model (Module 4 optional path)."""
    import torch  # optional dependency

    was_training = model.training
    model.train()  # keep dropout active
    preds: List[List[float]] = []
    with torch.no_grad():
        for _ in range(n_samples):
            out = model(batch)
            logits = out[0] if isinstance(out, (tuple, list)) else out
            preds.append(torch.sigmoid(logits).detach().cpu().tolist())
    if not was_training:
        model.eval()
    if not preds:
        return {"mean": [], "std": [], "ci_low": [], "ci_high": []}
    n_out = len(preds[0])
    mean = [sum(p[i] for p in preds) / len(preds) for i in range(n_out)]
    var = [sum((p[i] - mean[i]) ** 2 for p in preds) / len(preds) for i in range(n_out)]
    sd = [math.sqrt(v) for v in var]
    return {
        "mean": mean,
        "std": sd,
        "ci_low": [max(0.0, mean[i] - 1.96 * sd[i]) for i in range(n_out)],
        "ci_high": [min(1.0, mean[i] + 1.96 * sd[i]) for i in range(n_out)],
    }


def temperature_scale(probs: Sequence[float], labels: Sequence[int], grid: Optional[Sequence[float]] = None) -> float:
    """Fit a single temperature T minimising NLL (calibration for reported probabilities)."""
    grid = grid or [x / 20 for x in range(1, 61)]
    best_t, best_nll = 1.0, float("inf")
    for t in grid:
        nll = 0.0
        for p, y in zip(probs, labels):
            p = min(max(p, 1e-9), 1 - 1e-9)
            logit = math.log(p / (1 - p)) / t
            q = 1 / (1 + math.exp(-logit))
            q = min(max(q, 1e-9), 1 - 1e-9)
            nll += -(y * math.log(q) + (1 - y) * math.log(1 - q))
        if nll < best_nll:
            best_nll, best_t = nll, t
    return round(best_t, 3)


if __name__ == "__main__":
    print("bootstrap_ci:", bootstrap_ci([0.2, 0.5, 0.7, 0.6, 0.9]))
    print("beta_ci(0.72):", beta_ci(0.72))
    print("temperature_scale:", temperature_scale([0.9, 0.8, 0.2, 0.1], [1, 0, 0, 0]))
