"""Phenomizer-style semantic similarity baseline (Module 4 benchmark).

Implements Resnik similarity over the HPO DAG using information content derived from
disease->phenotype annotations (phenotype.hpoa). This is the published Phenomizer
algorithm family, re-implemented so we can benchmark the GNN against it without
depending on the external Phenomizer web service.

Reference: Köhler et al. 2009 (Phenomizer); Robinson et al. 2008 (semantic similarity).
"""
from __future__ import annotations

import math
import random
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
        # Merge SAME_AS disease identities (name-matched across sources) so phenotype
        # evidence pools: hpoa annotates Wilson disease under OMIM:277900 while our
        # seed/Orphanet data uses ORPHA:915 — without pooling neither profile is complete.
        self._merge_same_as()
        self.total_diseases = max(1, len(self.disease_terms))
        # Precompute every term's ancestor closure ONCE (the real ontology has ~17k
        # terms; recomputing DFS per (patient, disease) pair made scoring ~1000x
        # slower than necessary on the full phenotype.hpoa graph).
        self._anc: Dict[str, frozenset] = {}
        for t in {t for ts in self.disease_terms.values() for t in ts} | set(self.parents):
            self._anc[t] = frozenset(self._ancestors_and_self(t))
        # propagate annotations to ancestors
        propagated: Dict[str, Set[str]] = {}
        for d, terms in self.disease_terms.items():
            with_anc = set()
            for t in terms:
                with_anc |= self._anc.get(t) or frozenset((t,))
            propagated[d] = with_anc
            for t in with_anc:
                self.term_freq[t] += 1
        self.propagated = propagated
        for t, f in self.term_freq.items():
            self.ic[t] = -math.log(f / self.total_diseases) if f > 0 else 0.0
        # pair cache for MICA across repeated diagnose/explain calls
        self._mica_cache: Dict[Tuple[str, str], Tuple[str, float]] = {}
        # term-generation null (Phenomizer): per patient term, the distribution of
        # MICA-IC against the annotation universe. A seeded sample keeps the null
        # identical for every disease while bounding the per-term construction cost
        # (the full 20k-term universe costs ~1s per new patient term).
        universe = sorted({t for ts in self.propagated.values() for t in ts})
        if len(universe) > 5000:
            rng = random.Random(1234)
            universe = sorted(rng.sample(universe, 5000))
        self._universe_terms = universe
        self._universe_n = max(1, len(self._universe_terms))
        self._null_dist: Dict[str, List[float]] = {}
        self._null_mat = None  # lazily built (row-index, ic-vector, universe-ancestor matrix)

    def _merge_same_as(self) -> None:
        """Union-find over SAME_AS edges; every member ID resolves to the pooled profile.

        `canonical_roots` (ORPHA preferred) is what ranking iterates, so a merged
        disease appears once, under its Orphanet identity.
        """
        same = [(e["src"], e["dst"]) for e in self.graph.edges if e["type"] == "SAME_AS"]
        if not same:
            self.canonical_roots = set(self.disease_terms)
            return
        parent: Dict[str, str] = {}

        def find(x: str) -> str:
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for a, b in same:
            if a in self.disease_terms and b in self.disease_terms:
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[rb] = ra
        for d in self.disease_terms:
            find(d)
        comps: Dict[str, List[str]] = {}
        for d in self.disease_terms:
            comps.setdefault(find(d), []).append(d)
        merged_terms: Dict[str, Set[str]] = {}
        roots = set()
        self._root_of = {}
        from ml_services.etl.graph_store import canonical_disease_root

        for members in comps.values():
            profile = set()
            for m in members:
                profile |= self.disease_terms[m]
            root = canonical_disease_root(members, self.graph)
            roots.add(root)
            for m in members:
                merged_terms[m] = profile
                self._root_of[m] = root
        self.disease_terms = merged_terms
        self.canonical_roots = roots

    def canonical_id(self, disease_id: str) -> str:
        """Resolve any disease ID to its merged canonical identity (case-label side)."""
        return getattr(self, "_root_of", {}).get(disease_id, disease_id)

    def canonical_diseases(self) -> List[str]:
        return sorted(getattr(self, "canonical_roots", ()) or self.disease_terms.keys())

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
        """Most informative common ancestor (cached)."""
        if t1 > t2:
            t1, t2 = t2, t1
        hit = self._mica_cache.get((t1, t2))
        if hit is not None:
            return hit
        a1 = self._anc.get(t1)
        a2 = self._anc.get(t2)
        if not a1 or not a2:
            result = ("", 0.0)
        else:
            common = a1 & a2
            result = (max(common, key=lambda t: self.ic.get(t, 0.0)) if common else "",
                      max((self.ic.get(t, 0.0) for t in common), default=0.0))
        self._mica_cache[(t1, t2)] = result
        return result

    def resnik(self, t1: str, t2: str) -> float:
        return self.mica(t1, t2)[1]

    def disease_score(self, patient_terms: List[str], disease_id: str) -> float:
        """Phenomizer p-value score (Köhler et al. 2009) with the term-generation null.

        For each patient term, p_i = P(a random disease-annotated term matches at
        least as well as the observed best match), approximated by the global IC
        distribution over all annotated terms: p_i = #{u : IC(u) >= IC(best)} / T.
        The denominator is the GLOBAL universe, never the disease's own profile
        size — so large diseases gain no floor advantage, which is what broke the
        naive within-disease formulation. Combined via the product method with
        the gamma correction: p_combined = GammaCCDF(n, -sum ln p_i).
        Returns -log10(p_combined); higher = more significant.
        """
        d_terms = self.propagated.get(disease_id)
        if not d_terms or not patient_terms:
            return 0.0
        log_sum, used = 0.0, 0
        for pt in patient_terms:
            best = max((self.resnik(pt, dt) for dt in d_terms), default=0.0)
            if best <= 0.0:
                continue  # p_i = 1: uninformative finding here
            p_i = self._p_at_least(pt, best)
            log_sum -= math.log(p_i)
            used += 1
        if used == 0:
            return 0.0
        try:
            from scipy.special import gammaincc

            p_combined = float(gammaincc(used, log_sum))
        except ImportError:
            # Wilson–Hilferty fallback for the gamma upper tail
            z = (log_sum - used) / math.sqrt(2 * used)
            p_combined = 0.5 * math.erfc(z / math.sqrt(2))
        p_combined = max(p_combined, 1e-300)
        return -math.log10(p_combined)

    def _term_index(self):
        """Shared (row-map, ic-vector) over the ontology term vocabulary."""
        if getattr(self, "_tidx", None) is None:
            import numpy as np

            terms = sorted(self.ic.keys())
            row = {t: i for i, t in enumerate(terms)}
            icv = np.zeros(len(terms), dtype=np.float64)
            for t, v in self.ic.items():
                icv[row[t]] = v
            self._tidx = (row, icv)
        return self._tidx

    def _ensure_score_matrix(self):
        """Lazy (term x disease) annotation matrix for vectorized scoring.

        Column j marks the propagated profile of disease j. Combined with a
        patient term's ancestor row-vector this yields, per disease, the best
        MICA-IC — exactly what disease_score() computes per disease in a Python
        loop (~46M pair evaluations per case at 12.9k diseases), but in one
        matrix pass (~100x faster)."""
        if getattr(self, "_score_mat", None) is not None:
            return self._score_mat
        import numpy as np
        try:
            from scipy import sparse
            use_sparse = True
        except ImportError:
            sparse, use_sparse = None, False
        row, icv = self._term_index()
        disease_ids = list(self.propagated.keys())
        rows, cols = [], []
        for j, d in enumerate(disease_ids):
            for t in self.propagated[d]:
                i = row.get(t)
                if i is not None:
                    rows.append(i)
                    cols.append(j)
        if use_sparse:
            A = sparse.csr_matrix((np.ones(len(rows)), (rows, cols)),
                                  shape=(len(icv), len(disease_ids)))
        else:
            A = np.zeros((len(icv), len(disease_ids)), dtype=bool)
            if rows:
                A[rows, cols] = True
        self._score_mat = (disease_ids, row, icv, A, use_sparse)
        return self._score_mat

    def score_all(self, patient_terms: List[str]) -> Dict[str, float]:
        """Vectorized disease_score() for every canonical disease at once.

        Same math, same p-values: per patient term the best MICA-IC per disease,
        converted to a p-value against that term's term-generation null, combined
        by the gamma product method. ~100x faster than the per-disease loop,
        which makes corpus-scale evaluation (400 cases) feasible."""
        import numpy as np
        try:
            from scipy.special import gammaincc as _gammaincc
        except ImportError:
            _gammaincc = None
        all_ids, row, icv, A, is_sparse = self._ensure_score_matrix()
        n_dis = len(all_ids)
        log_sum = np.zeros(n_dis, dtype=np.float64)
        used = np.zeros(n_dis, dtype=np.float64)
        for pt in patient_terms:
            anc = self._anc.get(pt)
            if not anc:
                continue  # unannotated finding: uninformative everywhere
            sel = [row[t] for t in anc if t in row]
            if not sel:
                continue
            sub = A[sel, :]
            sub = sub.toarray() if is_sparse else sub
            best = (icv[sel][:, None] * sub).max(axis=0)  # best MICA-IC per disease
            dist = self._null_dist.get(pt)
            if dist is None:
                dist = self._null_distribution(anc)
                self._null_dist[pt] = dist
            arr = np.asarray(dist, dtype=np.float64)
            idx = np.searchsorted(arr, best - 1e-9, side="left")
            p = (len(arr) - idx) / len(arr)
            p = np.maximum(p, 1.0 / self._universe_n)
            mask = best > 0.0  # matches disease_score's `best <= 0: continue`
            log_sum += np.where(mask, -np.log(p), 0.0)
            used += mask
        if _gammaincc is not None:
            pc = np.where(used > 0, _gammaincc(used, log_sum), 1.0)
        else:
            z = (log_sum - used) / np.sqrt(2.0 * np.maximum(used, 1.0))
            pc = np.where(used > 0,
                          0.5 * np.frompyfunc(math.erfc, 1, 1)(z / math.sqrt(2.0)).astype(float),
                          1.0)
        pc = np.maximum(pc, 1e-300)
        scores = -np.log10(pc)
        scores[used == 0] = 0.0
        return dict(zip(all_ids, scores.round(10).tolist()))

    def _p_at_least(self, patient_term: str, ic_value: float) -> float:
        """P(random annotated term u has IC(MICA(patient_term, u)) >= ic_value).

        The exact term-generation null of Köhler et al. 2009 (uniform-weight variant):
        the observed best match is compared against how well the same patient term
        would match ANY term in the annotation universe — not against the disease's
        own profile (which would favour large profiles) and not against a global IC
        histogram (which ignores that MICA-IC is capped by ancestor depth).
        """
        import bisect

        dist = self._null_dist.get(patient_term)
        if dist is None:
            anc = self._anc.get(patient_term)
            if not anc:
                self._null_dist[patient_term] = dist = [0.0]
            else:
                dist = self._null_distribution(anc)
                self._null_dist[patient_term] = dist
        idx = bisect.bisect_left(dist, ic_value - 1e-9)
        return max((len(dist) - idx) / len(dist), 1.0 / self._universe_n)

    def _null_distribution(self, anc) -> List[float]:
        """The same per-term null as the naive loop, computed via a chunked boolean
        ancestor matrix. The loop cost ~7s per *new* patient term (5,000 universe
        terms x set intersections), which made corpus-scale evaluation impossible;
        the matrix path is ~50x faster and produces the identical distribution."""
        try:
            import numpy as np
        except ImportError:
            return sorted(
                max((self.ic.get(t, 0.0) for t in anc & (self._anc.get(u) or frozenset())), default=0.0)
                for u in self._universe_terms
            )
        if getattr(self, "_null_mat", None) is None:
            terms = sorted(self.ic.keys())
            row = {t: i for i, t in enumerate(terms)}
            icv = np.zeros(len(terms), dtype=np.float64)
            for t, v in self.ic.items():
                icv[row[t]] = v
            U = np.zeros((len(self._universe_terms), len(terms)), dtype=bool)
            for i, u in enumerate(self._universe_terms):
                for t in (self._anc.get(u) or ()):  # universe term ancestors
                    j = row.get(t)
                    if j is not None:
                        U[i, j] = True
            self._null_mat = (row, icv, U)
        row, icv, U = self._null_mat
        a = np.zeros(U.shape[1], dtype=bool)
        for t in anc:
            j = row.get(t)
            if j is not None:
                a[j] = True
        vals = np.empty(U.shape[0], dtype=np.float64)
        step = 1024
        for s in range(0, U.shape[0], step):
            mask = U[s:s + step] & a
            vals[s:s + step] = (mask * icv).max(axis=1)
        return sorted(float(v) for v in vals)

    # --------------------------- diagnosis ---------------------------

    def diagnose(self, hpo_ids: List[str], top_k: int = 10) -> List[dict]:
        canon = set(self.canonical_diseases())
        scores = [(d, s) for d, s in self.score_all(hpo_ids).items() if d in canon]
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
            truth = self.canonical_id(c.get("confirmed_diagnosis", ""))
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
