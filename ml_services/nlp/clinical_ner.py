"""Module 1: Multilingual Clinical NLP Engine — clinical NER with token-level LID.

Patent claim #1: token-level language identification inside medical NER for Indian
code-mixed clinical text.

Two backends:
  * LexicalRuleNER (always available): longest-match lexicons for symptoms/drugs,
    regexes for duration/lab values/age, family-history cues. Deterministic, fast,
    and used by the offline ASHA path and the test suite.
  * MuRILNER (optional): fine-tuned `google/muril-base-cased` multi-task model
    (train with ml_services.nlp.train_clinical_ner). Loaded automatically when the
    weights exist and transformers is installed.
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from ml_services.config import MODELS_DIR, SEEDS_DIR
from ml_services.utils import read_csv_rows, read_jsonl, token_language

# ----------------------------- lexicons -----------------------------

_DURATION_RE = re.compile(
    r"\b(?:\d{1,2}|ek|do|teen|char|chaar|panch|chhe|saat|aath|nou|das)\s+"
    r"(?:mahine|mahino|mahina|hafte|hafte|hafta|din|saal|saalon|weeks?|months?|days?|years?|months)\b",
    re.IGNORECASE,
)
_LAB_RE = re.compile(
    r"\b(?:Hb|HB|hemoglobin|Hemoglobin|platelets?| TLC |WBC|SGOT|SGPT|serum ceruloplasmin|"
    r"HbA2|HbF|MCV|ferritin)\s*[:=]?\s*\d+(?:\.\d+)?",
    re.IGNORECASE,
)
_AGE_RE = re.compile(
    r"\b(?:\d{1,2}|chhattis|barah|do|teen)\s+(?:saal|mahine|mahine ka|saal ka|years?|months?)\s*"
    r"(?:ka|ki|old)?\b|\bnewborn\b|\bnew born\b",
    re.IGNORECASE,
)
_FAMILY_RE = re.compile(
    r"\b(?:cousin|cousins|consanguineous|first[- ]cousin|paternal|maternal|uncle|aunt|"
    r"parivaar mein|family history|papa ko bhi|maa ko bhi|bhai ko bhi|behen ko bhi|"
    r"shadi rishtedaar mein|hua hai)\b",
    re.IGNORECASE,
)
_SEVERITY_WORDS = {
    "mild": "mild", "severe": "severe", "bahut": "severe", "zyada": "severe",
    "thoda": "mild", "high": "severe", "critical": "severe", "stable": "mild",
}

# Negation cues. Applied from the *context before* a span: the colloquial Indian clinical
# phrasing "vajan nahi badh raha" carries its cue inside the matched span but is a positive
# finding, so cues inside the span are deliberately ignored.
_NEGATION_CUES = {
    "nahi", "nahin", "na", "no", "not", "never", "without", "absent", "denies", "denied",
    "bina", "kabhi nahi", "koi nahi", "nahi hai", "raha nahi", "ruled out", "negative for",
}
_CLAUSE_BREAKS = {"and", "but", "aur", "par", "lekin", "magar", "however", "whereas", ","}
_NEGATION_WINDOW_TOKENS = 6
_DURATION_WINDOW_TOKENS = 4

_CONF_BY_SOURCE = {"lexicon": 0.95, "regex": 0.99, "prefix": 0.68, "muril": 0.90}


class LexicalRuleNER:
    """Deterministic lexicon + regex clinical NER for Hindi/Hinglish/English."""

    def __init__(self) -> None:
        self.symptom_lexicon: List[dict] = []  # {phrase, hpo_id, hpo_name}
        self.drug_lexicon: List[str] = []
        self._load_lexicons()

    def _load_lexicons(self) -> None:
        syn_path = SEEDS_DIR / "indian_synonyms.csv"
        if syn_path.exists():
            for r in read_csv_rows(syn_path):
                phrase = (r.get("phrase") or "").strip().lower()
                if phrase:
                    self.symptom_lexicon.append(
                        {"phrase": phrase, "hpo_id": r.get("hpo_id", ""), "hpo_name": r.get("hpo_name", "")}
                    )
        drugs_path = SEEDS_DIR / "drugs.csv"
        if drugs_path.exists():
            self.drug_lexicon = [r["drug_name"].lower() for r in read_csv_rows(drugs_path) if r.get("drug_name")]
        # Romanised-Hindi vocabulary for token-level LID: the synonym dictionary is the
        # domain-specific part; utils supplies the general Hinglish function words.
        self.romanized_vocab = set()
        for entry in self.symptom_lexicon:
            for tok in entry["phrase"].split():
                if tok.isascii() and tok.isalpha():
                    self.romanized_vocab.add(tok.lower())
        # English HPO names as additional symptom triggers (doctors write English too)
        from ml_services.etl.graph_store import load_processed

        g = load_processed()
        if g:
            have = {s["phrase"] for s in self.symptom_lexicon}
            for n in g.by_type("Hpo"):
                nm = n["name"].lower()
                if nm and nm not in have and len(nm) > 4:
                    self.symptom_lexicon.append({"phrase": nm, "hpo_id": n["id"], "hpo_name": n["name"]})

        # Index once, after every source has contributed to the lexicon.
        self.symptom_lexicon_index = {s["phrase"]: s for s in self.symptom_lexicon}
        self.single_token_symptoms = sorted(
            {s["phrase"] for s in self.symptom_lexicon
             if " " not in s["phrase"] and s["phrase"].isascii() and s["phrase"].isalpha()
             and 5 <= len(s["phrase"]) <= 14}
        )

    # --------------------- matching ---------------------

    def _find_lexicon_spans(self, text: str, lexicon: List[str]):
        tl = text.lower()
        spans = []
        for phrase in sorted(lexicon, key=len, reverse=True):
            start = 0
            while True:
                idx = tl.find(phrase, start)
                if idx < 0:
                    break
                end = idx + len(phrase)
                boundary_before = idx == 0 or not (tl[idx - 1].isalnum())
                boundary_after = end >= len(tl) or not tl[end].isalnum()
                if boundary_before and boundary_after:
                    spans.append((idx, end))
                start = idx + max(1, len(phrase))
        # resolve overlaps, keep longest
        spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
        kept: List[tuple] = []
        last_end = -1
        for s, e in spans:
            if s >= last_end:
                kept.append((s, e))
                last_end = e
        return kept

    def extract(self, text: str) -> dict:
        entities: List[dict] = []
        tl = text.lower()

        phrase_to_entry = {s["phrase"]: s for s in self.symptom_lexicon}
        for s, e in self._find_lexicon_spans(text, [x["phrase"] for x in self.symptom_lexicon]):
            entry = phrase_to_entry[tl[s:e]]
            entities.append({"start": s, "end": e, "text": text[s:e], "label": "SYMPTOM",
                             "hpo_id": entry["hpo_id"], "hpo_name": entry["hpo_name"],
                             "lid": self._span_lid(text, s, e), "source": "lexicon"})


        for s, e in self._find_lexicon_spans(text, self.drug_lexicon):
            entities.append({"start": s, "end": e, "text": text[s:e], "label": "DRUG",
                             "lid": self._span_lid(text, s, e), "source": "lexicon"})

        for m in _DURATION_RE.finditer(text):
            entities.append({"start": m.start(), "end": m.end(), "text": m.group(0), "label": "DURATION",
                             "lid": self._span_lid(text, m.start(), m.end()), "source": "regex"})
        for m in _LAB_RE.finditer(text):
            entities.append({"start": m.start(), "end": m.end(), "text": m.group(0), "label": "LAB_VALUE",
                             "lid": self._span_lid(text, m.start(), m.end()), "source": "regex"})
        for m in _AGE_RE.finditer(text):
            entities.append({"start": m.start(), "end": m.end(), "text": m.group(0), "label": "AGE",
                             "lid": self._span_lid(text, m.start(), m.end()), "source": "regex"})
        for m in _FAMILY_RE.finditer(text):
            entities.append({"start": m.start(), "end": m.end(), "text": m.group(0), "label": "FAMILY_HISTORY",
                             "lid": self._span_lid(text, m.start(), m.end()), "source": "regex"})

        entities.extend(self._prefix_fallback_spans(text, entities))

        entities.sort(key=lambda x: x["start"])
        tokens = [{"text": t, "lid": token_language(t, self.romanized_vocab)} for t in text.split()]
        for e in entities:
            e.setdefault("confidence", _CONF_BY_SOURCE.get(e.get("source", ""), 0.5))
        self._annotate_negation(text, entities)
        self._attach_durations(text, entities)
        lid_counts: Dict[str, int] = {}
        for t in tokens:
            lid_counts[t["lid"]] = lid_counts.get(t["lid"], 0) + 1

        return {
            "text": text,
            "entities": entities,
            "tokens": tokens,
            "lid_counts": lid_counts,
            "is_code_mixed": len([k for k in lid_counts if lid_counts[k] > 0]) > 1,
            "romanised_hindi_tokens": sum(1 for t in tokens if t["lid"] == "HI-LATN"),
            "engine": "lexical_rule_ner",
            "negated_symptoms": [e["text"] for e in entities if e.get("negated")],
            "onset_durations": {e["text"]: e["duration"] for e in entities if e.get("duration")},
        }

    # --------------------- generalisation: unseen surface forms ---------------------

    def _prefix_fallback_spans(self, text: str, found: List[dict]) -> List[dict]:
        """Catch inflectional variants not present verbatim in the dictionary.

        Romanised Hindi is highly inflected (kamzor/kamzori, sujan/soojan, dard/dardii) and
        ASR output adds more variation. When a token shares a >= 5-character stem with exactly
        one single-token symptom entry, accept it at lower confidence and route it through the
        module-10 review queue via the mapper's low-confidence path.
        """
        if not self.single_token_symptoms:
            return []
        covered = [(e["start"], e["end"]) for e in found]
        out: List[dict] = []
        for m in re.finditer(r"[A-Za-z]{4,}", text):
            tok = m.group(0).lower()
            if any(s <= m.start() < e or s < m.end() <= e for s, e in covered):
                continue
            hits = [t for t in self.single_token_symptoms if t != tok and
                    (tok.startswith(t[:5]) or t.startswith(tok[:5])) and abs(len(t) - len(tok)) <= 3]
            if len(hits) != 1:
                continue
            entry = self.symptom_lexicon_index[hits[0]]
            if not entry.get("hpo_id"):
                continue
            out.append({"start": m.start(), "end": m.end(), "text": text[m.start():m.end()],
                        "label": "SYMPTOM", "hpo_id": entry["hpo_id"], "hpo_name": entry["hpo_name"],
                        "lid": self._span_lid(text, m.start(), m.end()), "source": "prefix",
                        "matched_lexicon_form": hits[0]})
        return out

    # --------------------- negation + onset duration ---------------------

    def _annotate_negation(self, text: str, entities: List[dict]) -> None:
        words = text.split()
        starts: List[int] = []
        pos = 0
        for w in words:
            starts.append(pos)
            pos += len(w) + 1

        for e in entities:
            if e["label"] != "SYMPTOM":
                continue
            first = 0
            for i, s in enumerate(starts):
                if s < e["start"]:
                    first = i + 1
            window = words[max(0, first - _NEGATION_WINDOW_TOKENS):first]
            # Cues never cross a sentence boundary: "... nahi hota. Bahut kamzor hai" must
            # not negate "kamzor".
            for i in range(len(window) - 1, -1, -1):
                if window[i][-1:] in ".;!?।" or window[i].lower().strip(",") in _CLAUSE_BREAKS:
                    window = window[i + 1:]
                    break
            ctx = " ".join(w.lower().strip(".,;!?") for w in window)
            e["negated"] = any(re.search(rf"\b{re.escape(cue)}\b", ctx) for cue in _NEGATION_CUES)
            if e["negated"]:
                e["negation_context"] = ctx

    def _attach_durations(self, text: str, entities: List[dict]) -> None:
        durations = [e for e in entities if e["label"] == "DURATION"]
        symptoms = [e for e in entities if e["label"] == "SYMPTOM"]
        for s in symptoms:
            best, best_gap = None, None
            for d in durations:
                gap = (s["start"] - d["end"]) if d["end"] <= s["start"] else (d["start"] - s["end"])
                if gap < 0 or gap > _DURATION_WINDOW_TOKENS * 12:
                    continue
                if best_gap is None or gap < best_gap:
                    best, best_gap = d, gap
            if best is not None:
                s["duration"] = best["text"].strip()

    def _span_lid(self, text: str, s: int, e: int) -> str:
        span = text[s:e]
        lids = {token_language(tok, self.romanized_vocab) for tok in span.split() if tok.strip()}
        if not lids:
            return "EN"
        if len(lids) > 1:
            return "MIXED"
        return lids.pop()


class MuRILNER:
    """Fine-tuned MuRIL token-classification backend (optional)."""

    def __init__(self, model_dir=None):
        from transformers import AutoModelForTokenClassification, AutoTokenizer  # requires transformers

        model_dir = model_dir or (MODELS_DIR / "clinical_ner_muril")
        self.tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
        self.model = AutoModelForTokenClassification.from_pretrained(str(model_dir))
        self.model.eval()
        labels_path = model_dir / "labels.json"
        with open(labels_path, "r", encoding="utf-8") as f:
            self.label_list: List[str] = json.load(f)

    def extract(self, text: str) -> dict:
        import torch

        tokens = text.split()
        enc = self.tokenizer(tokens, is_split_into_words=True, return_tensors="pt", truncation=True)
        with torch.no_grad():
            logits = self.model(**enc).logits[0]
        word_ids = enc.word_ids(0)
        preds = logits.argmax(-1).tolist()
        entities = []
        seen_word: Dict[int, dict] = {}
        for i, wid in enumerate(word_ids):
            if wid is None:
                continue
            label = self.label_list[preds[i]]
            if label == "O" or wid in seen_word:
                continue
            seen_word[wid] = {"token_index": wid, "label": label.replace("B-", "").replace("I-", "")}
        # group consecutive tokens of same label into spans (whitespace tokens)
        cur_label, cur_start = None, None
        for wid in sorted(seen_word):
            lab = seen_word[wid]["label"]
            tok = tokens[wid]
            start = len(" ".join(tokens[:wid])) + (1 if wid else 0)
            end = start + len(tok)
            if lab != cur_label:
                if cur_label is not None:
                    entities.append({"start": cur_start, "end": prev_end, "text": text[cur_start:prev_end],
                                     "label": cur_label, "lid": "MIXED", "source": "muril"})
                cur_label, cur_start = lab, start
            prev_end = end
        if cur_label is not None:
            entities.append({"start": cur_start, "end": prev_end, "text": text[cur_start:prev_end],
                             "label": cur_label, "lid": "MIXED", "source": "muril"})
        tokens_lid = [{"text": t, "lid": token_language(t)} for t in tokens]
        return {"text": text, "entities": sorted(entities, key=lambda x: x["start"]),
                "tokens": tokens_lid, "lid_counts": {}, "is_code_mixed": True}


def get_ner():
    """Pick the best available backend: fine-tuned MuRIL if present, else lexical."""
    model_dir = MODELS_DIR / "clinical_ner_muril"
    if (model_dir / "config.json").exists():
        try:
            return MuRILNER(model_dir)
        except Exception:
            pass
    return LexicalRuleNER()


ClinicalNER = LexicalRuleNER  # public alias


if __name__ == "__main__":
    ner = get_ner()
    demo = [
        "Patient ko 6 mahine se haath pair mein sujan hai aur walking mushkil ho gayi hai.",
        "Peeli aankhein aur piliya do hafte se hai, liver functions disturb hain.",
        "Prescription mein clopidogrel 75mg aur atorvastatin likha gaya hai.",
        "Maa puchi thi ki cousin marriage hai, consanguineous shadi hui hai.",
    ]
    for d in demo:
        r = ner.extract(d)
        ents = ", ".join(f"{e['label']}:'{e['text']}'" for e in r["entities"])
        print(f"[{'code-mixed' if r['is_code_mixed'] else 'monolingual'}] {ents or '(none)'}")
