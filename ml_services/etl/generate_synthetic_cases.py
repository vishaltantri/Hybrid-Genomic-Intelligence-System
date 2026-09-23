"""Generate a synthetic Indian rare-disease case corpus from the knowledge graph.

Why this exists
---------------
No public Indian rare-disease case corpus can be redistributed (ICMR NRROID is
request-only, AIIMS case reports are not licensed for reuse). So, exactly as the
project plan states, national-scale case data is *simulated* from the knowledge
graph's own disease/phenotype/prevalence structure and clearly labelled
``synthetic: true``. Every generated case is derived from real HPO disease
annotations; only the patient is fictional.

Used by:
  * Module 4 - differential-diagnosis evaluation (top-k / MRR)
  * Module 7 - case-based reasoning index (FAISS)
  * Module 8 - federated learning across simulated hospitals
  * Module 11 - national dashboard aggregation

Usage:
    python -m ml_services.etl.generate_synthetic_cases --n 300
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List

from ml_services.config import SEEDS_DIR
from ml_services.etl.graph_store import load_processed
from ml_services.utils import read_csv_rows, write_jsonl

# How often each noise mechanism fires. Real clinicians under-report and over-report,
# so the generator reproduces both: dropped cardinal findings and phenocopies.
DROP_PROB = 0.28          # a true finding is not reported
NOISE_PROB = 0.20         # an unrelated finding is reported
PHENOCOPY_PROB = 0.10     # the case actually has a disease that mimics the target

AGE_BY_ONSET = {
    "childhood": (0, 12),
    "congenital": (0, 2),
    "infancy": (0, 3),
    "adult": (18, 55),
}
DEFAULT_AGE = (2, 30)


def _disease_profiles(graph) -> List[dict]:
    """Disease -> {phenotypes, prevalence, founder communities, inheritance, gene}."""
    profiles: List[dict] = []
    for disease in graph.by_type("Disease"):
        did = disease["id"]
        phenos = [n["id"] for n in graph.neighbors(did, "HAS_PHENOTYPE")]
        if len(phenos) < 2:
            continue
        founders: List[str] = []
        states: List[str] = []
        for e in graph.edges_to(did, "FOUNDER_RISK"):
            founders.append(e["src"])
        for e in graph.edges_to(did, "PREVALENT_IN"):
            states.append(e["src"])
        profiles.append({
            "disease_id": did,
            "name": disease.get("name", did),
            "phenotypes": phenos,
            "prevalence": float(disease.get("prevalence_per_100k") or 1.0),
            "inheritance": disease.get("inheritance", ""),
            "genes": [g["id"] for g in graph.neighbors(did, "ASSOCIATED_WITH")],
            "founders": founders,
            "states": states,
        })
    return profiles


def _community_states(graph) -> Dict[str, List[str]]:
    """community -> states it is concentrated in (for realistic geo assignment)."""
    out: Dict[str, List[str]] = defaultdict(list)
    for node in graph.by_type("Ethnicity"):
        cid = node["id"]
        for e in graph.edges_to(cid, "LOCATED_IN"):
            out[cid].append(e["src"])
    return out


def _pick_age(inheritance: str, rng: random.Random) -> dict:
    key = ""
    low = inheritance.lower()
    for k in AGE_BY_ONSET:
        if k in low:
            key = k
            break
    if not key:
        key = "childhood" if "recessive" in low else "adult"
    lo, hi = AGE_BY_ONSET.get(key, DEFAULT_AGE)
    years = rng.randint(lo, hi)
    return {"age_years": years, "age_months": years * 12 + rng.randint(0, 11) if years < 2 else years * 12}


def generate(n: int = 300, seed: int = 42, out_path: Path | None = None) -> dict:
    graph = load_processed()
    if graph is None:
        raise SystemExit("Build the knowledge graph first: python -m ml_services.etl.kg_build")

    rng = random.Random(seed)
    profiles = _disease_profiles(graph)
    if not profiles:
        raise SystemExit("No diseases with >=2 phenotype annotations in the graph.")

    community_states = _community_states(graph)
    all_hpo = [n["id"] for n in graph.by_type("Hpo")]
    states = [n["id"] for n in graph.by_type("State")]

    # Sample diseases in proportion to Indian prevalence, so the corpus looks like a
    # district hospital's case mix rather than a uniform disease catalogue. Prevalence is
    # compressed (sqrt, capped at 80/100k) because a country-scale G6PD rate of 4% would
    # otherwise swamp the corpus and make the diagnosis benchmark trivially unbalanced.
    weights = [min(max(p["prevalence"], 0.05), 80.0) ** 0.5 for p in profiles]
    mimic_pool = {p["disease_id"]: [q["disease_id"] for q in profiles
                                    if q["disease_id"] != p["disease_id"]
                                    and set(q["phenotypes"]) & set(p["phenotypes"])]
                  for p in profiles}

    cases: List[dict] = []
    for i in range(n):
        # phenocopy: report a mimicking disease instead of the sampled one
        target = rng.choices(profiles, weights=weights, k=1)[0]
        if rng.random() < PHENOCOPY_PROB and mimic_pool.get(target["disease_id"]):
            mid = rng.choice(mimic_pool[target["disease_id"]])
            actual = next(p for p in profiles if p["disease_id"] == mid)
        else:
            actual = target

        observed = [h for h in actual["phenotypes"] if rng.random() > DROP_PROB]
        if not observed:
            observed = [rng.choice(actual["phenotypes"])]
        observed = list(dict.fromkeys(observed))
        own = set(actual["phenotypes"])
        if rng.random() < NOISE_PROB:
            distractors = [h for h in rng.sample(all_hpo, min(6, len(all_hpo))) if h not in own]
            observed += distractors[:rng.randint(1, 2)]

        # geography: founder community if the disease has one, else a state it is
        # prevalent in, else a random state
        community = ""
        state = ""
        if actual["founders"] and rng.random() < 0.6:
            community = rng.choice(actual["founders"])
            cand = community_states.get(community) or actual["states"]
            state = rng.choice(cand) if cand else rng.choice(states)
        elif actual["states"] and rng.random() < 0.7:
            state = rng.choice(actual["states"])
        else:
            state = rng.choice(states)

        consanguineous = rng.random() < (0.30 if state in {"Tamil Nadu", "Karnataka", "Andhra Pradesh",
                                                           "Telangana", "Kerala"} else 0.10)
        sex = "M"
        if "x-linked" in actual["inheritance"].lower():
            sex = rng.choice(["M", "M", "F"])   # X-linked phenotypes present more in boys

        age = _pick_age(actual["inheritance"], rng)
        cases.append({
            "case_id": f"SYN{i + 1:04d}",
            "synthetic": True,
            "confirmed_diagnosis": actual["disease_id"],
            "confirmed_diagnosis_name": actual["name"],
            "hpo": sorted(set(observed)),
            "n_observed": len(set(observed)),
            "n_true_phenotypes": len(own),
            "state": state,
            "community": community,
            "sex": sex,
            "consanguineous_parents": consanguineous,
            "gene": (actual["genes"] or [""])[0],
            "inheritance": actual["inheritance"],
            "generation_note": ("Simulated patient drawn from real HPO disease annotations; "
                                "not a real person. Findings dropped/noised to mimic clinical "
                                "under- and over-reporting."),
            **age,
        })

    out_path = out_path or (SEEDS_DIR / "synthetic_cases.jsonl")
    write_jsonl(out_path, cases)

    mix = Counter(c["confirmed_diagnosis"] for c in cases)
    stats = {
        "n_cases": len(cases),
        "n_diseases": len(mix),
        "mean_observed": round(sum(c["n_observed"] for c in cases) / len(cases), 2),
        "mean_true": round(sum(c["n_true_phenotypes"] for c in cases) / len(cases), 2),
        "consanguineous_fraction": round(sum(c["consanguineous_parents"] for c in cases) / len(cases), 3),
        "top_diseases": mix.most_common(5),
        "path": str(out_path),
    }
    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="")
    ap.add_argument("--preview", action="store_true", help="print the disease mix without writing")
    args = ap.parse_args()
    stats = generate(args.n, args.seed, Path(args.out) if args.out else None)
    print(json.dumps(stats, indent=2, default=str))


if __name__ == "__main__":
    main()
