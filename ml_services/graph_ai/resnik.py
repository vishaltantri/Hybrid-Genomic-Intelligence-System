"""Phenomizer-style semantic similarity baseline (Module 4 benchmark).

Implements Resnik similarity over the HPO DAG using information content derived from
disease->phenotype annotations (phenotype.hpoa). This is the published Phenomizer
algorithm family, re-implemented so we can benchmark the GNN against it without
depending on the external Phenomizer web service.

Reference: Köhler et al. 2009 (Phenomizer); Robinson et al. 2008 (semantic similarity).
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from ml_services.etl.graph_store import GraphData, load_processed


class PhenomizerBaseline:
    def __init__(self, graph: Optional[GraphData] = None):
        self.graph = graph or load_processed()
        if self.graph is None:
            raise RuntimeError("Knowledge graph not built. Run: python -m ml_services.etl.kg_build")
        self.parents: Dict[str, Set[str]] = defaultdict(set)
        self.disease_terms: Dict[str, Set[str]] = defaultdict(set)
        self.term_freq: Dict[str, int] = defaultdict(int)
        self.total_diseases: int = 0
        self.ic: Dict[str, float] = {}
        self._build()

    # ------------------------------ build ------------------------------

    def _build(self) -> None:
        for e in self.graph.edges:
            if e["type"] == "IS_A":
                self.parents[e["src"]].add(e["dst"])
        for e in self.graph.edges:
            if e["type"] == "HAS_PHENOTYPE":
                self.disease_terms[e["src"]].add(e["dst"])
        self.total_diseases = max(1, len(self.disease_terms))
        # propagate annotations to ancestors
        propagated: Dict[str, Set[str]] = {}
        for d, terms in self.disease_terms.items():
            with_anc = set()
            for t in terms:
                with_anc |= self._ancestors_and_self(t)
            propagated[d] = with_anc
            for t in with_anc:
                self.term_freq[t] += 1
        self.propagated = propagated
        for t, f in self.term_freq.items():
            self.ic[t] = -math.log(f / self.total_diseases) if f > 0 else 0.0

    def _ancestors_and_self(self, term: str) -> Set[str]:
        out = {term}
        stack = [term]
        while stack:
            cur = stack.pop()
            for p in self.parents.get(cur, ()):
                if p not in out:
                    out.add(p)
                    stack.append(p)
        return out

    # --------------------------- similarity ---------------------------

    def mica(self, t1: str, t2: str) -> Tuple[str, float]:
        """Most informative common ancestor."""
        a1 = self._ancestors_and_self(t1)
        a2 = self._ancestors_and_self(t2)
        common = a1 & a2
        if not common:
            return "", 0.0
        best = max(common, key=lambda t: self.ic.get(t, 0.0))
        return best, self.ic.get(best, 0.0)

    def resnik(self, t1: str, t2: str) -> float:
        return self.mica(t1, t2)[1]

    def disease_score(self, patient_terms: List[str], disease_id: str) -> float:
        """Phenomizer-style score: mean best-match similarity of patient terms to disease terms."""
        d_terms = self.propagated.get(disease_id)
        if not d_terms or not patient_terms:
            return 0.0
        best_sum = 0.0
        for pt in patient_terms:
            best = max((self.resnik(pt, dt) for dt in d_terms), default=0.0)
            best_sum += best
        return best_sum / len(patient_terms)

    # --------------------------- diagnosis ---------------------------

    def diagnose(self, hpo_ids: List[str], top_k: int = 10) -> List[dict]:
        scores = []
        for disease_id in self.disease_terms:
            s = self.disease_score(hpo_ids, disease_id)
            scores.append((disease_id, s))
        scores.sort(key=lambda x: x[1], reverse=True)
        out = []
        for disease_id, s in scores[:top_k]:
            node = self.graph.node("Disease", disease_id) or {}
            out.append({
                "disease_id": disease_id,
                "disease_name": node.get("name", disease_id),
                "score": round(s, 4),
                "inheritance": node.get("inheritance", ""),
            })
        return out

    def evaluate(self, cases: List[dict], k: int = 5) -> dict:
        """Hits@k / MRR for cases with true disease labels."""
        hits, rr = 0, 0.0
        for c in cases:
            ranked = self.diagnose(c.get("hpo", []), top_k=max(k, 10))
            ids = [r["disease_id"] for r in ranked]
            truth = c.get("confirmed_diagnosis")
            if truth in ids[:k]:
                hits += 1
            if truth in ids:
                rr += 1.0 / (ids.index(truth) + 1)
        n = max(1, len(cases))
        return {"n_cases": len(cases), f"hits@{k}": round(hits / n, 4), "mrr": round(rr / n, 4)}


if __name__ == "__main__":
    from ml_services.utils import read_jsonl
    from ml_services.config import SEEDS_DIR

    baseline = PhenomizerBaseline()
    cases = read_jsonl(SEEDS_DIR / "seed_cases.jsonl")
    print(baseline.evaluate(cases, k=5))
    demo = ["HP:0000616", "HP:0001337", "HP:0001394"]
    print("Demo case HPO:", demo)
    for r in baseline.diagnose(demo, top_k=5):
        print(f"  {r['score']:.3f}  {r['disease_name']}")
