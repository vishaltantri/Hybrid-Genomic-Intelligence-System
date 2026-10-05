"""Clinical text intelligence (Phase 5): a structuring layer over the existing NER and HPO mapper.

Nothing here is a second NER or a second HPO matcher:
  * spans for phenotypes, drugs, labs, ages and durations come from the existing NER backend (`registry.ner`),
  * phenotype -> HPO normalisation uses the NER's dictionary hit or the existing `HPOMapper.map_phrase`,
  * genes, diseases and drugs are normalised only against the Genomera knowledge graph; variants are recognised with the
    same HGVS/rsID patterns the evidence module uses.
The layer adds what the NER does not carry: per-concept assertion (present / absent / possible / historical), experiencer
(patient vs family member), onset, severity, and an explicit normalisation status. It is rule-based and says so.

Entity types NOT produced because no lexicon or model backs them in this deployment: PROCEDURE, ANATOMICAL_SITE.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Tuple

from ml_services.evidence import normalize as EN

SUPPORTED_LABELS = ["PHENOTYPE", "DISEASE", "GENE", "VARIANT", "DRUG", "LAB", "FAMILY_RELATION", "AGE", "ONSET", "SEVERITY"]
UNSUPPORTED_LABELS = {"PROCEDURE": "no procedure lexicon or model is configured",
                      "ANATOMICAL_SITE": "no anatomy lexicon or model is configured"}
MAX_TEXT = 20000
MAP_ACCEPT = 0.6          # mapper score needed to accept an HPO mapping without review
REVIEW_BELOW = 0.75       # NER confidence under which a lexicon mapping is flagged for review

_RELATIONS = {
    "mother": "mother", "mom": "mother", "maa": "mother", "mummy": "mother", "father": "father", "dad": "father", "papa": "father",
    "brother": "brother", "bhai": "brother", "sister": "sister", "behen": "sister", "sibling": "sibling", "siblings": "sibling",
    "son": "son", "daughter": "daughter", "uncle": "uncle", "chacha": "uncle", "mama": "uncle", "aunt": "aunt", "mausi": "aunt",
    "bua": "aunt", "cousin": "cousin", "grandmother": "grandmother", "dadi": "grandmother", "nani": "grandmother",
    "grandfather": "grandfather", "dada": "grandfather", "nana": "grandfather", "parents": "parent", "parent": "parent",
}
_REL_RE = re.compile(r"\b(" + "|".join(sorted(_RELATIONS, key=len, reverse=True)) + r")\b", re.I)

_NEG_BEFORE = [r"no", r"not", r"denies", r"denied", r"without", r"absent", r"negative for", r"free of", r"no evidence of",
               r"no history of", r"never", r"nahi", r"nahin", r"koi nahi", r"bina"]
_NEG_AFTER = [r"nahi(?: hai| hota| hain)?", r"nahin", r"absent", r"not present", r"not seen", r"negative", r"was ruled out", r"ruled out"]
_RULED_OUT = [r"ruled out", r"excluded", r"r/o excluded"]
_UNCERTAIN = [r"possible", r"possibly", r"probable", r"probably", r"suspected", r"suspicion of", r"suspicious for", r"likely",
              r"query", r"\?", r"may have", r"might have", r"cannot exclude", r"consider", r"concern for", r"r/o", r"rule out",
              r"\?\s*", r"shayad", r"differential includes"]
_HISTORY = [r"history of", r"h/o", r"past history of", r"previous(?:ly)?", r"prior", r"resolved", r"earlier had"]
_SEVERITY = {"mild": "mild", "mildly": "mild", "moderate": "moderate", "moderately": "moderate", "severe": "severe", "severely": "severe",
             "profound": "profound", "marked": "severe", "gross": "severe", "slight": "mild"}
_ONSET_TERMS = {"congenital": "Congenital onset", "from birth": "Congenital onset", "since birth": "Congenital onset",
                "neonatal": "Neonatal onset", "infantile": "Infantile onset", "childhood onset": "Childhood onset",
                "juvenile": "Juvenile onset", "adult onset": "Adult onset", "late onset": "Late onset"}
_ONSET_TERM_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, _ONSET_TERMS), key=len, reverse=True)) + r")\b", re.I)
_DUR_RE = re.compile(r"\b(\d{1,3})\s*(days?|weeks?|months?|years?|yrs?|mahine|mahino|hafte|saal|din)\b", re.I)
_SENT_SPLIT = re.compile(r"(?<=[.;!?।\n])\s+")


def _alt(items: Iterable[str]) -> str:
    return "(?:" + "|".join(items) + ")"


_NEG_BEFORE_RE = re.compile(r"(?:^|\W)" + _alt(_NEG_BEFORE) + r"\W+(?:\w+\W+){0,4}$", re.I)
_NEG_AFTER_RE = re.compile(r"^\W*(?:\w+\W+){0,2}?" + _alt(_NEG_AFTER) + r"\b", re.I)
_UNC_BEFORE_RE = re.compile(_alt(_UNCERTAIN) + r"\W*(?:\w+\W+){0,4}$", re.I)
_HIST_BEFORE_RE = re.compile(_alt(_HISTORY) + r"\W+(?:\w+\W+){0,4}$", re.I)
_RULED_AFTER_RE = re.compile(r"^\W*(?:\w+\W+){0,2}?" + _alt(_RULED_OUT), re.I)
_RULED_BEFORE_RE = re.compile(_alt(_RULED_OUT) + r"\W+(?:\w+\W+){0,3}$", re.I)
_CLAUSE_SPLIT = re.compile(r"\s*(?:,|;|:|\bbut\b|\bhowever\b|\balthough\b|\bwhereas\b|\blekin\b|\bpar\b|\bmagar\b|\baur\b|\band\b)\s*", re.I)


def _sentence_bounds(text: str) -> List[Tuple[int, int]]:
    out, pos = [], 0
    for part in _SENT_SPLIT.split(text):
        i = text.find(part, pos)
        if i < 0:
            continue
        out.append((i, i + len(part)))
        pos = i + len(part)
    return out or [(0, len(text))]


def _clause_before(text: str, start: int, sent_start: int) -> str:
    """Text of the current clause preceding `start`; cues never cross sentences or clause breaks (so 'no fever, tremor
    present' does not negate tremor). A negation list ('no fever, seizures or tremor') is handled by `_list_negated`."""
    seg = text[sent_start:start]
    parts = _CLAUSE_SPLIT.split(seg)
    return parts[-1] if parts else seg


def _clause_after(text: str, end: int, sent_end: int) -> str:
    seg = text[end:sent_end]
    return _CLAUSE_SPLIT.split(seg, maxsplit=1)[0]


def _list_negated(text: str, start: int, sent_start: int) -> bool:
    """'No fever, seizures or tremor': a negation cue opens a comma/or-separated list that continues to the span."""
    seg = text[sent_start:start]
    m = re.search(r"(?:^|\W)(no|denies|denied|without|negative for|absent)\W+([\w\s,/-]*)$", seg, re.I)
    if not m:
        return False
    tail = m.group(2)
    return not re.search(r"\b(but|however|although|whereas|and has|with)\b", tail, re.I) and len(tail.split()) <= 12


def assess_context(text: str, start: int, end: int, sentence: Tuple[int, int]) -> dict:
    """Assertion / experiencer for one concept span, from its own sentence only."""
    s0, s1 = sentence
    before = _clause_before(text, start, s0)
    after = _clause_after(text, end, s1)
    ruled = bool(_RULED_AFTER_RE.search(after) or _RULED_BEFORE_RE.search(before))
    negated = ruled or bool(_NEG_BEFORE_RE.search(before) or _NEG_AFTER_RE.search(after) or _list_negated(text, start, s0))
    uncertain = bool(_UNC_BEFORE_RE.search(before))
    historical = bool(_HIST_BEFORE_RE.search(before))
    rel = None
    for m in _REL_RE.finditer(text[s0:end]):
        # a relation counts when it appears in the same clause as the concept (possessive/predicate forms)
        gap = text[s0 + m.end():start]
        if not _CLAUSE_SPLIT.search(gap) and len(gap.split()) <= 8:
            rel = _RELATIONS[m.group(1).lower()]
    if not rel:
        # "Wilson disease ruled out in brother", "tremor in her mother"
        m = re.match(r"^\W*(?:\w+\W+){0,3}?(?:in|of|for|among)\s+(?:his|her|the)?\s*(\w+)\b", after, re.I)
        if m and m.group(1).lower() in _RELATIONS:
            rel = _RELATIONS[m.group(1).lower()]
    if re.search(r"\b(family history|fh)\b", before, re.I) and not rel:
        rel = "family (unspecified)"
    if negated:
        assertion = "absent"
    elif uncertain:
        assertion = "possible"
    elif historical:
        assertion = "historical"
    else:
        assertion = "present"
    return {"assertion": assertion, "negated": negated, "ruled_out": ruled, "uncertain": uncertain and not negated,
            "historical": historical, "experiencer": "family" if rel else "patient", "family_relation": rel}


class ClinicalTextAnalyzer:
    def __init__(self, registry):
        self.registry = registry
        self._gene_ids: Optional[set] = None
        self._diseases: Optional[List[dict]] = None
        self._drugs: Optional[Dict[str, str]] = None

    # ---------------------------- lexicons from the graph ----------------------------
    def _load(self) -> None:
        if self._gene_ids is not None:
            return
        g = self.registry.graph
        self._gene_ids = {n["id"] for n in g.by_type("Gene")}
        self._diseases = []
        for n in g.by_type("Disease"):
            names = {n["name"].lower()} | {s.lower() for s in (n.get("synonyms") or []) if s}
            for nm in names:
                if len(nm) >= 5:
                    self._diseases.append({"phrase": nm, "id": n["id"], "name": n["name"]})
        self._diseases.sort(key=lambda d: -len(d["phrase"]))
        self._drugs = {n["id"].lower(): n["id"] for n in g.by_type("Drug")}

    # ---------------------------- helpers ----------------------------
    @staticmethod
    def _sent_of(sents: List[Tuple[int, int]], pos: int) -> Tuple[int, int]:
        for a, b in sents:
            if a <= pos < b or pos == b:
                return a, b
        return sents[-1]

    @staticmethod
    def _word_spans(text: str, phrase: str) -> List[Tuple[int, int]]:
        return [(m.start(), m.end()) for m in re.finditer(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text, re.I)]

    def _normalise_phenotype(self, ent: dict) -> dict:
        mapper = self.registry.hpo_mapper
        if ent.get("hpo_id"):
            conf = float(ent.get("confidence", 0.5))
            node = self.registry.graph.node("Hpo", ent["hpo_id"])
            return {"system": "HPO", "id": ent["hpo_id"], "name": (node or {}).get("name") or ent.get("hpo_name") or ent["text"],
                    "method": f"ner_{ent.get('source', 'lexicon')}", "confidence": round(conf, 3),
                    "status": "normalized" if conf >= REVIEW_BELOW else "needs_review"}
        ranked = mapper.map_phrase(ent["text"])
        if ranked and ranked[0]["score"] >= MAP_ACCEPT:
            top = ranked[0]
            return {"system": "HPO", "id": top["hpo_id"], "name": top.get("hpo_name") or top["hpo_id"], "method": f"hpo_mapper_{top.get('source', 'fuzzy')}",
                    "confidence": round(float(top["score"]), 3), "status": "normalized"}
        if ranked and ranked[0]["score"] >= 0.35:
            top = ranked[0]
            return {"system": "HPO", "id": top["hpo_id"], "name": top.get("hpo_name") or top["hpo_id"], "method": f"hpo_mapper_{top.get('source', 'fuzzy')}",
                    "confidence": round(float(top["score"]), 3), "status": "needs_review"}
        return {"system": "HPO", "id": None, "name": None, "method": None, "confidence": None, "status": "unmapped"}

    # ---------------------------- main ----------------------------
    def analyze(self, text: str) -> dict:
        self._load()
        sents = _sentence_bounds(text)
        base = self.registry.ner.extract(text)
        ents: List[dict] = []

        def add(label, s, e, source, confidence, **kw):
            ent = {"label": label, "start": s, "end": e, "text": text[s:e], "source": source, "confidence": round(float(confidence), 3),
                   "normalized": None, "assertion": None, "negated": False, "uncertain": False, "historical": False,
                   "experiencer": None, "family_relation": None}
            ent.update(kw)
            ents.append(ent)
            return ent

        # AGE vs ONSET: the base NER reports every "N unit" as a DURATION and often as an AGE too.
        for m in _DUR_RE.finditer(text):
            tail = text[m.end():m.end() + 14].lower()
            head = text[max(0, m.start() - 12):m.start()].lower()
            if re.match(r"[\s-]*(old|ka|ki)\b", tail) or re.search(r"\b(aged?|age)\W*$", head):
                add("AGE", m.start(), m.end() + (len(re.match(r"[\s-]*(old|ka|ki)\b", tail).group(0)) if re.match(r"[\s-]*(old|ka|ki)\b", tail) else 0),
                    "regex", 0.99, value={"amount": int(m.group(1)), "unit": m.group(2).lower()})
            elif re.search(r"\b(since|for|from|over|past|last)\W*$", head) or re.match(r"\W*(se|ago|back)\b", tail):
                add("ONSET", m.start(), m.end(), "regex", 0.95, value={"amount": int(m.group(1)), "unit": m.group(2).lower(), "kind": "duration"})
        for m in _ONSET_TERM_RE.finditer(text):
            add("ONSET", m.start(), m.end(), "lexicon", 0.95, value={"kind": "onset_term", "term": _ONSET_TERMS[m.group(1).lower()]})
        for m in re.finditer(r"\bnew[- ]?born\b", text, re.I):
            add("AGE", m.start(), m.end(), "regex", 0.99, value={"term": "newborn"})

        covered: List[Tuple[int, int]] = []
        # --- phenotypes from the NER (symptom spans); negation is re-assessed with the sentence-scoped rules below
        for e in base["entities"]:
            if e["label"] == "SYMPTOM":
                ent = add("PHENOTYPE", e["start"], e["end"], e.get("source", "ner"), e.get("confidence", 0.5), hpo_id=e.get("hpo_id"), hpo_name=e.get("hpo_name"))
                ent["normalized"] = self._normalise_phenotype({**e, "text": text[e["start"]:e["end"]]})
                covered.append((e["start"], e["end"]))
            elif e["label"] == "DRUG":
                nm = e["text"].lower()
                add("DRUG", e["start"], e["end"], "lexicon", e.get("confidence", 0.9),
                    normalized={"system": "Genomera drug list", "id": self._drugs.get(nm), "name": self._drugs.get(nm) or e["text"], "method": "exact",
                                "confidence": 0.95, "status": "normalized" if nm in self._drugs else "unmapped"})
                covered.append((e["start"], e["end"]))
            elif e["label"] == "LAB_VALUE":
                m = re.match(r"\s*(.+?)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*$", e["text"])
                add("LAB", e["start"], e["end"], "regex", e.get("confidence", 0.99),
                    value={"analyte": m.group(1).strip() if m else e["text"], "value": float(m.group(2)) if m else None, "unit": None},
                    normalized={"system": None, "id": None, "name": None, "method": None, "confidence": None, "status": "unmapped"})
                covered.append((e["start"], e["end"]))
            elif e["label"] == "FAMILY_HISTORY" and e["text"].lower() in ("consanguineous", "first cousin", "first-cousin", "family history", "cousin marriage"):
                add("FAMILY_RELATION", e["start"], e["end"], "regex", 0.9, value={"term": e["text"].lower()})

        # --- relation words
        for m in _REL_RE.finditer(text):
            add("FAMILY_RELATION", m.start(), m.end(), "lexicon", 0.95, normalized={"system": "Genomera pedigree relation", "id": _RELATIONS[m.group(1).lower()],
                "name": _RELATIONS[m.group(1).lower()], "method": "exact", "confidence": 0.95, "status": "normalized"})

        # --- diseases (graph names/synonyms)
        taken: List[Tuple[int, int]] = []
        for d in self._diseases:
            for s, e in self._word_spans(text, d["phrase"]):
                if any(s < b and a < e for a, b in taken):
                    continue
                taken.append((s, e))
                add("DISEASE", s, e, "knowledge_graph", 0.95, normalized={"system": "Orphanet", "id": d["id"], "name": d["name"], "method": "exact_name",
                                                                         "confidence": 0.95, "status": "normalized"})
        # --- genes: only uppercase symbols present in the graph, so ordinary words are never read as genes
        for m in re.finditer(r"\b[A-Z][A-Z0-9]{1,9}\b", text):
            if m.group(0) in self._gene_ids:
                add("GENE", m.start(), m.end(), "knowledge_graph", 0.97, normalized={"system": "Genomera gene list", "id": m.group(0), "name": m.group(0),
                    "method": "exact_symbol", "confidence": 0.97, "status": "normalized"})
        # --- variants: HGVS and rsID; linked to a gene only when exactly one known gene is named in the same sentence
        for rx, kind in ((EN.HGVS_C, "hgvs_c"), (EN.HGVS_P, "hgvs_p"), (EN.RSID, "rsid")):
            for m in rx.finditer(text):
                sent = self._sent_of(sents, m.start())
                genes = {g["text"] for g in ents if g["label"] == "GENE" and sent[0] <= g["start"] < sent[1]}
                gene = next(iter(genes)) if len(genes) == 1 else None
                add("VARIANT", m.start(), m.end(), "regex", 0.99, value={"kind": kind, "gene": gene,
                    "gene_link": "unambiguous (one gene in the sentence)" if gene else ("ambiguous (multiple genes in the sentence)" if len(genes) > 1 else "no gene in the sentence")},
                    normalized={"system": "HGVS" if kind != "rsid" else "dbSNP", "id": m.group(0).lower() if kind == "rsid" else m.group(0), "name": m.group(0),
                                "method": "pattern", "confidence": 0.99, "status": "normalized"})

        # --- severity words: attach to the closest phenotype within the sentence (<= 3 words after)
        for m in re.finditer(r"\b(" + "|".join(_SEVERITY) + r")\b", text, re.I):
            sent = self._sent_of(sents, m.start())
            follow = [p for p in ents if p["label"] == "PHENOTYPE" and p["start"] >= m.end() and p["start"] < sent[1]
                      and len(text[m.end():p["start"]].split()) <= 3]
            tgt = min(follow, key=lambda p: p["start"]) if follow else None
            sev = add("SEVERITY", m.start(), m.end(), "lexicon", 0.9, value={"severity": _SEVERITY[m.group(1).lower()],
                      "attached_to": tgt["text"] if tgt else None})
            if tgt:
                tgt["severity"] = _SEVERITY[m.group(1).lower()]

        # --- assertion / experiencer for clinical concepts
        for e in ents:
            if e["label"] in ("PHENOTYPE", "DISEASE", "DRUG"):
                sent = self._sent_of(sents, e["start"])
                e.update(assess_context(text, e["start"], e["end"], sent))
        # --- onset attaches to the nearest preceding/following phenotype in the same sentence (<= 6 words)
        for o in [x for x in ents if x["label"] == "ONSET"]:
            sent = self._sent_of(sents, o["start"])
            cands = [p for p in ents if p["label"] == "PHENOTYPE" and sent[0] <= p["start"] < sent[1]]
            if cands:
                def gap(p):
                    return abs(p["start"] - o["end"]) if p["start"] >= o["end"] else abs(o["start"] - p["end"])
                tgt = min(cands, key=gap)
                if len(text[min(tgt["end"], o["end"]):max(tgt["start"], o["start"])].split()) <= 6:
                    tgt["onset"] = o["value"]
                    o["attached_to"] = tgt["text"]

        # drop overlapping duplicates (keep the longest span within the same label), then order
        ents.sort(key=lambda x: (x["start"], -(x["end"] - x["start"])))
        out: List[dict] = []
        for e in ents:
            if any(o["label"] == e["label"] and e["start"] < o["end"] and o["start"] < e["end"] for o in out):
                continue
            out.append(e)
        for i, e in enumerate(out):
            e["id"] = f"e{i + 1}"
        return self._summarise(text, out, base)

    def _summarise(self, text: str, ents: List[dict], base: dict) -> dict:
        def pheno(pred):
            seen, res = set(), []
            for e in ents:
                n = e.get("normalized") or {}
                if e["label"] == "PHENOTYPE" and e["experiencer"] == "patient" and pred(e) and n.get("id") and n["id"] not in seen:
                    seen.add(n["id"])
                    res.append({"hpo_id": n["id"], "name": n["name"], "text": e["text"], "assertion": e["assertion"], "status": n["status"],
                                "confidence": n["confidence"], "onset": e.get("onset"), "severity": e.get("severity")})
            return res
        present = pheno(lambda e: e["assertion"] in ("present", "historical"))
        absent = pheno(lambda e: e["assertion"] == "absent")
        possible = pheno(lambda e: e["assertion"] == "possible")
        family = []
        for e in ents:
            if e["label"] in ("PHENOTYPE", "DISEASE") and e["experiencer"] == "family":
                n = e.get("normalized") or {}
                family.append({"relation": e["family_relation"], "label": e["label"], "text": e["text"], "assertion": e["assertion"],
                               "concept_id": n.get("id"), "concept_name": n.get("name")})
        conflicts = [{"hpo_id": p["hpo_id"], "name": p["name"], "detail": "documented both as present and as absent in this text"}
                     for p in absent if p["hpo_id"] in {x["hpo_id"] for x in present}]
        unmapped = [e["text"] for e in ents if e["label"] == "PHENOTYPE" and (e["normalized"] or {}).get("status") == "unmapped"]
        needs_review = [e["text"] for e in ents if (e.get("normalized") or {}).get("status") == "needs_review"]
        counts: Dict[str, int] = {}
        for e in ents:
            counts[e["label"]] = counts.get(e["label"], 0) + 1
        return {
            "text": text, "entities": ents, "counts": counts,
            "summary": {"present_phenotypes": present, "absent_phenotypes": absent, "possible_phenotypes": possible,
                        "family_findings": family, "conflicts": conflicts, "unmapped_phenotypes": unmapped, "needs_review": needs_review,
                        "hpo_ids_present": [p["hpo_id"] for p in present], "hpo_ids_absent": [p["hpo_id"] for p in absent],
                        "ages": [e["text"] for e in ents if e["label"] == "AGE"]},
            "engine": {"ner": type(self.registry.ner).__name__, "assertion": "rule-based (sentence-scoped cues)", "hpo": "existing HPOMapper / NER dictionary",
                       "unsupported_labels": UNSUPPORTED_LABELS},
            "is_code_mixed": base.get("is_code_mixed", False), "lid_counts": base.get("lid_counts", {}),
            "disclaimer": "Automated extraction for clinician review; it can miss or misread text. Nothing is written to a case without confirmation.",
        }


    # ---------------------------- assistant grounding ----------------------------
    def ai_context(self, text: str) -> dict:
        r = self.analyze(text[:MAX_TEXT])
        sm = r["summary"]

        def names(items):
            return "; ".join(f'{p["name"]} ({p["hpo_id"]})' for p in items) or "none"
        lines = ["CLINICAL TEXT ANALYSIS (automated, rule-based extraction of the clinician-provided note; verify against the note):",
                 f"- Present/historical phenotypes: {names(sm['present_phenotypes'])}",
                 f"- Explicitly absent (negated): {names(sm['absent_phenotypes'])}",
                 f"- Possible/uncertain: {names(sm['possible_phenotypes'])}"]
        for f in sm["family_findings"]:
            lines.append(f"- Family ({f['relation']}): {f['concept_name'] or f['text']} [{f['assertion']}]")
        if sm["conflicts"]:
            lines.append("- Conflicts: " + "; ".join(c["name"] + " documented as both present and absent" for c in sm["conflicts"]))
        if sm["unmapped_phenotypes"]:
            lines.append("- Phenotype wording not mapped to HPO: " + ", ".join(sm["unmapped_phenotypes"]))
        lines.append("Anything not listed was not extracted; do not assume it is absent.")
        return {"text": "\n".join(lines),
                "citations": [{"source_type": "clinical_text_nlp", "identifier": "note", "title": "Clinical text analysis",
                               "summary": f"{len(sm['present_phenotypes'])} present, {len(sm['absent_phenotypes'])} absent, {len(sm['possible_phenotypes'])} possible",
                               "reliability": "automated extraction"}],
                "summary": {"nlp": {"present": len(sm["present_phenotypes"]), "absent": len(sm["absent_phenotypes"]),
                                    "possible": len(sm["possible_phenotypes"]), "family": len(sm["family_findings"])}}}
