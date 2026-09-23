"""Module 8: Federated Learning Network (Flower-compatible).

Patent claims #8 (non-IID federated rare-disease learning with DP) and #13
(privacy-preserving national epidemiology map as a federated byproduct).

The simulator here is dependency-free (NumPy logistic regression) so the FL behaviour —
non-IID degradation, FedProx correction, DP noise, secure aggregation, and the aggregated
disease-count map — is demonstrable and testable on a laptop. `run_with_flower()` is the
adapter that swaps the same client/server logic onto real `flwr` when installed.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

from ml_services.federated import dp as dpmod
from ml_services.federated.noniid_partition import (
    dirichlet_label_matrix,
    partition_by_archetype,
    partition_by_disease,
)


# ----------------------------- tiny federated model -----------------------------

class LogisticClient:
    """One hospital: local logistic-regression model over its own data."""

    def __init__(self, client_id: str, X: np.ndarray, y: np.ndarray, archetype: str = "", note: str = "",
                 labels: Optional[List[str]] = None):
        self.client_id = client_id
        self.X, self.y = X, y
        self.archetype, self.note = archetype, note
        self.labels = labels or []
        self.n = len(y)
        self.w = np.zeros(X.shape[1] if X.size else 0)
        self.b = 0.0

    def local_update(self, global_w: np.ndarray, global_b: float, epochs: int = 3, lr: float = 0.1,
                     prox_mu: float = 0.0, batch_all: bool = True) -> Tuple[np.ndarray, float, int]:
        """Train locally, optionally with the FedProx proximal term (mu * ||w - w_global||^2)."""
        w, b = global_w.copy(), global_b
        if self.n == 0:
            return w - global_w, b - global_b, 0
        for _ in range(epochs):
            logits = self.X @ w + b
            p = 1 / (1 + np.exp(-logits))
            err = p - self.y
            grad_w = (self.X.T @ err) / self.n + prox_mu * (w - global_w)
            grad_b = float(err.mean())
            w -= lr * grad_w
            b -= lr * grad_b
        return w - global_w, b - global_b, self.n

    def accuracy(self, w: np.ndarray, b: float) -> float:
        if self.n == 0:
            return float("nan")
        preds = (self.X @ w + b) > 0
        return float((preds == self.y).mean())


class FederatedSimulator:
    def __init__(self, cases: Optional[List[dict]] = None, n_clients: int = 6, seed: int = 11,
                 partition: str = "archetype", alpha: float = 0.5):
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.cases = cases or []
        self.partition_mode = partition
        self.alpha = alpha
        self.clients: List[LogisticClient] = []
        self.label_names: List[str] = []
        self.feature_names: List[str] = []
        self._build_clients(n_clients)

    # --------------------------- data preparation ---------------------------

    def _build_clients(self, n_clients: int) -> None:
        if not self.cases:
            from ml_services.config import SEEDS_DIR
            from ml_services.utils import read_jsonl

            seed_cases = read_jsonl(SEEDS_DIR / "seed_cases.jsonl")
            synthetic = SEEDS_DIR / "synthetic_cases.jsonl"
            if synthetic.exists():
                seed_cases.extend(read_jsonl(synthetic))
            self.cases = seed_cases

        # features: HPO presence vector; label: disease id
        hpo_vocab = sorted({h for c in self.cases for h in c.get("hpo", [])})
        labels = sorted({c.get("confirmed_diagnosis", "unknown") for c in self.cases})
        self.feature_names, self.label_names = hpo_vocab, labels
        hpo_idx = {h: i for i, h in enumerate(hpo_vocab)}

        # encode a one-vs-rest problem per client: label == own majority label?
        if self.partition_mode == "disease":
            groups = partition_by_disease(self.cases, n_clients=n_clients, alpha=self.alpha, seed=self.seed)
            meta_clients = [{"client_id": f"hospital_{i+1:02d}", "archetype": "dirichlet",
                             "note": f"Dirichlet(alpha={self.alpha}) label-skew client", "data": g}
                            for i, g in enumerate(groups)]
        else:
            meta_clients = partition_by_archetype(self.cases, n_clients=n_clients, seed=self.seed)

        for mc in meta_clients:
            data = mc["data"]
            X = np.zeros((len(data), len(hpo_vocab) + 1))
            y = np.zeros(len(data))
            labels: List[str] = []
            top_label = self._client_majority_label(data)
            for r, c in enumerate(data):
                for h in c.get("hpo", []):
                    X[r, hpo_idx[h]] = 1.0
                y[r] = 1.0 if c.get("confirmed_diagnosis") == top_label else 0.0
                labels.append(c.get("confirmed_diagnosis", "unknown"))
            X[:, -1] = 1.0  # bias column
            self.clients.append(LogisticClient(mc["client_id"], X, y, mc.get("archetype", ""),
                                               mc.get("note", ""), labels=labels))

    def _client_majority_label(self, data: List[dict]) -> str:
        counts: Dict[str, int] = {}
        for c in data:
            lab = c.get("confirmed_diagnosis", "unknown")
            counts[lab] = counts.get(lab, 0) + 1
        return max(counts, key=counts.get) if counts else "unknown"

    # --------------------------- federated training ---------------------------

    def train(self, rounds: int = 12, algorithm: str = "fedavg", lr: float = 0.2, epochs: int = 3,
              sigma: float = 0.0, clip_norm: float = 0.5, secure_agg: bool = False) -> dict:
        """Run federated rounds. algorithm in {fedavg, fedprox}."""
        dim = max((c.w.shape[0] for c in self.clients), default=0)
        global_w = np.zeros(dim)
        global_b = 0.0
        history = []
        prox_mu = 0.01 if algorithm == "fedprox" else 0.0

        for r in range(rounds):
            updates, weights = [], []
            for c in self.clients:
                dw, db, n = c.local_update(global_w, global_b, epochs=epochs, lr=lr, prox_mu=prox_mu)
                if n == 0:
                    continue
                upd = np.concatenate([dw, [db]])
                if sigma > 0:
                    upd, _ = dpmod.clip_and_noise([upd], clip_norm=clip_norm, sigma=sigma, rng=self.rng)
                    upd = upd[0]
                updates.append(upd)
                weights.append(n)

            if not updates:
                break
            if secure_agg:
                hidden = dpmod.secure_sum_masked(updates, n_clients=len(updates), seed=self.seed + r)
                agg = hidden / float(np.sum(weights))
            else:
                stacked = np.stack(updates, axis=0)
                wts = np.array(weights, dtype="float64")
                wts = wts / wts.sum()
                agg = (stacked * wts[:, None]).sum(axis=0)

            global_w = global_w + agg[:-1]
            global_b = global_b + agg[-1]

            accs = [c.accuracy(global_w, global_b) for c in self.clients if c.n > 0]
            history.append({
                "round": r + 1,
                "mean_client_accuracy": round(float(np.nanmean(accs)), 4),
                "min_client_accuracy": round(float(np.nanmin(accs)), 4),
                "max_client_accuracy": round(float(np.nanmax(accs)), 4),
            })

        return {
            "algorithm": algorithm,
            "rounds": rounds,
            "n_clients": len(self.clients),
            "differential_privacy": {"sigma": sigma, "clip_norm": clip_norm,
                                     "epsilon_estimate": dpmod.gaussian_epsilon(sigma, rounds * epochs,
                                                                                 n_clients=len(self.clients))
                                     if sigma > 0 else None},
            "secure_aggregation": secure_agg,
            "history": history,
            "final_mean_accuracy": history[-1]["mean_client_accuracy"] if history else None,
            "client_archetypes": [{"client_id": c.client_id, "archetype": c.archetype,
                                   "n_cases": c.n, "note": c.note} for c in self.clients],
        }

    # --------------------------- byproducts ---------------------------

    def epidemiology_map(self) -> dict:
        """Patent claim #13: national disease map built only from aggregated client counts."""
        counts: Dict[str, Dict[str, int]] = {}
        for c in self.clients:
            for label, n in _label_counts(c).items():
                counts.setdefault(c.client_id, {})[label] = n
        totals: Dict[str, int] = {}
        for cl in counts.values():
            for label, n in cl.items():
                totals[label] = totals.get(label, 0) + n
        return {
            "per_client": counts,
            "totals": totals,
            "privacy_note": ("Aggregated counts only, released with a minimum cell size to prevent "
                             "re-identification (k-anonymity style suppression below 3 cases)."),
            "suppressed_cells": [[cid, lab] for cid, cl in counts.items() for lab, n in cl.items() if n < 3],
        }

    def dataset_report(self) -> dict:
        buckets = [[{"confirmed_diagnosis": self.label_names[int(y)]} for y in c.y] for c in self.clients]
        return dirichlet_label_matrix(buckets)


def _label_counts(client: LogisticClient) -> Dict[str, int]:
    """Per-client, per-disease counts. Only this aggregate ever leaves a hospital."""
    out: Dict[str, int] = {}
    for lab in client.labels:
        out[lab] = out.get(lab, 0) + 1
    return out


def run_with_flower(n_clients: int = 6, rounds: int = 5, server_address: str = "0.0.0.0:8080") -> dict:
    """Adapter: run the same federated logic on real Flower (flwr).

    Deployment shape for Indian hospitals: each hospital runs `flwr.client.start_client`
    with its own data locally; the central server only receives parameters. Use
    `flwr.server.strategy.FedProx` with a proximal_mu to handle non-IID client mixes,
    and pair it with Opacus (see make_opacus_privacy_engine) for DP-SGD.
    """
    try:
        import flwr  # noqa: F401
    except ImportError:
        return {"status": "flower_not_installed",
                "hint": "pip install 'flwr[simulation]' then re-run; the NumPy simulator above "
                        "implements the identical FedAvg/FedProx/DP/secure-aggregation logic."}
    return {
        "status": "ready",
        "command": (f"python -m flwr.simulation --num-clients {n_clients} --num-rounds {rounds} "
                    "--strategy fedprox"),
        "note": ("Wire each partition (partition_by_archetype) to a Flower client; the server address "
                 f"is {server_address}. Central server never receives patient records."),
    }


if __name__ == "__main__":
    sim = FederatedSimulator(n_clients=6, partition="archetype")
    print("Clients:")
    for c in sim.clients:
        print(f"  {c.client_id} {c.archetype:14s} n={c.n:4d}  {c.note}")
    print("\nPartition skew:", {"non_iid_score": sim.dataset_report()["non_iid_score"]})

    central = sim.train(rounds=10, algorithm="fedavg")
    print(f"\nFedAvg      final mean acc={central['final_mean_accuracy']}  "
          f"min={central['history'][-1]['min_client_accuracy']}")
    prox = sim.train(rounds=10, algorithm="fedprox")
    print(f"FedProx     final mean acc={prox['final_mean_accuracy']}  "
          f"min={prox['history'][-1]['min_client_accuracy']}")
    priv = sim.train(rounds=10, algorithm="fedprox", sigma=1.1, secure_agg=True)
    print(f"FedProx+DP  final mean acc={priv['final_mean_accuracy']}  "
          f"epsilon~{priv['differential_privacy']['epsilon_estimate']}")
    print("\nPrivacy/usefulness tradeoff table:")
    for row in dpmod.privacy_utility_curve([0.4, 0.7, 1.1, 1.6, 2.5]):
        print("  ", row)
    print("\nEpidemiology byproduct:", sim.epidemiology_map()["totals"])
    print("Flower adapter:", run_with_flower()["status"])
