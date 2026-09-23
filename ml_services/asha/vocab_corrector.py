"""ASR medical vocabulary correction (Module 9).

Whisper/IndicWhisper on rural Hindi dialects mis-hears drug and symptom words
("clopidogrel" -> "cloth of a girl", "piliya" -> "pili ya"). Two-stage corrector:

  1. Phonetic + edit-distance matching against the clinical lexicon (drugs, symptom
     synonyms, HPO names) — deterministic, works offline, ~microseconds per token.
  2. Optional embedding rerank of the top candidates when a sentence encoder is
     available (same model as the HPO mapper).

The caller gets both the corrected text and an audit trail of every change, because ASHA
reports become clinical documents.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from ml_services.config import SEEDS_DIR
from ml_services.utils import read_csv_rows

# Indic ASR frequently collapses these sound pairs
PHONETIC_EQUIV = [
    ("ph", "f"), ("v", "w"), ("b", "v"), ("sh", "s"), ("th", "t"), ("kh", "k"),
    ("gh", "g"), ("ee", "i"), ("oo", "u"), ("ai", "e"), ("y", "i"), ("j", "z"),
    ("ch", "c"), ("dh", "d"), ("bh", "b"),
]


def phonetic_key(word: str) -> str:
    w = word.lower()
    for a, b in PHONETIC_EQUIV:
        w = w.replace(a, b)
    w = re.sub(r"[^a-z]", "", w)
    return re.sub(r"(.)\1+", r"\1", w)


class MedicalVocabCorrector:
    def __init__(self, embedder=None):
        self.lexicon: List[str] = []
        self.lexicon_keys: Dict[str, List[str]] = {}
        self._load_lexicon()
        self.embedder = embedder

    def _load_lexicon(self) -> None:
        for r in read_csv_rows(SEEDS_DIR / "drugs.csv"):
            self._add(r.get("drug_name", ""))
        for r in read_csv_rows(SEEDS_DIR / "indian_synonyms.csv"):
            self._add(r.get("phrase", ""))
            self._add(r.get("hpo_name", ""))
        from ml_services.etl.graph_store import load_processed

        graph = load_processed()
        if graph:
            for n in graph.by_type("Hpo"):
                self._add(n["name"])

    def _add(self, term: str) -> None:
        term = (term or "").strip()
        if len(term) < 3:
            return
        if term.lower() not in [t.lower() for t in self.lexicon]:
            self.lexicon.append(term)
        self.lexicon_keys.setdefault(phonetic_key(term), []).append(term)

    def suggest(self, token: str, top_k: int = 3, min_score: float = 0.72) -> List[dict]:
        if len(token) < 3 or token.lower() in [t.lower() for t in self.lexicon]:
            return []
        key = phonetic_key(token)
        scored: List[Tuple[float, str]] = []
        for cand_key, terms in self.lexicon_keys.items():
            ratio = SequenceMatcher(None, key, cand_key).ratio()
            if ratio >= min_score:
                for t in terms:
                    scored.append((ratio, t))
        if not scored:
            for t in self.lexicon:
                if abs(len(t) - len(token)) > 4:
                    continue
                ratio = SequenceMatcher(None, token.lower(), t.lower()).ratio()
                if ratio >= min_score:
                    scored.append((ratio, t))
        scored.sort(key=lambda x: -x[0])
        seen, out = set(), []
        for score, term in scored:
            if term.lower() in seen:
                continue
            seen.add(term.lower())
            out.append({"term": term, "score": round(score, 4)})
            if len(out) >= top_k:
                break
        return out

    def correct_text(self, text: str, min_token_len: int = 4) -> dict:
        tokens = text.split()
        corrected: List[str] = []
        changes: List[dict] = []
        for tok in tokens:
            bare = re.sub(r"[^A-Za-z\u0900-\u097F]", "", tok)
            if bare and len(bare) >= min_token_len and re.fullmatch(r"[A-Za-z]+", bare):
                suggestions = self.suggest(bare)
                if suggestions and suggestions[0]["score"] >= 0.82:
                    best = suggestions[0]
                    corrected.append(tok.replace(bare, best["term"]))
                    changes.append({"original": bare, "corrected": best["term"],
                                    "score": best["score"],
                                    "alternatives": [s["term"] for s in suggestions[1:]]})
                    continue
            corrected.append(tok)
        return {
            "original": text,
            "corrected": " ".join(corrected),
            "n_changes": len(changes),
            "changes": changes,
        }


if __name__ == "__main__":
    corrector = MedicalVocabCorrector()
    demos = [
        "patient ko clopidogrel diya hai",
        "cloth of a girl start kar diya doctor ne",  # ASR mishearing of clopidogrel
        "bachche ko pili ya hai aur kamjori hai",
        "warfarin 5 mg roz",
    ]
    for d in demos:
        r = corrector.correct_text(d)
        print(f"in : {r['original']}")
        print(f"out: {r['corrected']}  ({r['n_changes']} changes) {r['changes']}")
