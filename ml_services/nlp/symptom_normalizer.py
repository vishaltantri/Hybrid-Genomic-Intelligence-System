"""Indian symptom normalizer (Module 2): colloquial/Hinglish phrase -> HPO term.

Uses the Indian synonym dictionary (patent claim #2) plus HPO names/synonyms.
Pure-Python lexical scorer; an embedding-based reranker is layered on in
hpo_mapper.HPOMapper when sentence-transformers is installed.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from ml_services.config import SEEDS_DIR
from ml_services.etl.graph_store import GraphData, load_processed
from ml_services.utils import read_csv_rows


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().strip())


def _char_ngrams(s: str, n: int = 3):
    s = _norm(s).replace(" ", "_")
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}


def _token_set(s: str):
    return set(_norm(s).split())


class SymptomNormalizer:
    """Dictionary + fuzzy normalizer over the Indian synonym layer and HPO terms."""

    def __init__(self, graph: Optional[GraphData] = None):
        self.graph = graph or load_processed()
        self.phrase_to_hpo: Dict[str, List[dict]] = {}
        self._candidates: List[dict] = []  # {hpo_id, text, source}
        self._build_index()

    def _build_index(self) -> None:
        # 1) Indian synonym dictionary (exact phrases)
        syn_path = SEEDS_DIR / "indian_synonyms.csv"
        if syn_path.exists():
            for r in read_csv_rows(syn_path):
                phrase = _norm(r.get("phrase", ""))
                hpo_id = (r.get("hpo_id") or "").strip()
                if phrase and hpo_id:
                    self.phrase_to_hpo.setdefault(phrase, []).append(
                        {"hpo_id": hpo_id, "hpo_name": r.get("hpo_name", ""), "source": "indian_synonym",
                         "language": r.get("language", "")}
                    )
                    self._candidates.append({"hpo_id": hpo_id, "text": phrase, "source": "indian_synonym"})

        # 2) HPO names + ontology synonyms from the graph
        if self.graph:
            for n in self.graph.by_type("Hpo"):
                self._candidates.append({"hpo_id": n["id"], "text": n["name"], "source": "hpo_name"})
                for syn in n.get("synonyms", []) or []:
                    self._candidates.append({"hpo_id": n["id"], "text": syn, "source": "hpo_synonym"})

        # Deduplicate candidates by (hpo_id, text)
        seen = set()
        uniq = []
        for c in self._candidates:
            k = (c["hpo_id"], _norm(c["text"]))
            if k not in seen:
                seen.add(k)
                uniq.append(c)
        self._candidates = uniq

    def exact_lookup(self, phrase: str) -> List[dict]:
        return self.phrase_to_hpo.get(_norm(phrase), [])

    def fuzzy(self, text: str, top_k: int = 5) -> List[dict]:
        """Score a free-text symptom against all candidate strings."""
        q = _norm(text)
        if not q:
            return []
        q_tokens = _token_set(text)
        q_ngrams = _char_ngrams(text)
        scored = []
        for c in self._candidates:
            t = _norm(c["text"])
            t_tokens = _token_set(c["text"])
            t_ngrams = _char_ngrams(c["text"])
            # combined lexical score
            jac = len(q_tokens & t_tokens) / len(q_tokens | t_tokens) if (q_tokens | t_tokens) else 0.0
            ng = len(q_ngrams & t_ngrams) / len(q_ngrams | t_ngrams) if (q_ngrams | t_ngrams) else 0.0
            ratio = SequenceMatcher(None, q, t).ratio()
            score = 0.45 * jac + 0.25 * ng + 0.30 * ratio
            if score > 0.05:
                scored.append({
                    "hpo_id": c["hpo_id"],
                    "matched_text": c["text"],
                    "source": c["source"],
                    "score": round(min(1.0, score), 4),
                })
        scored.sort(key=lambda d: d["score"], reverse=True)
        # keep best per HPO id
        best: Dict[str, dict] = {}
        for s in scored:
            best.setdefault(s["hpo_id"], s)
        return list(best.values())[:top_k]

    def normalize(self, phrase: str, confidence_threshold: float = 0.55) -> dict:
        """Full normalize pipeline: exact dict hit first, else fuzzy, flag low confidence."""
        exact = self.exact_lookup(phrase)
        if exact:
            hit = exact[0]
            return {"input": phrase, "hpo_id": hit["hpo_id"], "hpo_name": hit["hpo_name"],
                    "confidence": 1.0, "method": "dictionary", "needs_review": False,
                    "alternatives": exact[1:3]}
        fuzzy = self.fuzzy(phrase, top_k=3)
        if fuzzy:
            top = fuzzy[0]
            return {"input": phrase, "hpo_id": top["hpo_id"], "hpo_name": top["matched_text"],
                    "confidence": top["score"], "method": "fuzzy",
                    "needs_review": top["score"] < confidence_threshold,
                    "alternatives": fuzzy[1:3]}
        return {"input": phrase, "hpo_id": None, "hpo_name": None, "confidence": 0.0,
                "method": "none", "needs_review": True, "alternatives": []}


if __name__ == "__main__":
    sn = SymptomNormalizer()
    for p in ["piliya", "aankhon ka peela hona", "mirgi ka daura", "raat mein na dikhna",
              "yellow eyes since 2 weeks", "haath pair mein sujan"]:
        r = sn.normalize(p)
        print(f"{p!r:38s} -> {r['hpo_id']} ({r['method']}, conf={r['confidence']:.2f})")
