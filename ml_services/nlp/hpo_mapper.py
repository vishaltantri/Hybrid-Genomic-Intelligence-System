"""Module 2: HPO Phenotype Mapper with Indian Synonym Engine.

Pipeline: clinical entities (Module 1) -> HPO terms.

Design:
  * Lexical stage (always available): SymptomNormalizer dictionary + fuzzy scoring.
  * Rerank stage (optional): sentence-transformers embeddings, used when
    `GENOMIND_EMBED_MODEL` is installed/cached, to reorder the lexical top-k.
  * Every mapping carries a confidence; low-confidence mappings are queued for
    clinician review (active learning loop, Module 10).

Training the reranker is done by ml_services/nlp/train_hpo_mapper.py using
(Muril/e5) bi-encoders with MultipleNegativesRankingLoss on HPO term text pairs.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

from ml_services.config import REPORTS_DIR
from ml_services.etl.graph_store import load_processed
from ml_services.nlp.clinical_ner import LexicalRuleNER, get_ner
from ml_services.nlp.symptom_normalizer import SymptomNormalizer
from ml_services.utils import cosine, write_jsonl

SYMPTOM_LABELS = {"SYMPTOM", "BODY_PART"}
EMBED_MODEL = os.environ.get("GENOMIND_EMBED_MODEL", "intfloat/multilingual-e5-base")


class HPOMapper:
    def __init__(self, graph=None, normalizer: Optional[SymptomNormalizer] = None, use_embeddings: bool = True):
        self.graph = graph or load_processed()
        self.normalizer = normalizer or SymptomNormalizer(self.graph)
        self._embedder = None
        self._hpo_matrix = None
        self._hpo_ids: List[str] = []
        self.use_embeddings = use_embeddings
        self._review_queue: List[dict] = []

    # ------------------------- embeddings (optional) -------------------------

    def _load_embedder(self):
        if self._embedder is not None or not self.use_embeddings:
            return self._embedder
        try:
            from sentence_transformers import SentenceTransformer

            self._embedder = SentenceTransformer(EMBED_MODEL)
        except Exception:
            self._embedder = False  # sentinel: unavailable
        return self._embedder

    def _ensure_hpo_matrix(self):
        if self._hpo_matrix is not None:
            return self._hpo_matrix
        embedder = self._load_embedder()
        if not embedder or not self.graph:
            self._hpo_matrix = []
            return self._hpo_matrix
        ids, texts = [], []
        for n in self.graph.by_type("Hpo"):
            ids.append(n["id"])
            syn = "; ".join((n.get("synonyms") or [])[:3])
            texts.append(f"{n['name']}. {n.get('definition', '')} {syn}".strip())
        self._hpo_ids = ids
        self._hpo_matrix = embedder.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return self._hpo_matrix

    def _embed_score(self, text: str, candidates: List[str]) -> Dict[str, float]:
        embedder = self._load_embedder()
        matrix = self._ensure_hpo_matrix()
        if not embedder or len(matrix) == 0:
            return {}
        try:
            vec = embedder.encode([text], normalize_embeddings=True, show_progress_bar=False)[0]
        except Exception:
            return {}
        out: Dict[str, float] = {}
        for cid in candidates:
            if cid in self._hpo_ids:
                idx = self._hpo_ids.index(cid)
                out[cid] = float((matrix[idx] @ vec).item())
        return out

    # ------------------------------ mapping ------------------------------

    def map_phrase(self, phrase: str, top_k: int = 5, threshold: float = 0.55) -> List[dict]:
        """Map one free-text symptom phrase to ranked HPO terms."""
        base = self.normalizer.fuzzy(phrase, top_k=top_k)
        if not base:
            r = self.normalizer.normalize(phrase, confidence_threshold=threshold)
            return [r] if r["hpo_id"] else []
        embed_scores = self._embed_score(phrase, [b["hpo_id"] for b in base])
        for b in base:
            if b["hpo_id"] in embed_scores:
                b["score"] = round(0.5 * b["score"] + 0.5 * max(0.0, embed_scores[b["hpo_id"]]), 4)
        base.sort(key=lambda d: d["score"], reverse=True)
        return base

    def map_text(self, text: str, classify_missing: bool = True) -> dict:
        """Full text -> HPO profile, using the NER backend to find symptom spans."""
        ner = get_ner()
        return self.map_ner_result(ner.extract(text), classify_missing=classify_missing)

    def map_ner_result(self, ner_result: dict, classify_missing: bool = True) -> dict:
        profile: Dict[str, dict] = {}
        unmapped: List[str] = []

        for ent in ner_result.get("entities", []):
            if ent["label"] not in SYMPTOM_LABELS:
                continue
            # 1) direct lexicon hit from NER
            if ent.get("hpo_id"):
                self._add(profile, ent["hpo_id"], ent.get("hpo_name") or ent["text"], 0.95, ent["text"], "ner_lexicon")
                continue
            # 2) mapper
            ranked = self.map_phrase(ent["text"])
            if ranked and ranked[0]["score"] >= 0.35:
                top = ranked[0]
                self._add(profile, top["hpo_id"], top.get("matched_text", ent["text"]), top["score"], ent["text"], top.get("source", "fuzzy"))
            else:
                unmapped.append(ent["text"])

        items = sorted(profile.values(), key=lambda d: d["confidence"], reverse=True)
        low_confidence = [i for i in items if i["confidence"] < 0.55]
        if low_confidence:
            for i in low_confidence:
                self._review_queue.append(i)
            write_jsonl(REPORTS_DIR / "active_learning_queue.jsonl", self._review_queue[-200:])

        return {
            "text": ner_result.get("text", ""),
            "hpo_profile": items,
            "hpo_ids": [i["hpo_id"] for i in items],
            "unmapped_symptoms": unmapped,
            "low_confidence_count": len(low_confidence),
            "is_code_mixed": ner_result.get("is_code_mixed", False),
            "lid_counts": ner_result.get("lid_counts", {}),
        }

    @staticmethod
    def _add(profile: Dict[str, dict], hpo_id: str, hpo_name: str, confidence: float, evidence: str, method: str) -> None:
        cur = profile.get(hpo_id)
        if cur is None or confidence > cur["confidence"]:
            profile[hpo_id] = {
                "hpo_id": hpo_id,
                "hpo_name": hpo_name,
                "confidence": round(float(confidence), 4),
                "evidence_text": evidence,
                "method": method,
            }

    def add_confirmed_synonym(self, phrase: str, hpo_id: str, hpo_name: str = "") -> None:
        """Active-learning write-back: grow the Indian synonym dictionary (patent #2)."""
        import csv

        from ml_services.config import SEEDS_DIR

        path = SEEDS_DIR / "indian_synonyms.csv"
        exists = path.exists()
        with open(path, "a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if not exists:
                w.writerow(["phrase", "hpo_id", "hpo_name", "language", "notes"])
            w.writerow([phrase.strip().lower(), hpo_id, hpo_name, "hinglish", "added_by_active_learning"])
        self.normalizer.phrase_to_hpo.setdefault(phrase.strip().lower(), []).append(
            {"hpo_id": hpo_id, "hpo_name": hpo_name, "source": "indian_synonym", "language": "hinglish"}
        )


if __name__ == "__main__":
    mapper = HPOMapper()
    demo = [
        "Patient ko 6 mahine se haath pair mein sujan hai aur walking mushkil ho gayi hai.",
        "Peeli aankhein aur piliya do hafte se hai, liver functions disturb hain.",
        "Raat mein na dikhna shuru hua hai, balbala aur kamzori bhi hai.",
    ]
    for d in demo:
        out = mapper.map_text(d)
        prof = ", ".join(f"{i['hpo_id']}({i['confidence']:.2f})" for i in out["hpo_profile"])
        print(f"{d[:48]:50s} -> {prof or '(none)'}")
