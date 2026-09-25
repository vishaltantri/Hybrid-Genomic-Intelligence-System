"""Module 4: GNN-Powered Differential Diagnosis Engine.

Patent claim #5: GNN differential diagnosis using an Indian-population-weighted
heterogeneous graph. Patent claim #6 adjacent: population-aware priors.

Scoring = phenotype similarity (Resnik/Phenomizer family on the same graph the GNN
trains on) x Indian population prior:

    prior(d) = prevalence(d) x consanguinity_modifier(d, state) x founder_modifier(d, community)

The multiplicative prior is *the* India-specific contribution: two patients with the
same phenotype but different state/community get different ranked differentials.

When PyTorch Geometric is available and a trained HAN checkpoint exists
(models/gnn_han.pt), the GNN can blend its scores into the ranking as a light,
evidence-gated re-ranker (use_gnn=True). Training lives in
ml_services/graph_ai/han_model.py.

IMPORTANT (measured, not assumed): on the 400-case benchmark the GNN blend
REDUCES hits@5 from 0.95 to ~0.44 even after hard-negative retraining and
frozen-encoder retraining. The reason is structural: our synthetic training
profiles are derived from the same graph the Resnik p-value scorer uses, so
the head adds no signal beyond it — only noise inside phenotypic tie bands.
Default is therefore use_gnn=False (deterministic path); revisit once real
multi-hop evidence (patient outcomes, gene/drug response edges) exists.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

from ml_services.config import MODELS_DIR, SEEDS_DIR
from ml_services.etl.graph_store import GraphData, load_processed
from ml_services.graph_ai import bayesian
from ml_services.graph_ai.resnik import PhenomizerBaseline
from ml_services.utils import read_csv_rows, softmax

# phenotype-set noise model (Phenomizer-style): probability a finding is unrelated
NOISE = 0.05
# blend exponents: how much phenotype evidence vs population prior weighs
ALPHA_PHENO = 1.0
# GNN blend weight: final likelihood = sim^(1-w) * gnn_relative^w. The GNN captures
# multi-hop structure the pairwise Resnik score misses, but it is trained on synthetic
# pairs only — so it enters as a light re-ranker (w=0.1) that must not override strong
# phenotype + population-prior evidence. Degrades to pure Phenomizer without a checkpoint.
GNN_WEIGHT = 0.1
# The India prior enters as a *relative* weight around the cohort median, so it re-ranks
# phenotypically plausible candidates instead of overriding strong phenotype evidence.
BETA_PRIOR = 0.15


class DifferentialDiagnosisEngine:
    def __init__(self, graph: Optional[GraphData] = None, use_gnn: bool = False):
        self.graph = graph or load_processed()
        if self.graph is None:
            raise RuntimeError("Knowledge graph not built. Run: python -m ml_services.etl.kg_build")
        self.baseline = PhenomizerBaseline(self.graph)
        self.use_gnn = use_gnn
        self._gnn = None
        self.confirmatory = self._load_confirmatory_tests()
        self.state_consanguinity = {
            n["id"]: float(n.get("consanguinity_rate") or 0.0) / 100.0
            for n in self.graph.by_type("State")
        }
        self.community_index = {n["id"]: n for n in self.graph.by_type("Ethnicity")}

    # --------------------------- loading helpers ---------------------------

    def _match_state(self, state: str) -> str:
        """Tolerant state lookup: 'tamil nadu'/'Tamil nadu'/'TN-style' variants must hit
        the graph's canonical state ids, else the consanguinity prior silently zeroes."""
        raw = (state or "").strip()
        if not raw:
            return ""
        if raw in self.state_consanguinity:
            return raw
        low = raw.lower()
        for sid in self.state_consanguinity:
            if sid.lower() == low or sid.lower().replace(" ", "") == low.replace(" ", ""):
                return sid
        node = self.graph.node("State", raw) or {}
        name = (node.get("name") or "").lower()
        for sid in self.state_consanguinity:
            if sid.lower() == name:
                return sid
        return raw  # unknown state: keep as-is, prior treats it as absent

    def _load_confirmatory_tests(self) -> Dict[str, dict]:
        path = SEEDS_DIR / "confirmatory_tests.csv"
        if not path.exists():
            return {}
        return {r["disease_id"]: r for r in read_csv_rows(path)}

    def _maybe_load_gnn(self):
        if not self.use_gnn or self._gnn is not None:
            return self._gnn
        ckpt = MODELS_DIR / "gnn_han.pt"
        if not ckpt.exists():
            self._gnn = False
            return self._gnn
        try:
            from ml_services.graph_ai.han_model import load_han

            self._gnn = load_han(ckpt, self.graph)
        except Exception:
            self._gnn = False
        return self._gnn

    # --------------------------- population priors ---------------------------

    def population_prior(self, disease_id: str, state: str = "", community: str = "", sex: str = "") -> dict:
        node = self.graph.node("Disease", disease_id) or {}
        prevalence = float(node.get("prevalence_per_100k") or 0.1)
        prior = prevalence / 100_000.0

        # consanguinity modifier: recessive diseases are amplified in high-consanguinity states
        cons_rate = self.state_consanguinity.get(state, 0.0)
        inheritance = (node.get("inheritance") or "").lower()
        is_recessive = "recessive" in inheritance
        cons_mult = 1.0 + (2.0 * cons_rate if is_recessive else 0.25 * cons_rate)

        # founder/community modifier
        found_mult = 1.0
        community_notes = []
        for cname, cnode in self.community_index.items():
            if community and cname.lower() != community.lower():
                continue
            if cnode.get("founder_disease_id") == disease_id:
                found_mult = float(cnode.get("carrier_multiplier") or 1.0)
                community_notes.append(cnode.get("founder_note") or f"Founder risk documented in {cname}")
            if not community and disease_id in (cnode.get("founder_note") or "") and cnode.get("founder_disease_id") == disease_id:
                community_notes.append(cnode.get("founder_note") or "")

        # X-linked and sex
        sex_mult = 1.0
        if "x-linked" in inheritance:
            if "m" in (sex or "").lower():
                sex_mult = 3.0
            elif "f" in (sex or "").lower():
                sex_mult = 0.3

        total = prior * cons_mult * found_mult * sex_mult
        return {
            "prevalence_per_100k": prevalence,
            "consanguinity_rate": cons_rate,
            "consanguinity_multiplier": round(cons_mult, 3),
            "founder_multiplier": round(found_mult, 3),
            "sex_multiplier": sex_mult,
            "prior": total,
            "inheritance": node.get("inheritance", ""),
            "notes": [n for n in community_notes if n],
        }

    # --------------------------- attribution ---------------------------

    def attribute_symptoms(self, hpo_ids: List[str], disease_id: str, top_n: int = 5) -> List[dict]:
        """Which of the patient's findings drove this diagnosis, and by how much."""
        d_terms = self.baseline.propagated.get(disease_id, set())
        if not d_terms:
            return []
        contributions = []
        for pt in hpo_ids:
            best_t, best_ic = "", 0.0
            for dt in d_terms:
                _, ic = self.baseline.mica(pt, dt)
                if ic > best_ic:
                    best_t, best_ic = dt, ic
            # specificity weight: rare terms (high IC) matter more, matching the patent claim
            specificity = self.baseline.ic.get(pt, 0.5)
            contributions.append({
                "patient_term": pt,
                "matched_disease_term": best_t,
                "similarity": round(best_ic, 4),
                "specificity": round(specificity, 4),
                "contribution": round(best_ic * max(specificity, 0.1), 4),
            })
        total = sum(c["contribution"] for c in contributions) or 1.0
        for c in contributions:
            c["weight_pct"] = round(100.0 * c["contribution"] / total, 1)
        contributions.sort(key=lambda c: c["contribution"], reverse=True)
        return contributions[:top_n]

    def missing_terms(self, hpo_ids: List[str], disease_id: str, top_n: int = 3) -> List[dict]:
        """Findings expected in this disease that the patient does NOT have (higher certainty if present)."""
        d_terms = self.baseline.propagated.get(disease_id, set())
        patient = set(hpo_ids)
        missing = [t for t in d_terms if t not in patient and self.baseline.ic.get(t, 0) > 0]
        missing.sort(key=lambda t: self.baseline.ic.get(t, 0), reverse=True)
        out = []
        for t in missing[:top_n]:
            node = self.graph.node("Hpo", t) or {}
            out.append({"hpo_id": t, "hpo_name": node.get("name", t),
                        "would_increase": "certainty" if self.baseline.ic.get(t, 0) > 1.0 else "slightly"})
        return out

    # --------------------------- referral helpers ---------------------------

    def nearest_services(self, disease_id: str, state: str = "", city: str = "", limit: int = 3) -> dict:
        labs = [n for n in self.graph.by_type("Lab") if n.get("nabl_accredited")]
        specialists = self.graph.by_type("Doctor")
        if state:
            labs = sorted(labs, key=lambda l: 0 if l.get("state") == state else 1)
            specialists = sorted(specialists, key=lambda s: 0 if s.get("state") == state else 1)
        return {
            "labs": [
                {"name": l["name"], "city": l.get("city", ""), "state": l.get("state", ""), "nabl": True}
                for l in labs[:limit]
            ],
            "specialists": [
                {"name": s["name"], "specialty": s.get("specialty", ""), "city": s.get("city", ""),
                 "state": s.get("state", ""), "institution": s.get("institution", "")}
                for s in specialists[:limit]
            ],
        }

    # --------------------------- main entrypoint ---------------------------

    def diagnose(
        self,
        hpo_ids: List[str],
        patient_context: Optional[dict] = None,
        top_k: int = 10,
        explain: bool = False,
        uncertainty: bool = True,
    ) -> dict:
        patient_context = patient_context or {}
        state = self._match_state(patient_context.get("state", ""))
        community = patient_context.get("community", "")
        sex = patient_context.get("sex", "")

        candidates: List[dict] = []
        canon = set(self.baseline.canonical_diseases())
        all_scores = self.baseline.score_all(hpo_ids)
        for disease_id, sim in all_scores.items():
            if sim <= 0 or disease_id not in canon:
                continue
            prior = self.population_prior(disease_id, state, community, sex)
            candidates.append({
                "disease_id": disease_id,
                "similarity": sim,
                "prior": prior,
            })

        if not candidates:
            return {
                "hpo_ids": list(hpo_ids),
                "patient_context": patient_context,
                "results": [],
                "engine": "gnn_han" if self._maybe_load_gnn() else "graph_similarity+india_prior",
                "note": ("No phenotype matched any disease in the knowledge graph. "
                         "Add HPO terms or extend the graph."),
            }

        # GNN blend: one batched pass over all candidates; their sigmoid scores are
        # normalised against the best candidate so only *relative* GNN evidence re-ranks.
        gnn = self._maybe_load_gnn()
        gnn_scores = gnn.score(hpo_ids, [c["disease_id"] for c in candidates]) if gnn else {}
        max_gnn = max(gnn_scores.values(), default=0.0)

        # Relative Indian prior: normalise across the candidate set so prevalence scale
        # cancels out and only India-specific *differences* (consanguinity, founder,
        # sex, relative prevalence) re-rank the differential.
        priors = sorted(c["prior"]["prior"] for c in candidates)
        median_prior = priors[len(priors) // 2] if priors else 1.0
        max_sim = max(c["similarity"] for c in candidates)
        for c in candidates:
            likelihood = max(c["similarity"] - NOISE, 1e-6)
            rel = (c["prior"]["prior"] / median_prior) if median_prior > 0 else 1.0
            rel = max(rel, 1e-3)
            c["prior_relative"] = round(rel, 4)
            # Gate: the India prior re-ranks only phenotypically plausible candidates
            # (within 80% of the best similarity). Strong phenotype evidence wins outright;
            # borderline profiles are exactly where consanguinity/founder knowledge helps.
            close_call = c["similarity"] >= 0.80 * max_sim
            exposure = BETA_PRIOR if close_call else 0.02
            c["prior_applied"] = close_call
            if gnn_scores:
                c["gnn_score"] = round(gnn_scores.get(c["disease_id"], 0.0), 4)
                # logits at temperature T=0.25: the raw sigmoid compresses differences
                # (two decimals of p = 10x odds), so identical-ish outputs would drown
                # the phenotype signal. Temperature restores usable separations.
                T = 0.25
                logit = math.log(max(c["gnn_score"], 1e-6) / (1.0 - max(c["gnn_score"], 1e-6) if c["gnn_score"] < 1.0 else 1.0 - 1e-6))
                c["gnn_relative"] = max(math.exp(T * logit), 1e-3)
                # Evidence-gated: the GNN re-ranks only inside phenotypic near-ties
                # (same gate as the India prior), never overriding strong evidence.
                gnn_exposure = GNN_WEIGHT if close_call else 0.0
                c["gnn_applied"] = gnn_exposure > 0
                likelihood = (likelihood ** (1.0 - gnn_exposure)) * (c["gnn_relative"] ** gnn_exposure)
            c["weighted_score"] = (likelihood ** ALPHA_PHENO) * (rel ** exposure)

        probs = softmax([math.log(c["weighted_score"]) if c["weighted_score"] > 0 else -50.0 for c in candidates])
        for c, p in zip(candidates, probs):
            c["probability"] = p
        candidates.sort(key=lambda c: c["probability"], reverse=True)
        top = candidates[:top_k]

        results = []
        for c in top:
            disease_id = c["disease_id"]
            node = self.graph.node("Disease", disease_id) or {}
            entry = {
                "disease_id": disease_id,
                "disease_name": node.get("name", disease_id),
                "probability": round(c["probability"], 4),
                "phenotype_similarity": round(c["similarity"], 4),
                "gnn_score": c.get("gnn_score"),
                "inheritance": node.get("inheritance", ""),
                "population_prior": {
                    "prevalence_per_100k": c["prior"]["prevalence_per_100k"],
                    "consanguinity_multiplier": c["prior"]["consanguinity_multiplier"],
                    "founder_multiplier": c["prior"]["founder_multiplier"],
                    "sex_multiplier": c["prior"]["sex_multiplier"],
                    "relative_weight": c.get("prior_relative", 1.0),
                    "prior_applied_to_ranking": c.get("prior_applied", False),
                    "india_notes": c["prior"]["notes"],
                },
            }
            if uncertainty:
                lo, hi = bayesian.beta_ci(entry["probability"], n_effective=10 + 4 * len(hpo_ids))
                entry["probability_ci"] = [lo, hi]
                # input-robustness: how stable is this rank if one finding were wrong?
                def score_fn(subset, _d=disease_id):
                    return self.baseline.disease_score(subset, _d)
                jl, jh = bayesian.jackknife_ci(hpo_ids, score_fn)
                entry["similarity_jackknife"] = [jl, jh]
            if explain:
                entry["driving_symptoms"] = self.attribute_symptoms(hpo_ids, disease_id)
                entry["missing_findings"] = self.missing_terms(hpo_ids, disease_id)
            tests = self.confirmatory.get(disease_id)
            if tests:
                entry["confirmatory_tests"] = {
                    "first_line": [t.strip() for t in (tests.get("first_line_tests") or "").split(";") if t.strip()],
                    "genetic": [t.strip() for t in (tests.get("genetic_confirmation") or "").split(";") if t.strip()],
                    "india_note": tests.get("india_note", ""),
                }
            entry["genes"] = [g["id"] for g in self.graph.neighbors(disease_id, "ASSOCIATED_WITH")]
            results.append(entry)

        out = {
            "hpo_ids": hpo_ids,
            "patient_context": patient_context,
            "results": results,
            "engine": "gnn_han" if self._maybe_load_gnn() else "graph_similarity+india_prior",
            "ranking_note": (
                "Ranking blends phenotype similarity with Indian population priors "
                "(prevalence, state consanguinity, community founder risk)."
            ),
        }
        if results:
            out["referral"] = self.nearest_services(results[0]["disease_id"], state,
                                                    patient_context.get("city", ""))
        return out

    # --------------------------- evaluation ---------------------------

    def evaluate(self, cases: List[dict], k: int = 5) -> dict:
        hits, rr, improved = 0, 0.0, 0
        for c in cases:
            ranked = self.diagnose(c.get("hpo", []), patient_context=c, top_k=10)["results"]
            ids = [r["disease_id"] for r in ranked]
            truth = self.baseline.canonical_id(c.get("confirmed_diagnosis", ""))
            if truth in ids[:k]:
                hits += 1
            if truth in ids:
                rr += 1.0 / (ids.index(truth) + 1)
            eng_rank = ids.index(truth) if truth in ids else None
            base_ids = [r["disease_id"] for r in self.baseline.diagnose(c.get("hpo", []), top_k=len(ids) or 10)]
            base_rank = base_ids.index(truth) if truth in base_ids else None
            if eng_rank is not None and (base_rank is None or eng_rank < base_rank):
                improved += 1
        n = max(1, len(cases))
        return {
            "n_cases": len(cases),
            f"hits@{k}": round(hits / n, 4),
            "mrr": round(rr / n, 4),
            "cases_improved_vs_phenomizer_baseline": improved,
        }


if __name__ == "__main__":
    from ml_services.config import SEEDS_DIR as SD
    from ml_services.utils import read_jsonl

    engine = DifferentialDiagnosisEngine()
    demo = ["HP:0000616", "HP:0001337", "HP:0001394"]
    res = engine.diagnose(demo, {"state": "Andhra Pradesh", "community": "Reddy", "sex": "M"}, top_k=5, explain=True)
    print(f"Engine: {res['engine']}")
    for r in res["results"]:
        print(f"  {r['probability']*100:5.1f}%  {r['disease_name']}  (sim={r['phenotype_similarity']:.3f}, "
              f"cons={r['population_prior']['consanguinity_multiplier']})")
    top = res["results"][0] if res["results"] else None
    if top:
        print("  drivers:", [(d["patient_term"], d["weight_pct"]) for d in top.get("driving_symptoms", [])])
        print("  tests:", (top.get("confirmatory_tests") or {}).get("first_line"))
    cases = read_jsonl(SD / "seed_cases.jsonl")
    print("eval:", engine.evaluate(cases, k=3))
    print("baseline eval:", PhenomizerBaseline().evaluate(cases, k=3))
