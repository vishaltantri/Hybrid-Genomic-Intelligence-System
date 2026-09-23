"""Non-IID partitioning of training data across simulated Indian hospitals (Module 8).

Patent claim #8: federated rare-disease learning with non-IID Indian hospital population
handling. A metro tertiary centre and a tribal district hospital have utterly different
case mixes; the simulator models that explicitly with three partition strategies:

  * "language"  — clients differ by the mix of Hindi/Hinglish/English notes
  * "disease"   — clients differ by disease prevalence (Dirichlet over labels)
  * "hospital_archetype" — realistic archetypes: metro_tertiary, district, tribal, phc
"""
from __future__ import annotations

import random
from typing import Dict, List

import numpy as np

ARCHETYPES = {
    "metro_tertiary": {
        "note": "AIIMS/PGIMER-like: wide case mix, English-heavy notes, rare diseases seen",
        "disease_alpha": 3.0,
        "language_mix": {"EN": 0.6, "HI-EN": 0.3, "HI": 0.1},
    },
    "district": {
        "note": "District hospital: commoner conditions, Hindi/Hinglish notes",
        "disease_alpha": 1.0,
        "language_mix": {"EN": 0.25, "HI-EN": 0.45, "HI": 0.3},
    },
    "tribal": {
        "note": "Tribal belt hospital: sickle cell / G6PD heavy, regional language notes",
        "disease_alpha": 0.4,
        "language_mix": {"EN": 0.1, "HI-EN": 0.3, "HI": 0.6},
    },
    "phc": {
        "note": "Primary health centre: ASHA-referred, low lab availability",
        "disease_alpha": 0.5,
        "language_mix": {"EN": 0.05, "HI-EN": 0.25, "HI": 0.7},
    },
}


def partition_by_disease(cases: List[dict], n_clients: int = 6, alpha: float = 1.0, seed: int = 11) -> List[List[dict]]:
    """Dirichlet label-skew partition; low alpha = more non-IID (realistic for rare disease)."""
    rng = np.random.default_rng(seed)
    by_label: Dict[str, List[dict]] = {}
    for c in cases:
        by_label.setdefault(c.get("confirmed_diagnosis") or c.get("label") or "unknown", []).append(c)
    client_buckets: List[List[dict]] = [[] for _ in range(n_clients)]
    for label, items in by_label.items():
        props = rng.dirichlet([alpha] * n_clients)
        counts = (props * len(items)).astype(int)
        while counts.sum() < len(items):
            counts[rng.integers(0, n_clients)] += 1
        rng.shuffle(items)
        start = 0
        for i, cnt in enumerate(counts):
            client_buckets[i].extend(items[start:start + cnt])
            start += cnt
    return client_buckets


def partition_by_archetype(cases: List[dict], n_clients: int = 6, seed: int = 11) -> List[dict]:
    """Assign each case to a hospital archetype, then group. Returns rich client metadata."""
    rng = random.Random(seed)
    names = list(ARCHETYPES)
    clients = []
    for i in range(n_clients):
        archetype = names[i % len(names)]
        spec = ARCHETYPES[archetype]
        clients.append({
            "client_id": f"hospital_{i+1:02d}",
            "archetype": archetype,
            "note": spec["note"],
            "language_mix": spec["language_mix"],
            "data": [],
            "name": f"{archetype.replace('_', ' ').title()} Hospital {i+1}",
        })
    for c in cases:
        # weight archetype choice by the case's language and disease to mimic referral patterns
        lang = c.get("note_lang", "EN")
        weights = []
        for cl in clients:
            w = cl["language_mix"].get(lang, 0.05)
            if cl["archetype"] == "tribal" and c.get("disease_id") in ("ORPHA:232", "ORPHA:355"):
                w *= 3.0
            if cl["archetype"] == "metro_tertiary" and c.get("disease_id") in ("ORPHA:915", "ORPHA:98863"):
                w *= 2.0
            weights.append(max(w, 1e-6))
        total = sum(weights)
        pick = rng.random() * total
        acc = 0.0
        chosen = clients[-1]
        for cl, w in zip(clients, weights):
            acc += w
            if pick <= acc:
                chosen = cl
                break
        chosen["data"].append(c)
    return clients


def dirichlet_label_matrix(client_buckets: List[List[dict]]) -> Dict[str, object]:
    """Label distribution matrix + a non-IID-ness score (1 - mean normalised entropy)."""
    labels = sorted({(c.get("confirmed_diagnosis") or c.get("label") or "unknown")
                     for bucket in client_buckets for c in bucket})
    mat = np.zeros((len(client_buckets), len(labels)))
    for i, bucket in enumerate(client_buckets):
        for c in bucket:
            lab = c.get("confirmed_diagnosis") or c.get("label") or "unknown"
            mat[i, labels.index(lab)] += 1
    row_sums = mat.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1
    probs = mat / row_sums
    entropies = []
    for row in probs:
        p = row[row > 0]
        entropies.append(float(-(p * np.log2(p)).sum()) if len(p) else 0.0)
    max_entropy = np.log2(len(labels)) if len(labels) > 1 else 1.0
    mean_norm_entropy = float(np.mean(entropies) / max_entropy) if max_entropy else 0.0
    return {
        "labels": labels,
        "counts": mat.astype(int).tolist(),
        "mean_normalised_entropy": round(mean_norm_entropy, 4),
        "non_iid_score": round(1.0 - mean_norm_entropy, 4),
        "interpretation": ("Higher non_iid_score = clients' case mixes are more skewed "
                           "(harder federated setting, closer to real Indian hospitals)."),
    }


if __name__ == "__main__":
    from ml_services.config import SEEDS_DIR
    from ml_services.utils import read_jsonl

    cases = read_jsonl(SEEDS_DIR / "seed_cases.jsonl")
    meta = [dict(c) for c in cases]
    by_disease = partition_by_disease(meta, n_clients=6, alpha=0.5)
    print("Dirichlet (alpha=0.5) partition sizes:", [len(b) for b in by_disease])
    info = dirichlet_label_matrix(by_disease)
    print("labels:", info["labels"])
    print("non_iid_score:", info["non_iid_score"])
    clients = partition_by_archetype(meta, n_clients=6)
    for c in clients:
        print(f"  {c['client_id']} {c['archetype']:14s} cases={len(c['data'])}")
