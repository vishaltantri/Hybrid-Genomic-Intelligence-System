"""Template-based augmentation for the clinical NER seed corpus.

Why: 25 hand-labelled sentences cannot fine-tune MuRIL (span F1 was 0.0 — the
model memorised instead of generalising). This module composes new Hinglish
clinical sentences from templates + the project's own lexicons (Indian symptom
synonyms, drugs, durations, lab values, family-history cues). Gold spans are
exact by construction, so the augmented corpus needs no relabelling.

Every generated sentence is marked {"augmented": true}; the hand-labelled seed
stays the evaluation core.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import List

from ml_services.config import SEEDS_DIR
from ml_services.utils import read_csv_rows, write_jsonl

CONNECTORS = ["aur", "ke saath", "saath mein", "plus", "and"]
FEELERS = ["hai", "ho gaya hai", "hua hai", "lag raha hai", "rehta hai"]
PATIENTS = ["Patient ko", "Bachche ko", "Mujhe", "Usko", "Bacche ko", "Mariz ko"]


def _load_vocab() -> dict:
    symptoms = []
    for r in read_csv_rows(SEEDS_DIR / "indian_synonyms.csv"):
        p = (r.get("phrase") or "").strip().lower()
        if p:
            symptoms.append({"text": p, "label": "SYMPTOM"})
    drugs = [{"text": r["drug_name"].lower(), "label": "DRUG"}
             for r in read_csv_rows(SEEDS_DIR / "drugs.csv") if r.get("drug_name")]
    nums = ["do", "teen", "char", "panch", "chhe", "saat", "aath", "nou", "das",
            "2", "3", "4", "5", "6", "8", "10", "12"]
    units = ["din", "hafte", "mahine", "saal", "weeks", "months", "years"]
    durations = [{"text": f"{n} {u}", "label": "DURATION"} for n in nums for u in units]
    ages = [{"text": f"{n} {u} ka", "label": "AGE"} for n in nums[:12] for u in ("saal", "mahine")]
    labs = [{"text": f"{t} {v}", "label": "LAB_VALUE"}
            for t in ("Hb", "HbA2", "MCV", "platelets", "TLC", "ferritin", "SGOT")
            for v in ("5.2", "7.8", "9.0", "12.4", "3.1", "88", "60")]
    family = [{"text": t, "label": "FAMILY_HISTORY"} for t in
              ("cousin marriage", "consanguineous shadi", "family history", "parivaar mein",
               "papa ko bhi", "maa ko bhi", "bhai ko bhi yahi")]
    return {"SYMPTOM": symptoms, "DRUG": drugs, "DURATION": durations,
            "AGE": ages, "LAB_VALUE": labs, "FAMILY_HISTORY": family}


class _Sentence:
    """Incremental string builder recording gold char spans."""

    def __init__(self):
        self.parts: List[str] = []
        self.entities: List[dict] = []

    def word(self, w: str) -> "_Sentence":
        self.parts.append(w)
        return self

    def ent(self, text: str, label: str) -> "_Sentence":
        start = sum(len(p) + 1 for p in self.parts)
        self.parts.append(text)
        self.entities.append({"start": start, "end": start + len(text), "label": label})
        return self

    def build(self) -> dict:
        text = " ".join(self.parts).replace(" ,", ",").replace(" .", ".") + "."
        return {"text": text, "entities": self.entities, "augmented": True, "lang": "HI-EN-AUG"}


def generate(n: int = 400, seed: int = 29, out_path: Path | None = None) -> dict:
    rng = random.Random(seed)
    v = _load_vocab()
    out: List[dict] = []
    seen = set()
    tries = 0
    while len(out) < n and tries < n * 20:
        tries += 1
        s = _Sentence()
        pattern = rng.randint(0, 5)
        if pattern == 0:  # symptom + duration
            s.word(rng.choice(PATIENTS))
            e = rng.choice(v["SYMPTOM"]); s.ent(**e)
            d = rng.choice(v["DURATION"]); s.word(f"{d['text']} se")
            s.word(rng.choice(FEELERS))
        elif pattern == 1:  # two symptoms
            s.word(rng.choice(PATIENTS))
            e1 = rng.choice(v["SYMPTOM"]); s.ent(**e1)
            s.word(rng.choice(CONNECTORS))
            e2 = rng.choice([x for x in v["SYMPTOM"] if x["text"] != e1["text"]]); s.ent(**e2)
            s.word(rng.choice(FEELERS))
        elif pattern == 2:  # symptom + drug
            s.word(rng.choice(PATIENTS))
            e = rng.choice(v["SYMPTOM"]); s.ent(**e)
            s.word(rng.choice(CONNECTORS))
            d = rng.choice(v["DRUG"]); s.ent(**d)
            s.word(rng.choice(("chal raha hai", "diya gaya hai", "shuru kiya")))
        elif pattern == 3:  # age + symptom
            s.word("Bacha" if rng.random() < 0.5 else "Child")
            a = rng.choice(v["AGE"]); s.ent(**a)
            s.word(rng.choice(("hai,", "hai aur")))
            e = rng.choice(v["SYMPTOM"]); s.ent(**e)
            s.word(rng.choice(FEELERS))
        elif pattern == 4:  # lab + family history
            l = rng.choice(v["LAB_VALUE"]); s.ent(**l)
            s.word(rng.choice(("hai,", "hai aur")))
            f = rng.choice(v["FAMILY_HISTORY"]); s.ent(**f)
        else:  # negation context (labels still mark the span; negation is contextual)
            s.word(rng.choice(PATIENTS))
            e = rng.choice(v["SYMPTOM"]); s.ent(**e)
            s.word(rng.choice(("nahi hai.", "nahin hai.", "nahi tha.")))
            s.word(rng.choice(("Lekin", "Par")))
            e2 = rng.choice(v["SYMPTOM"]); s.ent(**e2)
            s.word(rng.choice(FEELERS))
        row = s.build()
        if row["text"] in seen:
            continue
        seen.add(row["text"])
        row["id"] = f"aug{len(out) + 1:04d}"
        out.append(row)
    out_path = out_path or (SEEDS_DIR / "clinical_ner_augmented.jsonl")
    write_jsonl(out_path, out)
    from collections import Counter
    lab = Counter(e["label"] for r in out for e in r["entities"])
    return {"sentences": len(out), "labels": dict(lab), "path": str(out_path)}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=400)
    args = ap.parse_args()
    print(json.dumps(generate(args.n), indent=1))
