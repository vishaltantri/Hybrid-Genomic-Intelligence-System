"""Phase 8: Diagnosis Intelligence — presentation/integration layer over the existing engine.

The ranking is never recomputed or re-weighted here. Every number comes from `DifferentialDiagnosisEngine`
(Resnik/Phenomizer similarity x relative Indian population prior), the Twin's genomic-support annotation, or a real
engine re-run (what-if via the Twin scenario engine, discriminating-phenotype probes via `diagnose`).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from backend.app import store
from ml_services.graph_ai import gnn_diagnosis as gd
from ml_services.phenotype.service import assertion_state, NOT_DOCUMENTED
from ml_services.twin import twin_state as ts

DISCLAIMER = "Clinical Decision Support. Computational ranking for clinician review; it is not a diagnosis."
PROBE_LIMIT = 10


class DiagnosisIntelError(ValueError):
    pass


class DiagnosisIntelligence:
    def __init__(self, registry):
        self.registry = registry

    # ------------------------------ shared ------------------------------
    def _name(self, hid: str) -> str:
        return (self.registry.graph.node("Hpo", hid) or {}).get("name", hid)

    def _state(self, patient_id: str, top_k: int = 8):
        core = self.registry.twin.load_core(patient_id)
        dx = ts.evaluate_diagnosis_state(self.registry.diagnosis, self.registry.graph, core["hpo_ids"], core["context"],
                                         core["variants"], top_k=top_k, explain=True,
                                         _cache=self.registry.twin.engine._dx_cache)
        return core, dx

    def _evidence_quality(self, case_id: str, variant_ids: List[str], genes: List[str]) -> dict:
        items = store.evidence_list(case_id)
        linked = [e for e in items if e.get("variant_id") in set(variant_ids)]
        if not linked:
            label = "Insufficient evidence" if variant_ids else "No matching record"
            return {"label": label, "saved_items": 0, "note": "No saved literature/database evidence is linked to this disease's variants."}
        return {"label": "Evidence saved", "saved_items": len(linked), "in_report": sum(1 for e in linked if e["in_report"]),
                "note": "Counts of saved items only; Genomera does not grade or score literature."}

    # ------------------------------ workspace ------------------------------
    def workspace(self, patient_id: str) -> dict:
        core, dx = self._state(patient_id)
        patient, events = core["patient"], core["events"]
        st = assertion_state(events)
        members = store.ped_list_members(patient_id)
        evidence = store.evidence_list(patient_id)
        summary = {"patient_id": patient_id, "age": patient.get("age"), "sex": patient.get("sex"),
                   "state": patient.get("state") or NOT_DOCUMENTED, "community": patient.get("community") or NOT_DOCUMENTED,
                   "phenotypes": len(core["hpo_ids"]), "explicitly_absent": sum(1 for s in st.values() if s["assertion"] == "absent"),
                   "uncertain": sum(1 for s in st.values() if s["assertion"] == "possible"),
                   "variants": len(core["variants"]) if core["analysis"] else None,
                   "variant_note": None if core["analysis"] else "Not analyzed: no variant analysis linked to this case.",
                   "pedigree_members": len(members), "pedigree_note": None if members else "No pedigree recorded.",
                   "saved_evidence": len(evidence)}
        if not dx["available"]:
            return {"patient_id": patient_id, "summary": summary, "available": False, "differential": [], "top_diagnosis": None,
                    "note": dx["note"], "disclaimer": DISCLAIMER}
        vmap = {v["variant_id"]: v for v in core["variants"]}
        rows = []
        for d in dx["differential"]:
            vids = d["genomic_support"]["variant_ids"]
            rows.append({
                "rank": d["rank"], "disease_id": d["disease_id"], "disease_name": d["disease_name"], "probability": d["probability"],
                "phenotype_similarity": d["phenotype_similarity"], "inheritance": d["inheritance"], "genes": d["genes"],
                "supporting_phenotypes": [{"hpo_id": s["patient_term"], "name": self._name(s["patient_term"]), "weight_pct": s["weight_pct"]}
                                          for s in d["driving_symptoms"] if s["similarity"] > 0],
                "missing_findings": [{"hpo_id": m["hpo_id"], "name": m["hpo_name"], "status": NOT_DOCUMENTED if m["hpo_id"] not in st else st[m["hpo_id"]]["assertion"]}
                                     for m in d["missing_findings"]],
                "variants": [{"variant_id": v, "gene_symbol": vmap[v].get("gene_symbol"), "hgvs": vmap[v].get("hgvs"),
                              "acmg_classification": vmap[v].get("acmg_classification")} for v in vids if v in vmap],
                "genomic_support": d["genomic_support"],
                "evidence_quality": self._evidence_quality(patient_id, vids, d["genes"]),
                "confirmatory_tests": d.get("confirmatory_tests"),
            })
        return {"patient_id": patient_id, "summary": summary, "available": True, "top_diagnosis": rows[0], "differential": rows,
                "ranking_basis": dx["ranking_basis"], "engine": dx["engine"], "disclaimer": DISCLAIMER}

    # ------------------------------ why ranked ------------------------------
    def why(self, patient_id: str, disease_id: str) -> dict:
        core, dx = self._state(patient_id, top_k=10)
        if not dx["available"]:
            raise DiagnosisIntelError(dx["note"])
        diff = {d["disease_id"]: d for d in dx["differential"]}
        if disease_id not in diff:
            raise LookupError(f"Disease '{disease_id}' is not in this case's ranked differential")
        d = diff[disease_id]
        pp = d.get("population_prior") or {}
        top = dx["differential"][0]
        sims = [x["phenotype_similarity"] for x in dx["differential"]]
        max_sim = max(sims)
        gated = d["phenotype_similarity"] >= 0.80 * max_sim
        lines = [f"Phenotype similarity (Resnik/Phenomizer information content) is {d['phenotype_similarity']} "
                 f"against a best of {max_sim} in this differential."]
        if gated:
            lines.append(f"It is within 80% of the best similarity, so the Indian population prior is applied "
                         f"(exposure {gd.BETA_PRIOR}); relative prior weight {pp.get('relative_weight')}.")
        else:
            lines.append("It is below 80% of the best similarity, so the Indian population prior has only a minimal effect on its rank.")
        notes = pp.get("india_notes") or []
        if notes:
            lines.append("Population factors recorded: " + "; ".join(notes) + ".")
        if d["rank"] > 1:
            lines.append(f"Compared with {top['disease_name']}: similarity {top['phenotype_similarity']} vs {d['phenotype_similarity']}, "
                         f"probability {top['probability']} vs {d['probability']}.")
        lines.append("Variants do not change this ranking; they are shown as separate genomic support: "
                     f"{d['genomic_support']['pathogenic_or_likely']} pathogenic/likely pathogenic and {d['genomic_support']['vus']} VUS "
                     "matching this disease." if core["analysis"] else "No variant analysis is linked, so there is no genomic support to show (Not analyzed).")
        factors = {"phenotype_similarity": d["phenotype_similarity"], "probability": d["probability"], "rank": d["rank"],
                   "prevalence_per_100k": pp.get("prevalence_per_100k"), "consanguinity_multiplier": pp.get("consanguinity_multiplier"),
                   "founder_multiplier": pp.get("founder_multiplier"), "sex_multiplier": pp.get("sex_multiplier"),
                   "relative_prior_weight": pp.get("relative_weight"), "prior_applied": pp.get("prior_applied_to_ranking"),
                   "similarity_gate": 0.80, "prior_exposure": gd.BETA_PRIOR, "noise_floor": gd.NOISE}
        return {"patient_id": patient_id, "disease_id": disease_id, "disease_name": d["disease_name"], "rank": d["rank"],
                "explanation": lines, "factors": factors,
                "supporting_symptoms": [{**s, "patient_term_name": self._name(s["patient_term"]),
                                         "disease_term_name": self._name(s["matched_disease_term"])} for s in d["driving_symptoms"]],
                "missing_findings": [{"hpo_id": m["hpo_id"], "name": m["hpo_name"], "status": NOT_DOCUMENTED} for m in d["missing_findings"]],
                "disclaimer": DISCLAIMER}

    # ------------------------------ matrix ------------------------------
    def matrix(self, patient_id: str) -> dict:
        core, dx = self._state(patient_id, top_k=6)
        if not dx["available"]:
            return {"patient_id": patient_id, "available": False, "note": dx["note"], "columns": [], "rows": []}
        st = assertion_state(core["events"])
        cols = [{"hpo_id": h, "name": self._name(h)} for h in core["hpo_ids"]]
        rows = []
        for d in dx["differential"]:
            attrib = {a["patient_term"]: a for a in self.registry.diagnosis.attribute_symptoms(core["hpo_ids"], d["disease_id"], top_n=len(core["hpo_ids"]))}
            dterms = {e["dst"] for e in self.registry.graph.edges if e["type"] == "HAS_PHENOTYPE" and e["src"] == d["disease_id"]}
            cells = []
            for c in cols:
                a = attrib.get(c["hpo_id"])
                cells.append({"hpo_id": c["hpo_id"], "similarity": a["similarity"] if a else 0.0, "matched": bool(a and a["similarity"] > 0),
                              "disease_term": a["matched_disease_term"] if a and a["similarity"] > 0 else None})
            absent = [{"hpo_id": t, "name": self._name(t)} for t in dterms if st.get(t, {}).get("assertion") == "absent"]
            rows.append({"rank": d["rank"], "disease_id": d["disease_id"], "disease_name": d["disease_name"], "probability": d["probability"],
                         "cells": cells, "explicitly_absent": absent})
        return {"patient_id": patient_id, "available": True, "columns": cols, "rows": rows,
                "legend": "Cell value is the engine's term similarity; 0 means no matching disease term, not absence of the finding."}

    # ------------------------------ discriminating phenotypes ------------------------------
    def discriminating(self, patient_id: str) -> dict:
        """Real engine probes: add each candidate finding and see whether the top diagnosis changes."""
        core, dx = self._state(patient_id, top_k=5)
        if not dx["available"]:
            raise DiagnosisIntelError(dx["note"])
        st = assertion_state(core["events"])
        cands: List[str] = []
        for d in dx["differential"][:3]:
            for m in self.registry.diagnosis.missing_terms(core["hpo_ids"], d["disease_id"], 6):
                if m["hpo_id"] not in cands and m["hpo_id"] not in core["hpo_ids"] and m["hpo_id"] not in st:
                    cands.append(m["hpo_id"])
        base_top = dx["top_diagnosis"]
        out = []
        for h in cands[:PROBE_LIMIT]:
            r = self.registry.diagnosis.diagnose(sorted(core["hpo_ids"] + [h]), core["context"], top_k=3, explain=False, uncertainty=False)["results"]
            new_top = r[0] if r else None
            out.append({"hpo_id": h, "name": self._name(h), "status": NOT_DOCUMENTED,
                        "top_after": new_top["disease_name"] if new_top else None,
                        "top_probability_after": new_top["probability"] if new_top else None,
                        "changes_top_diagnosis": bool(new_top and new_top["disease_id"] != base_top["disease_id"]),
                        "top_probability_change": round(new_top["probability"] - base_top["probability"], 4) if new_top and new_top["disease_id"] == base_top["disease_id"] else None})
        out.sort(key=lambda x: (not x["changes_top_diagnosis"], -abs(x["top_probability_change"] or 0)))
        return {"patient_id": patient_id, "current_top": base_top["disease_name"], "current_probability": base_top["probability"], "probes": out,
                "note": "Each row is a real re-run of the diagnosis engine as if the finding were present. Confirm the finding clinically before recording it.",
                "disclaimer": DISCLAIMER}

    # ------------------------------ what-if ------------------------------
    def whatif(self, patient_id: str, user: str, spec: dict) -> dict:
        from ml_services.twin.scenario_engine import ScenarioError
        try:
            res = self.registry.twin.create_scenario(patient_id, user, spec)
        except ScenarioError as ex:
            raise DiagnosisIntelError(str(ex))
        slim = lambda b: {"top_diagnosis": (b.get("top_diagnosis") or {}).get("disease_name"),
                          "differential": [{"rank": d["rank"], "disease_id": d["disease_id"], "disease_name": d["disease_name"], "probability": d["probability"]}
                                           for d in b.get("differential", [])[:5]]}
        return {"patient_id": patient_id, "scenario_id": res["scenario_id"], "type_label": res["type_label"],
                "baseline": slim(res["baseline"]), "scenario": slim(res["scenario"]),
                "top_diagnosis_changed": res["diff"]["top_diagnosis_changed"], "disease_changes": res["diff"]["disease_changes"],
                "explanation": res["explanation"], "limitations": res["limitations"],
                "note": "Saved to the Digital Twin scenario list; the case record itself is not modified.", "disclaimer": DISCLAIMER}

    # ------------------------------ assistant context ------------------------------
    def ai_context(self, patient_id: str) -> dict:
        w = self.workspace(patient_id)
        if not w["available"]:
            return {"text": f"Diagnosis Intelligence: {w['note']}", "citations": []}
        lines = [f"Diagnosis Intelligence for {patient_id} (Clinical Decision Support; engine = {w['engine']}):"]
        for d in w["differential"][:5]:
            lines.append(f"#{d['rank']} {d['disease_name']} p={d['probability']} sim={d['phenotype_similarity']}; supporting: "
                         f"{', '.join(s['name'] for s in d['supporting_phenotypes']) or 'none'}; not documented: "
                         f"{', '.join(m['name'] for m in d['missing_findings'] if m['status'] == NOT_DOCUMENTED) or 'none'}; "
                         f"variants: {len(d['variants'])}; evidence: {d['evidence_quality']['label']}")
        return {"text": "\n".join(lines), "citations": [{"source_type": "diagnosis_intelligence", "identifier": patient_id,
                                                           "title": "Diagnosis Intelligence workspace", "summary": "Differential, supporting and missing findings, genomic support and saved-evidence counts for this case.",
                                                           "reliability": "Computational Inference"}]}
