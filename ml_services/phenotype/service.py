"""Phase 7: phenotype / HPO intelligence. Presentation + integration layer over existing components.

Nothing here invents scores: lexical matches are labelled by match type, semantic matches carry the HPO mapper's own
score and source, similarity and "why" come from the existing Resnik/Phenomizer engine. Findings the case does not
mention are "Not documented"; a contradiction exists only where the record explicitly negates a term.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from backend.app import store

ASSERTIONS = ("present", "absent", "possible")
NOT_DOCUMENTED = "Not documented"
MAX_Q = 200


class PhenotypeError(ValueError):
    pass


def assertion_state(events: List[dict]) -> Dict[str, dict]:
    """Latest explicit assertion per HPO term (chronological; an hpo_profile item counts as 'present')."""
    state: Dict[str, dict] = {}
    for ev in sorted(events, key=lambda e: e.get("created_utc") or ""):
        p = ev.get("payload") or {}
        if ev["kind"] == "hpo_profile":
            items = [(it, "present") for it in p.get("hpo_profile", [])]
        elif ev["kind"] == "phenotype_assertions":
            items = [(it, it["assertion"]) for it in p.get("assertions", [])]
        else:
            continue
        for it, asr in items:
            state[it["hpo_id"]] = {"assertion": asr, "event_id": ev["event_id"], "timestamp": ev["created_utc"],
                                   "evidence_text": it.get("evidence_text"), "onset": it.get("onset"),
                                   "severity": it.get("severity"), "method": it.get("method"), "confidence": it.get("confidence")}
    return state


class PhenotypeIntelligence:
    def __init__(self, registry):
        self.registry = registry
        self.g = registry.graph
        self._syn: Optional[Dict[str, List[dict]]] = None

    # ------------------------------ helpers ------------------------------
    def _hpo(self, hpo_id: str) -> Optional[dict]:
        return self.g.node("Hpo", hpo_id)

    def _name(self, hpo_id: str) -> str:
        return (self._hpo(hpo_id) or {}).get("name", hpo_id)

    def _synonyms(self) -> Dict[str, List[dict]]:
        if self._syn is None:
            self._syn = {}
            for e in self.g.edges:
                if e["type"] == "MAPS_TO" and e.get("src_type") == "IndianSynonym":
                    n = self.g.node("IndianSynonym", e["src"]) or {}
                    self._syn.setdefault(e["dst"], []).append({"text": e["src"], "language": n.get("language")})
        return self._syn

    def _edges(self, etype: str, **kw) -> List[dict]:
        return [e for e in self.g.edges if e["type"] == etype and all(e.get(k) == v for k, v in kw.items())]

    # ------------------------------ search ------------------------------
    def search(self, q: str, limit: int = 15) -> dict:
        q = (q or "").strip()
        if len(q) < 2:
            raise PhenotypeError("Enter at least 2 characters.")
        if len(q) > MAX_Q:
            raise PhenotypeError("Query is too long.")
        ql = q.lower()
        hits: Dict[str, dict] = {}
        ranks = {"id": 0, "name": 1, "synonym": 2, "indian_synonym": 3, "semantic": 4}

        def add(hid, match, **extra):
            n = self._hpo(hid)
            if not n:
                return
            cur = hits.get(hid)
            if cur is None or ranks[match] < cur["_rank"]:
                hits[hid] = {"hpo_id": hid, "name": n.get("name"), "match": match, "_rank": ranks[match], **extra}

        for n in self.g.by_type("Hpo"):
            name, hid = (n.get("name") or ""), n["id"]
            if ql in hid.lower():
                add(hid, "id")
            elif ql in name.lower():
                add(hid, "name", matched_text=name)
            else:
                for s in n.get("synonyms", []) or []:
                    if ql in s.lower():
                        add(hid, "synonym", matched_text=s)
                        break
        for hid, syns in self._synonyms().items():
            for s in syns:
                if ql in s["text"].lower():
                    add(hid, "indian_synonym", matched_text=s["text"], language=s["language"])
                    break
        semantic_note = None
        try:
            for m in self.registry.hpo_mapper.map_phrase(q, top_k=5, threshold=0.0):
                if m["hpo_id"] not in hits:
                    add(m["hpo_id"], "semantic", score=m["score"], source=m.get("source"), matched_text=m.get("matched_text"))
        except Exception:
            semantic_note = "Semantic mapping is unavailable."
        res = sorted(hits.values(), key=lambda h: (h["_rank"], -(h.get("score") or 0), h["name"] or ""))[:limit]
        for r in res:
            r.pop("_rank", None)
        return {"query": q, "results": res, "semantic_note": semantic_note,
                "note": "Semantic matches carry the HPO mapper's own score; lexical matches are labelled by match type." if res else "No matching HPO term."}

    # ------------------------------ term ------------------------------
    def term(self, hpo_id: str, patient_id: Optional[str] = None) -> dict:
        n = self._hpo(hpo_id)
        if not n:
            raise LookupError(f"HPO term '{hpo_id}' is not in the knowledge graph")
        parents = [e["dst"] for e in self._edges("IS_A", src=hpo_id)]
        children = [e["src"] for e in self._edges("IS_A", dst=hpo_id)]
        anc, stack = [], list(parents)
        while stack:
            c = stack.pop()
            if c not in anc:
                anc.append(c)
                stack += [e["dst"] for e in self._edges("IS_A", src=c)]
        diseases = []
        for e in self._edges("HAS_PHENOTYPE", dst=hpo_id):
            d = self.g.node("Disease", e["src"]) or {}
            genes = [x["src"] for x in self._edges("ASSOCIATED_WITH", dst=e["src"])]
            diseases.append({"disease_id": e["src"], "disease_name": d.get("name", e["src"]), "genes": genes,
                             "frequency": (e.get("attrs") or {}).get("frequency")})
        out = {"hpo_id": hpo_id, "name": n.get("name"), "definition": n.get("definition"), "synonyms": n.get("synonyms", []),
               "indian_synonyms": self._synonyms().get(hpo_id, []),
               "parents": [{"hpo_id": p, "name": self._name(p)} for p in parents],
               "children": [{"hpo_id": c, "name": self._name(c)} for c in children],
               "ancestors": [{"hpo_id": a, "name": self._name(a)} for a in anc],
               "organ_systems": self.registry.twin.ontology.organ_systems(hpo_id),
               "diseases": diseases, "case_variants": [], "variant_note": None}
        if patient_id:
            genes = {g for d in diseases for g in d["genes"]}
            core = self.registry.twin.load_core(patient_id)
            out["case_variants"] = [self._variant(v) for v in core["variants"] if v.get("gene_symbol") in genes]
            out["variant_note"] = None if core["variants"] else "Not analyzed: no variant analysis is linked to this case."
        return out

    @staticmethod
    def _variant(v: dict) -> dict:
        return {"variant_id": v.get("variant_id"), "gene_symbol": v.get("gene_symbol"), "hgvs": v.get("hgvs"),
                "acmg_classification": v.get("acmg_classification")}

    # ------------------------------ case ------------------------------
    def _top(self, core: dict, k: int = 5) -> List[dict]:
        if not core["hpo_ids"]:
            return []
        return self.registry.diagnosis.diagnose(core["hpo_ids"], core["context"], top_k=k, explain=False, uncertainty=False)["results"]

    def case(self, patient_id: str) -> dict:
        core = self.registry.twin.load_core(patient_id)
        st = assertion_state(core["events"])
        ont = self.registry.twin.ontology

        def row(hid, rec=None):
            s = st.get(hid, {})
            return {"hpo_id": hid, "name": ont.name(hid) or hid, "in_knowledge_graph": ont.known(hid),
                    "organ_systems": ont.organ_systems(hid) if ont.known(hid) else [],
                    "onset": s.get("onset") or NOT_DOCUMENTED, "severity": s.get("severity") or NOT_DOCUMENTED,
                    "evidence_text": s.get("evidence_text"), "documented": s.get("timestamp"),
                    "sources": [x.get("label") for x in (rec or {}).get("sources", [])]}

        observed = [row(h, r) for h, r in core["phenotype_records"].items()]
        negated = [row(h) for h, s in st.items() if s["assertion"] == "absent"]
        uncertain = [row(h) for h, s in st.items() if s["assertion"] == "possible"]
        top = self._top(core, 3)
        undocumented = []
        if top:
            for m in self.registry.diagnosis.missing_terms(core["hpo_ids"], top[0]["disease_id"], 12):
                if m["hpo_id"] not in st:
                    undocumented.append({"hpo_id": m["hpo_id"], "name": m.get("hpo_name"), "status": NOT_DOCUMENTED,
                                         "for_disease": top[0]["disease_name"]})
        # a contradiction exists only when the latest explicit assertion is 'absent' yet the term is still computed from another source
        conflicts = [{"hpo_id": h, "name": ont.name(h) or h, "note": "Marked absent but still present in another record."}
                     for h in core["phenotype_records"] if st.get(h, {}).get("assertion") == "absent"]
        return {"patient_id": patient_id, "observed": observed, "negated": negated, "uncertain": uncertain,
                "not_documented": undocumented, "conflicts": conflicts,
                "unknown_ids": [r["hpo_id"] for r in observed if not r["in_knowledge_graph"]],
                "top_diagnoses": [{"disease_id": d["disease_id"], "disease_name": d["disease_name"], "probability": d["probability"],
                                   "phenotype_similarity": d["phenotype_similarity"]} for d in top],
                "diagnosis_note": None if top else "Insufficient evidence: add at least one HPO term to rank diagnoses.",
                "note": "Uncertain and negated findings are not fed to the diagnosis engine."}

    # ------------------------------ compare ------------------------------
    def compare(self, patient_id: str, disease_id: str) -> dict:
        core = self.registry.twin.load_core(patient_id)
        d = self.g.node("Disease", disease_id)
        if not d:
            raise LookupError(f"Disease '{disease_id}' is not in the knowledge graph")
        st = assertion_state(core["events"])
        dterms = [e["dst"] for e in self._edges("HAS_PHENOTYPE", src=disease_id)]
        obs = set(core["hpo_ids"])
        eng = self.registry.diagnosis
        attrib = eng.attribute_symptoms(sorted(obs), disease_id) if obs else []
        score = None
        if obs:
            for r in eng.diagnose(sorted(obs), core["context"], top_k=50, explain=False, uncertainty=False)["results"]:
                if r["disease_id"] == disease_id:
                    score = {"probability": r["probability"], "phenotype_similarity": r["phenotype_similarity"]}
        covered = {a["matched_disease_term"] for a in attrib}
        genes = [x["src"] for x in self._edges("ASSOCIATED_WITH", dst=disease_id)]
        return {"patient_id": patient_id, "disease_id": disease_id, "disease_name": d.get("name"), "score": score,
                "score_note": None if score else "No matching record: the disease is outside the engine's ranked results for this profile.",
                "matched": [{"patient_term": a["patient_term"], "patient_term_name": self._name(a["patient_term"]),
                             "disease_term": a["matched_disease_term"], "disease_term_name": self._name(a["matched_disease_term"]),
                             "similarity": a["similarity"], "weight_pct": a.get("weight_pct")} for a in attrib],
                "unmatched_patient_terms": [{"hpo_id": h, "name": self._name(h)} for h in sorted(obs) if h not in {a["patient_term"] for a in attrib}],
                "explicitly_absent": [{"hpo_id": t, "name": self._name(t)} for t in dterms if st.get(t, {}).get("assertion") == "absent"],
                "not_documented": [{"hpo_id": t, "name": self._name(t), "status": NOT_DOCUMENTED} for t in dterms
                                   if t not in obs and t not in covered and t not in st],
                "genes": genes,
                "case_variants": [self._variant(v) for v in core["variants"] if v.get("gene_symbol") in genes],
                "variant_note": None if core["variants"] else "Not analyzed: no variant analysis is linked to this case.",
                "note": "Scores come from the existing Resnik/Phenomizer engine; this view does not re-weight them."}

    # ------------------------------ import ------------------------------
    def import_confirm(self, patient_id: str, user: str, accepted: List[dict]) -> dict:
        if not store.get_patient(patient_id):
            raise LookupError(f"Patient '{patient_id}' not found")
        if not accepted:
            raise PhenotypeError("Nothing was selected to import.")
        present, other = [], []
        for a in accepted:
            hid, asr = a.get("hpo_id"), a.get("assertion")
            if asr not in ASSERTIONS:
                raise PhenotypeError(f"Invalid assertion '{asr}'.")
            if not self._hpo(hid):
                raise PhenotypeError(f"HPO term '{hid}' is not in the knowledge graph.")
            item = {"hpo_id": hid, "name": self._name(hid), "evidence_text": (a.get("evidence_text") or "")[:300] or None,
                    "onset": a.get("onset"), "severity": a.get("severity"), "method": "clinician_confirmed_import",
                    "confidence": a.get("confidence")}
            (present if asr == "present" else other).append(item if asr == "present" else {**item, "assertion": asr})
        ev = []
        if present:
            ev.append(store.add_event(patient_id, "hpo_profile", {"hpo_profile": present, "confirmed_by": user})["event_id"])
        if other:
            ev.append(store.add_event(patient_id, "phenotype_assertions", {"assertions": other, "confirmed_by": user})["event_id"])
        store.audit(user, "phenotype_import", patient_id, f"present={len(present)} other={len(other)}")
        return {"patient_id": patient_id, "events": ev, "present": len(present), "negated_or_uncertain": len(other)}
