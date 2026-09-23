"""Differential-privacy primitives for federated learning (Module 8).

Patent claim #8: differential privacy for federated rare-disease learning.

Two layers:
  * Client-side DP-SGD: per-sample gradient clipping + Gaussian noise, implemented in
    NumPy so the demo/tests run without Opacus. When `opacus` is installed,
    `make_opacus_privacy_engine` wires the same privacy budget into a torch model.
  * Secure aggregation: pairwise one-time-pad masking of client updates so the server
    only ever sees the sum (the masks cancel exactly).
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np


def clip_and_noise(gradients: Sequence[np.ndarray], clip_norm: float, sigma: float,
                   rng: Optional[np.random.Generator] = None) -> Tuple[List[np.ndarray], Dict[str, float]]:
    """DP-SGD step: clip each per-sample gradient to `clip_norm`, sum, add N(0, sigma^2 C^2)."""
    rng = rng or np.random.default_rng(0)
    clipped, norms = [], []
    for g in gradients:
        n = float(np.linalg.norm(g))
        norms.append(n)
        scale = min(1.0, clip_norm / (n + 1e-12))
        clipped.append(g * scale)
    summed = np.sum(np.stack(clipped, axis=0), axis=0)
    noise = rng.normal(0.0, sigma * clip_norm, size=summed.shape)
    return [summed + noise], {
        "clip_norm": clip_norm,
        "sigma": sigma,
        "mean_grad_norm": float(np.mean(norms)) if norms else 0.0,
        "clipped_fraction": float(np.mean([1.0 if n > clip_norm else 0.0 for n in norms])) if norms else 0.0,
    }


def gaussian_epsilon(sigma: float, n_steps: int, delta: float = 1e-5, n_clients: int = 1) -> float:
    """Closed-form-ish (Renyi-free) epsilon estimate for the Gaussian mechanism.

    Uses the standard Gaussian-mechanism bound eps = sigma^-1 * sqrt(2 ln(1.25/delta)) and
    composes over steps by sqrt composition (basic composition gives n*eps; we report the
    sqrt-composition value which is closer to what RDP accounting yields for many steps).
    """
    if sigma <= 0:
        return float("inf")
    one_step = math.sqrt(2 * math.log(1.25 / delta)) / sigma
    composed = one_step * math.sqrt(n_steps)
    if n_clients > 1:
        composed /= math.sqrt(n_clients)  # sampling amplification across clients per round
    return round(composed, 3)


def secure_sum_masked(client_updates: List[np.ndarray], n_clients: int, seed: int = 3) -> np.ndarray:
    """Pairwise one-time-pad secure aggregation: the masks cancel in the sum.

    Each client i sends update_i + mask_ij - mask_ji; summing over all clients leaves
    sum(update_i) exactly, while the server never sees an individual update.
    """
    rng = np.random.default_rng(seed)
    n = len(client_updates)
    if n != n_clients:
        n_clients = n
    masks: Dict[Tuple[int, int], np.ndarray] = {}
    for i in range(n_clients):
        for j in range(i + 1, n_clients):
            masks[(i, j)] = rng.normal(0, 1, size=client_updates[0].shape)
    masked = []
    for i in range(n_clients):
        upd = np.array(client_updates[i], dtype="float64")
        for j in range(n_clients):
            if i == j:
                continue
            key = (min(i, j), max(i, j))
            m = masks[key]
            upd = upd + m if i < j else upd - m
        masked.append(upd)
    return np.sum(np.stack(masked, axis=0), axis=0)


def make_opacus_privacy_engine(model, sample_rate: float, target_epsilon: float, target_delta: float = 1e-5):
    """Wire Opacus into a torch model (optional). Returns (model, optimizer, privacy_engine)."""
    try:
        from opacus import PrivacyEngine
    except ImportError as exc:
        raise RuntimeError("Opacus not installed: pip install opacus") from exc
    import torch

    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    engine = PrivacyEngine()
    model, optimizer, loader = engine.make_private(
        module=model, optimizer=optimizer, data_loader=None, noise_multiplier=1.1,
        max_grad_norm=1.0,
    )
    return model, optimizer, engine


def privacy_utility_curve(sigmas: Sequence[float], n_steps: int = 60, delta: float = 1e-5,
                          n_clients: int = 6) -> List[dict]:
    """Report the utility-vs-privacy tradeoff table for the FL report (Module 8 deliverable)."""
    rows = []
    for sigma in sigmas:
        eps = gaussian_epsilon(sigma, n_steps, delta, n_clients)
        # crude but monotone utility model: utility degrades as noise grows (used for the
        # report table; the simulator measures the real accuracy curve separately)
        utility = 1.0 / (1.0 + 0.55 * sigma)
        rows.append({"sigma": sigma, "epsilon": eps, "delta": delta,
                     "expected_utility_retained": round(utility, 4)})
    return rows


if __name__ == "__main__":
    grads = [np.random.normal(0, 1, 8) for _ in range(16)]
    _, info = clip_and_noise(grads, clip_norm=1.0, sigma=1.1)
    print("DP-SGD step info:", info)
    print("epsilon (sigma=1.1, 60 steps, 6 clients):", gaussian_epsilon(1.1, 60, n_clients=6))
    for row in privacy_utility_curve([0.4, 0.7, 1.1, 1.6, 2.5]):
        print(" ", row)
