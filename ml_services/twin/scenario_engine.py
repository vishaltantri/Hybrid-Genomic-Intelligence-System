"""What-if scenario engine for the Digital Twin (Phase 3D).

Flow:   baseline twin inputs  ->  one explicit modification  ->  recompute the affected
modules with the EXISTING engines  ->  compare against the recomputed baseline.

Both sides of every comparison are produced by the same code path (`_evaluate`), so any
difference is attributable to the modification alone. Nothing is estimated with ad-hoc
percentages. Scenarios the platform cannot model are rejected with an explicit limitation.

Supported scenarios
    variant_exclusion         drop variants from the analysis; recompute counts, ranking, genomic support
    variant_reclassification  hypothetical ACMG class; recompute composite priority + genomic support
    phenotype_remove / _add   change the HPO set; re-run the diagnosis engine and phenotype scoring
    diagnosis_focus           compare a chosen working diagnosis against the current top diagnosis
    medication                run the PGx rule engine for a drug against genotypes present in the analysis

Not modelled (rejected): disease progression, treatment response, survival, lab values.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from ml_services.twin import twin_state as ts
from ml_services.variants.prioritizer import ACMG_POINTS, composite_score, tier_for_score

SCENARIO_TYPES = {
    "variant_exclusion": "Exclude variant(s)",
    "variant_reclassification": "Reclassify a variant (hypothetical ACMG class)",
    "phenotype_remove": "Remove phenotype(s)",
    "phenotype_add": "Add phenotype(s)",
    "diagnosis_focus": "Compare a different working diagnosis",
    "medication": "Introduce a medication (PGx rule screening)",
}

UNSUPPORTED = {
    "disease_progression": "Disease progression",
    "treatment_response": "Treatment response / clinical outcome",
    "survival": "Survival or prognosis probability",
    "lab_values": "Laboratory or physiological values",
}

DISCLAIMER = ("Computational decision-support simulation. It recomputes platform rules on hypothetical "
              "inputs; it is not a physiological measurement, a prediction of what will happen to a "
              "real patient, or a treatment recommendation.")


class ScenarioError(ValueError):
    """Raised when a scenario is invalid or cannot be modelled with the available data."""


class ScenarioEngine:
    def __init__(self, graph: Any, diagnosis_engine: Any, pgx_engine: Any, ontology: ts.HpoOntology):
        self.graph = graph
        self.dx = diagnosis_engine
        self.pgx = pgx_engine
        self.onto = ontology
        self._dx_cache: Dict[tuple, dict] = {}
        self._local = threading.local()   # per-request trace of the stages actually executed

    def _trace(self) -> list:
        if not hasattr(self._local, "trace"):
            self._local.trace = []
        return self._local.trace

    # ------------------------------ public ------------------------------

    def run(self, core: dict, spec: dict) -> dict:
        stype = spec.get("type")
        if stype in UNSUPPORTED:
            raise ScenarioError(f"{UNSUPPORTED[stype]}: this simulation is not available from the "
                                "current clinical data/model.")
        if stype not in SCENARIO_TYPES:
            raise ScenarioError(f"Unknown scenario type {stype!r}. Supported: {sorted(SCENARIO_TYPES)}")
        params = spec.get("params") or {}
        handler = getattr(self, f"_run_{stype}")
        self._local.trace = []
        t0 = time.perf_counter()
        result = handler(core, params)
        total_ms = (time.perf_counter() - t0) * 1000
        result["stages"] = self._stages(stype, params, result, total_ms)
        result["system_impact"] = self._system_impact(core, result)
        result.update({
            "scenario_id": f"SCN-{uuid.uuid4().hex[:8].upper()}",
            "type": stype,
            "type_label": SCENARIO_TYPES[stype],
            "name": (spec.get("name") or "").strip() or SCENARIO_TYPES[stype],
            "params": params,
            "disclaimer": DISCLAIMER,
        })
        return result

    # ------------------------------ evaluation ------------------------------

    def _variants_for(self, core: dict, hpos: List[str], exclude=(), reclass: Optional[dict] = None) -> List[dict]:
        out = []
        for v in core["variants"]:
            if v["variant_id"] in exclude:
                continue
            nv = dict(v)
            cls = (reclass or {}).get(v["variant_id"], v["acmg_classification"])
            nv["acmg_classification"] = cls
            nv["priority_score"] = composite_score(self.graph, v, hpos, cls)
            nv["priority_tier"] = tier_for_score(nv["priority_score"])
            out.append(nv)
        out.sort(key=lambda v: -v["priority_score"])  # stable: ties keep analysis order
        for i, v in enumerate(out):
            v["rank"] = i + 1
        return out

    def _evaluate(self, core: dict, hpos: List[str], exclude=(), reclass=None) -> dict:
        t0 = time.perf_counter()
        variants = self._variants_for(core, hpos, exclude, reclass)
        t1 = time.perf_counter()
        cache_before = len(self._dx_cache)
        dx = ts.evaluate_diagnosis_state(self.dx, self.graph, hpos, core["context"], variants,
                                         top_k=10, explain=False, _cache=self._dx_cache)
        t2 = time.perf_counter()
        self._trace().append({"genomic_ms": (t1 - t0) * 1000, "diagnosis_ms": (t2 - t1) * 1000,
                              "variants": len(variants), "phenotypes": len(hpos),
                              "diseases_ranked": len(dx["differential"]),
                              "reused_cached_ranking": len(self._dx_cache) == cache_before and dx["available"]})
        top = dx.get("top_diagnosis")
        counts = ts.count_classes(variants)
        return {
            "phenotype_count": len(hpos),
            "hpo_ids": sorted(hpos),
            "variant_counts": counts,
            "variant_ranking": [{"variant_id": v["variant_id"], "gene": v.get("gene_symbol"),
                                 "hgvs": v.get("cdna") or v.get("hgvs"), "rank": v["rank"],
                                 "priority_score": v["priority_score"],
                                 "classification": v["acmg_classification"],
                                 "tier": v["priority_tier"]} for v in variants],
            "top_variant": ({"variant_id": variants[0]["variant_id"], "gene": variants[0].get("gene_symbol"),
                             "priority_score": variants[0]["priority_score"]} if variants else None),
            "diagnosis_available": dx["available"],
            "top_diagnosis": ({
                "disease_id": top["disease_id"], "disease_name": top["disease_name"],
                "probability": top["probability"],
                "phenotype_similarity": top["phenotype_similarity"],
                "supporting_phenotypes": top["supporting_phenotype_count"],
                "relevant_variants": len(top["genomic_support"]["variant_ids"]),
                "genomic_priority": top["genomic_support"]["max_priority_score"],
            } if top else None),
            "differential": [{
                "rank": d["rank"], "disease_id": d["disease_id"], "disease_name": d["disease_name"],
                "probability": d["probability"], "phenotype_similarity": d["phenotype_similarity"],
                "supporting_phenotypes": d["supporting_phenotype_count"],
                "pathogenic_or_likely_variants": d["genomic_support"]["pathogenic_or_likely"],
                "vus_variants": d["genomic_support"]["vus"],
                "genomic_priority": d["genomic_support"]["max_priority_score"],
            } for d in dx["differential"]],
            "genomic_candidates": [{
                "disease_id": c["disease_id"], "disease_name": c["disease_name"],
                "phenotype_rank": c["phenotype_rank_in_differential"],
                "phenotype_similarity": c["phenotype_similarity"],
                "pathogenic_or_likely_variants": c["genomic_support"]["pathogenic_or_likely"],
                "vus_variants": c["genomic_support"]["vus"],
                "genomic_priority": c["genomic_support"]["max_priority_score"],
            } for c in dx["genomic_candidates"]],
        }

    # ------------------------------ stages / system impact ------------------------------

    def _stages(self, stype: str, params: dict, result: dict, total_ms: float) -> List[dict]:
        """The computation stages that actually ran, with server-measured durations (no progress faking)."""
        trace = self._trace()
        r = lambda x: round(x, 2)
        if len(trace) >= 2:                      # baseline + scenario evaluation
            g = sum(t["genomic_ms"] for t in trace)
            d = sum(t["diagnosis_ms"] for t in trace)
            sc = trace[-1]
            reused = all(t["reused_cached_ranking"] for t in trace[1:]) if sc["reused_cached_ranking"] else False
            phen = ("Diagnosis engine re-run on the modified phenotype set"
                    if not reused else "Ranking served from the engine cache (identical phenotype/context inputs already computed)")
            return [
                {"id": "apply", "label": "Applying scenario", "ms": None,
                 "detail": SCENARIO_TYPES[stype]},
                {"id": "genomic", "label": "Recomputing variant and genomic relevance", "ms": r(g),
                 "detail": f"{sc['variants']} variants re-scored (baseline and scenario), genomic support per disease"},
                {"id": "phenotype", "label": "Recomputing phenotype relevance and diagnosis", "ms": r(d),
                 "detail": f"{phen}; {sc['diseases_ranked']} diseases ranked from {sc['phenotypes']} phenotypes"},
                {"id": "compare", "label": "Comparing scenario Twin with baseline", "ms": r(max(total_ms - g - d, 0)),
                 "detail": f"{len(result.get('comparison', []))} measures compared"},
            ]
        return [
            {"id": "apply", "label": "Applying scenario", "ms": None, "detail": SCENARIO_TYPES[stype]},
            {"id": "compute", "label": "Recomputing with the platform engines", "ms": r(total_ms),
             "detail": "Diagnosis comparison" if stype == "diagnosis_focus" else "PGx rule screening"},
            {"id": "compare", "label": "Comparing scenario Twin with baseline", "ms": None,
             "detail": f"{len(result.get('comparison', []))} measures compared"},
        ]

    def _system_impact(self, core: dict, result: dict) -> List[dict]:
        """Body systems whose case-specific variant support changed (via gene -> KG disease -> phenotype system)."""
        from ml_services.twin.anatomy import build_anatomy

        def systems_for(variant_rows: List[dict]) -> Dict[str, List[str]]:
            by_id = {v["variant_id"]: v for v in core["variants"]}
            vs = []
            for row in variant_rows:
                src = by_id.get(row["variant_id"])
                if src:
                    vs.append({**src, "acmg_classification": row["classification"]})
            anat = build_anatomy(self.graph, self.onto, {"observed": []}, vs, {})
            return {s["id"]: s["variant_ids"] for s in anat["systems"] if s["variant_ids"]}

        from ml_services.twin.anatomy import system_of_hpo

        base, scen = result.get("baseline", {}), result.get("scenario", {})
        if "variant_ranking" not in base:
            return []
        bv, sv = systems_for(base["variant_ranking"]), systems_for(scen["variant_ranking"])

        def pheno(hpos: List[str]) -> Dict[str, int]:
            out: Dict[str, int] = {}
            for h in hpos:
                sid = system_of_hpo(h, self.onto) if self.onto.known(h) else None
                if sid:
                    out[sid] = out.get(sid, 0) + 1
            return out

        bp, sp = pheno(base.get("hpo_ids", [])), pheno(scen.get("hpo_ids", []))
        out = []
        for sid in sorted(set(bv) | set(sv) | set(bp) | set(sp)):
            row = {"system": sid, "variants_before": len(bv.get(sid, [])), "variants_after": len(sv.get(sid, [])),
                   "phenotypes_before": bp.get(sid, 0), "phenotypes_after": sp.get(sid, 0)}
            if (row["variants_before"], row["phenotypes_before"]) != (row["variants_after"], row["phenotypes_after"]):
                out.append(row)
        return out

    # ------------------------------ diffing ------------------------------

    @staticmethod
    def _diff(base: dict, scen: dict) -> dict:
        bd = {d["disease_id"]: d for d in base["differential"]}
        sd = {d["disease_id"]: d for d in scen["differential"]}
        disease_changes = []
        for did in list(bd) + [d for d in sd if d not in bd]:
            b, s = bd.get(did), sd.get(did)
            row = {
                "disease_id": did, "disease_name": (b or s)["disease_name"],
                "rank_before": b["rank"] if b else None, "rank_after": s["rank"] if s else None,
                "probability_before": b["probability"] if b else None,
                "probability_after": s["probability"] if s else None,
                "plp_before": b["pathogenic_or_likely_variants"] if b else None,
                "plp_after": s["pathogenic_or_likely_variants"] if s else None,
                "vus_before": b["vus_variants"] if b else None, "vus_after": s["vus_variants"] if s else None,
                "genomic_priority_before": b["genomic_priority"] if b else None,
                "genomic_priority_after": s["genomic_priority"] if s else None,
            }
            if (row["rank_before"], row["probability_before"], row["plp_before"], row["vus_before"],
                    row["genomic_priority_before"]) != (row["rank_after"], row["probability_after"],
                                                        row["plp_after"], row["vus_after"],
                                                        row["genomic_priority_after"]):
                disease_changes.append(row)

        bc = {c["disease_id"]: c for c in base["genomic_candidates"]}
        sc = {c["disease_id"]: c for c in scen["genomic_candidates"]}
        candidate_changes = []
        for did in list(bc) + [d for d in sc if d not in bc]:
            b, s = bc.get(did), sc.get(did)
            bv = (b["pathogenic_or_likely_variants"], b["vus_variants"], b["genomic_priority"]) if b else None
            sv = (s["pathogenic_or_likely_variants"], s["vus_variants"], s["genomic_priority"]) if s else None
            if bv != sv:
                candidate_changes.append({"disease_id": did, "disease_name": (b or s)["disease_name"],
                                          "before": bv, "after": sv})

        brank = {v["variant_id"]: v for v in base["variant_ranking"]}
        srank = {v["variant_id"]: v for v in scen["variant_ranking"]}
        variant_changes = []
        for vid, b in brank.items():
            s = srank.get(vid)
            if s is None:
                variant_changes.append({"variant_id": vid, "gene": b["gene"], "change": "excluded",
                                        "rank_before": b["rank"], "rank_after": None})
            elif (s["rank"], s["priority_score"], s["classification"]) != (b["rank"], b["priority_score"], b["classification"]):
                variant_changes.append({"variant_id": vid, "gene": b["gene"], "change": "rescored",
                                        "rank_before": b["rank"], "rank_after": s["rank"],
                                        "score_before": b["priority_score"], "score_after": s["priority_score"],
                                        "class_before": b["classification"], "class_after": s["classification"]})
        bt, st = base["top_diagnosis"], scen["top_diagnosis"]
        return {
            "top_diagnosis_changed": (bt or {}).get("disease_id") != (st or {}).get("disease_id"),
            "differential_order_changed": [d["disease_id"] for d in base["differential"]] !=
                                          [d["disease_id"] for d in scen["differential"]],
            "disease_changes": disease_changes,
            "genomic_candidate_changes": candidate_changes,
            "variant_changes": variant_changes,
            "variant_count_delta": {k: scen["variant_counts"][k] - base["variant_counts"][k]
                                    for k in base["variant_counts"]},
        }

    @staticmethod
    def _headline_rows(base: dict, scen: dict) -> List[dict]:
        def tv(side, key):
            t = side["top_diagnosis"]
            return t[key] if t else None
        return [
            {"label": "Top diagnosis", "baseline": tv(base, "disease_name"), "scenario": tv(scen, "disease_name")},
            {"label": "Top diagnosis probability", "baseline": tv(base, "probability"), "scenario": tv(scen, "probability")},
            {"label": "Supporting phenotypes (top diagnosis)", "baseline": tv(base, "supporting_phenotypes"),
             "scenario": tv(scen, "supporting_phenotypes")},
            {"label": "Relevant variants (top diagnosis)", "baseline": tv(base, "relevant_variants"),
             "scenario": tv(scen, "relevant_variants")},
            {"label": "Genomic priority (top diagnosis)", "baseline": tv(base, "genomic_priority"),
             "scenario": tv(scen, "genomic_priority")},
            {"label": "Phenotypes", "baseline": base["phenotype_count"], "scenario": scen["phenotype_count"]},
            {"label": "Variants analysed", "baseline": base["variant_counts"]["total"],
             "scenario": scen["variant_counts"]["total"]},
            {"label": "Pathogenic + likely pathogenic",
             "baseline": base["variant_counts"]["pathogenic"] + base["variant_counts"]["likely_pathogenic"],
             "scenario": scen["variant_counts"]["pathogenic"] + scen["variant_counts"]["likely_pathogenic"]},
            {"label": "VUS", "baseline": base["variant_counts"]["vus"], "scenario": scen["variant_counts"]["vus"]},
            {"label": "Tier 1 variants", "baseline": base["variant_counts"]["tier1"],
             "scenario": scen["variant_counts"]["tier1"]},
        ]

    def _package(self, base: dict, scen: dict, label: str, explanation: List[str],
                 limitations: List[str], extra: Optional[dict] = None) -> dict:
        out = {
            "label": label, "baseline": base, "scenario": scen,
            "comparison": self._headline_rows(base, scen),
            "diff": self._diff(base, scen),
            "explanation": explanation, "limitations": limitations,
        }
        out.update(extra or {})
        return out

    # ------------------------------ helpers ------------------------------

    def _need_variants(self, core: dict) -> None:
        if not core["variants"]:
            raise ScenarioError(f"{ts.INSUFFICIENT}: this scenario needs a Variant Intelligence analysis "
                                "linked to the patient.")

    def _need_phenotypes(self, core: dict) -> None:
        if not core["hpo_ids"]:
            raise ScenarioError(f"{ts.INSUFFICIENT}: this scenario needs documented HPO phenotypes.")

    @staticmethod
    def _vlabel(v: dict) -> str:
        return f"{v.get('gene_symbol') or 'unknown gene'} {v.get('cdna') or v.get('hgvs') or v['variant_id']}"

    def _ranking_sentences(self, diff: dict, base: dict, scen: dict, *, phenotype_driven: bool) -> List[str]:
        out: List[str] = []
        bt, st = base["top_diagnosis"], scen["top_diagnosis"]
        if not phenotype_driven:
            out.append("The differential diagnosis ranking is produced from HPO phenotypes and Indian "
                       "population priors only, so this change does not move it"
                       + (" (verified: ranking identical before and after)." if not diff["differential_order_changed"]
                          and not diff["top_diagnosis_changed"] else "."))
        elif diff["top_diagnosis_changed"]:
            out.append(f"Top diagnosis changed from {(bt or {}).get('disease_name', 'none')} "
                       f"to {(st or {}).get('disease_name', 'none')}.")
        else:
            out.append(f"Top diagnosis remains {(bt or {}).get('disease_name', 'none')}"
                       + (", but the ranking and probabilities changed." if diff["disease_changes"] else
                          "; ranking and probabilities are unchanged."))
        for ch in diff["disease_changes"][:6]:
            if ch["rank_before"] != ch["rank_after"] and phenotype_driven:
                out.append(f"{ch['disease_name']}: rank {ch['rank_before'] or 'not ranked'} -> "
                           f"{ch['rank_after'] or 'not ranked'}; probability "
                           f"{ch['probability_before']} -> {ch['probability_after']}.")
        for ch in diff["genomic_candidate_changes"][:6]:
            b, s = ch["before"], ch["after"]
            out.append(f"Genomic support for {ch['disease_name']}: "
                       f"{('P/LP=%d, VUS=%d, max priority=%s' % b) if b else 'none'} -> "
                       f"{('P/LP=%d, VUS=%d, max priority=%s' % s) if s else 'none'}.")
        return out

    # ------------------------------ scenarios ------------------------------

    def _run_variant_exclusion(self, core: dict, p: dict) -> dict:
        self._need_variants(core)
        ids = list(p.get("variant_ids") or [])
        if not ids:
            raise ScenarioError("Select at least one variant to exclude.")
        byid = {v["variant_id"]: v for v in core["variants"]}
        missing = [i for i in ids if i not in byid]
        if missing:
            raise ScenarioError(f"Variant(s) not in the selected analysis: {', '.join(missing)}")
        if len(ids) >= len(byid):
            raise ScenarioError("Excluding every variant leaves nothing to compare; keep at least one.")
        hpos = core["hpo_ids"]
        base = self._evaluate(core, hpos)
        scen = self._evaluate(core, hpos, exclude=set(ids))
        diff = self._diff(base, scen)
        ex = [byid[i] for i in ids]
        expl = [f"Excluded {self._vlabel(v)} ({v['acmg_classification']}, priority "
                f"{next(x['priority_score'] for x in base['variant_ranking'] if x['variant_id'] == v['variant_id'])}, "
                f"rank {next(x['rank'] for x in base['variant_ranking'] if x['variant_id'] == v['variant_id'])})."
                for v in ex]
        d = diff["variant_count_delta"]
        expl.append("Variant counts changed: " + ", ".join(f"{k} {v:+d}" for k, v in d.items() if v) + ".")
        expl += self._ranking_sentences(diff, base, scen, phenotype_driven=False)
        moved = [vc for vc in diff["variant_changes"] if vc["change"] == "rescored"]
        for vc in moved[:3]:
            expl.append(f"{vc['gene']} variant moved from rank {vc['rank_before']} to {vc['rank_after']}.")
        if len(moved) > 3:
            expl.append(f"{len(moved) - 3} further variant(s) each moved up one rank (see Variant changes).")
        return self._package(base, scen, "Variant exclusion", expl, [
            "Variant priority scores are per-variant, so excluding one variant re-ranks the others but does "
            "not change their scores.",
            "The diagnosis engine does not take variants as input; genomic support is a separate, computed view."],
            {"modification": {"excluded_variants": [self._vlabel(v) for v in ex]}})

    def _run_variant_reclassification(self, core: dict, p: dict) -> dict:
        self._need_variants(core)
        vid, new_cls = p.get("variant_id"), p.get("new_classification")
        byid = {v["variant_id"]: v for v in core["variants"]}
        if vid not in byid:
            raise ScenarioError("Select a variant from the selected analysis.")
        if new_cls not in ACMG_POINTS:
            raise ScenarioError(f"new_classification must be one of {list(ACMG_POINTS)}")
        v = byid[vid]
        if new_cls == v["acmg_classification"]:
            raise ScenarioError(f"Variant is already classified as {new_cls}; choose a different class.")
        hpos = core["hpo_ids"]
        base = self._evaluate(core, hpos)
        scen = self._evaluate(core, hpos, reclass={vid: new_cls})
        diff = self._diff(base, scen)
        b = next(x for x in base["variant_ranking"] if x["variant_id"] == vid)
        s = next(x for x in scen["variant_ranking"] if x["variant_id"] == vid)
        expl = [f"{self._vlabel(v)} hypothetically reclassified {v['acmg_classification']} -> {new_cls}.",
                f"ACMG component of its composite priority changed from {ACMG_POINTS[v['acmg_classification']]:g} "
                f"to {ACMG_POINTS[new_cls]:g} points; priority {b['priority_score']} -> {s['priority_score']}, "
                f"{b['tier']} -> {s['tier']}, rank {b['rank']} -> {s['rank']}."]
        expl += self._ranking_sentences(diff, base, scen, phenotype_driven=False)
        return self._package(base, scen, "Variant reclassification", expl, [
            "This applies a hypothetical ACMG class to the composite score; it does NOT re-run the ACMG "
            "criteria or assert that the evidence supports the new class.",
            "The diagnosis engine does not take variants as input."],
            {"modification": {"variant": self._vlabel(v), "from": v["acmg_classification"], "to": new_cls}})

    def _run_phenotype_remove(self, core: dict, p: dict) -> dict:
        self._need_phenotypes(core)
        ids = list(p.get("hpo_ids") or [])
        if not ids:
            raise ScenarioError("Select at least one phenotype to remove.")
        missing = [i for i in ids if i not in core["hpo_ids"]]
        if missing:
            raise ScenarioError(f"Phenotype(s) not in the current Twin: {', '.join(missing)}")
        return self._phenotype_scenario(core, [h for h in core["hpo_ids"] if h not in ids],
                                        "Phenotype removal", removed=ids, added=[])

    def _run_phenotype_add(self, core: dict, p: dict) -> dict:
        ids = list(p.get("hpo_ids") or [])
        if not ids:
            raise ScenarioError("Select at least one phenotype to add.")
        unknown = [i for i in ids if not self.onto.known(i)]
        if unknown:
            raise ScenarioError(f"Phenotype(s) not in the Knowledge Graph: {', '.join(unknown)}")
        dup = [i for i in ids if i in core["hpo_ids"]]
        if dup:
            raise ScenarioError(f"Phenotype(s) already present: {', '.join(dup)}")
        return self._phenotype_scenario(core, core["hpo_ids"] + ids, "Phenotype addition", removed=[], added=ids)

    def _phenotype_scenario(self, core: dict, new_hpos: List[str], label: str, removed: List[str],
                            added: List[str]) -> dict:
        base = self._evaluate(core, core["hpo_ids"])
        scen = self._evaluate(core, new_hpos)
        diff = self._diff(base, scen)
        nm = lambda h: f"{self.onto.name(h) or h} ({h})"
        expl = []
        if removed:
            expl.append("Removed phenotype(s): " + "; ".join(nm(h) for h in removed) + ".")
        if added:
            expl.append("Added phenotype(s): " + "; ".join(nm(h) for h in added) + ".")
        expl.append(f"The existing diagnosis engine was re-run on {len(new_hpos)} phenotype(s) "
                    f"(was {len(core['hpo_ids'])}).")
        expl += self._ranking_sentences(diff, base, scen, phenotype_driven=True)
        for vc in diff["variant_changes"][:6]:
            expl.append(f"{vc['gene']} variant priority {vc['score_before']} -> {vc['score_after']} "
                        f"(phenotype-overlap component with {vc['gene']}'s disease profile changed).")
        if not scen["diagnosis_available"]:
            expl.append(f"{ts.INSUFFICIENT}: no phenotypes remain, so no diagnosis can be ranked.")
        return self._package(base, scen, label, expl, [
            "Onset, severity and frequency are not modelled; each HPO term is treated as present/absent."],
            {"modification": {"removed": [nm(h) for h in removed], "added": [nm(h) for h in added]}})

    def _run_diagnosis_focus(self, core: dict, p: dict) -> dict:
        self._need_phenotypes(core)
        did = p.get("disease_id")
        node = self.graph.node("Disease", did) if did else None
        if not node:
            raise ScenarioError("Select a disease that exists in the Knowledge Graph.")
        hpos = core["hpo_ids"]
        variants = self._variants_for(core, hpos)
        wide = ts.evaluate_diagnosis_state(self.dx, self.graph, hpos, core["context"], variants,
                                           top_k=50, explain=True, _cache=self._dx_cache)
        if not wide["available"]:
            raise ScenarioError(f"{ts.INSUFFICIENT}: no phenotype matched any disease.")
        top = wide["top_diagnosis"]
        if top["disease_id"] == did:
            raise ScenarioError("That disease is already the top diagnosis; pick a different one.")
        hyp = next((d for d in wide["differential"] if d["disease_id"] == did), None)
        sim = round(self.dx.baseline.disease_score(hpos, did), 4)
        missing = self.dx.missing_terms(hpos, did, top_n=5)
        drivers = self.dx.attribute_symptoms(hpos, did, top_n=5)
        sup = ts.genomic_support(self.graph, variants, did)

        def side(d, sup_d, miss, drv, name, did_):
            return {
                "disease_id": did_, "disease_name": name,
                "rank": d["rank"] if d else None,
                "probability": d["probability"] if d else None,
                "phenotype_similarity": d["phenotype_similarity"] if d else sim,
                "supporting_phenotypes": ts.supporting_phenotypes(self.dx, hpos, did_),
                "missing_findings": miss, "driving_symptoms": drv,
                "genes": sup_d["genes"], "pathogenic_or_likely_variants": sup_d["pathogenic_or_likely"],
                "vus_variants": sup_d["vus"], "genomic_priority": sup_d["max_priority_score"],
                "relevant_variants": len(sup_d["variant_ids"]),
                "confirmatory_tests": (d or {}).get("confirmatory_tests") or
                (self.dx.confirmatory.get(did_) and {
                    "first_line": self.dx.confirmatory[did_].get("first_line_tests"),
                    "genetic": self.dx.confirmatory[did_].get("genetic_confirmation")}),
            }
        base = side(top, top["genomic_support"], top.get("missing_findings", []),
                    top.get("driving_symptoms", []), top["disease_name"], top["disease_id"])
        scen = side(hyp, sup, missing, drivers, node.get("name", did), did)
        rank_txt = (f"rank {hyp['rank']} (probability {hyp['probability']})" if hyp else
                    "outside the top 50 ranked differentials")
        expl = [f"Working diagnosis compared: {scen['disease_name']} vs current top {base['disease_name']}.",
                f"{scen['disease_name']} is at {rank_txt} on phenotype evidence, with phenotype similarity "
                f"{scen['phenotype_similarity']} vs {base['phenotype_similarity']}.",
                f"{scen['supporting_phenotypes']} of {len(hpos)} patient phenotype(s) support it "
                f"(vs {base['supporting_phenotypes']} for {base['disease_name']}).",
                f"Genomic support: {scen['pathogenic_or_likely_variants']} P/LP and {scen['vus_variants']} VUS "
                f"variant(s) in its genes ({', '.join(scen['genes']) or 'no gene recorded'}), vs "
                f"{base['pathogenic_or_likely_variants']} P/LP / {base['vus_variants']} VUS for the current top."]
        if missing:
            expl.append("Expected findings for the alternative that are not documented: "
                        + ", ".join(m["hpo_name"] for m in missing) + ".")
        return {"label": "Diagnosis comparison", "baseline": base, "scenario": scen, "comparison": [
            {"label": "Diagnosis", "baseline": base["disease_name"], "scenario": scen["disease_name"]},
            {"label": "Phenotype rank", "baseline": base["rank"], "scenario": scen["rank"]},
            {"label": "Probability", "baseline": base["probability"], "scenario": scen["probability"]},
            {"label": "Phenotype similarity", "baseline": base["phenotype_similarity"], "scenario": scen["phenotype_similarity"]},
            {"label": "Supporting phenotypes", "baseline": base["supporting_phenotypes"], "scenario": scen["supporting_phenotypes"]},
            {"label": "Relevant variants", "baseline": base["relevant_variants"], "scenario": scen["relevant_variants"]},
            {"label": "P/LP variants", "baseline": base["pathogenic_or_likely_variants"], "scenario": scen["pathogenic_or_likely_variants"]},
            {"label": "Genomic priority", "baseline": base["genomic_priority"], "scenario": scen["genomic_priority"]},
        ], "diff": {"top_diagnosis_changed": False, "diagnosis_comparison": True},
            "explanation": expl,
            "limitations": ["This compares evidence for two diagnoses; it does not change the engine's ranking "
                            "or establish that the alternative is correct."],
            "modification": {"working_diagnosis": scen["disease_name"]}}

    def _run_medication(self, core: dict, p: dict) -> dict:
        drugs = [d.strip() for d in (p.get("drugs") or []) if d and d.strip()]
        if not drugs:
            raise ScenarioError("Enter at least one drug name.")
        known, observations = ts.known_genotypes_from_variants(core["variants"])
        patient = core["patient"]
        res = self.pgx.check_drugs(drugs, state=patient.get("state") or "", known_genotypes=known,
                                   age=patient.get("age_years"), sex=patient.get("sex") or "")
        alerts = res["alerts"]
        base = {"medications_recorded": 0, "alerts": 0, "note": "No medication list is stored in the case data."}
        scen = {"medications_screened": drugs, "alerts": len(alerts),
                "critical": res["summary"]["critical"], "high": res["summary"]["high"],
                "medium": res["summary"]["medium"], "low": res["summary"]["low"],
                "drugs_without_pgx_rule": res["drugs_without_pgx_rule"],
                "findings": [{k: a[k] for k in ("drug", "gene", "severity", "inferred_status", "recommendation",
                                                "evidence_level", "alternatives", "assumption")} for a in alerts]}
        expl = []
        for a in alerts:
            basis = ("assigned from the patient's variant analysis" if a["assumption"] == "known_genotype_override"
                     else "inferred from Indian population allele frequency (no patient genotype available)")
            expl.append(f"{a['drug']} / {a['gene']}: {a['severity']} severity; status {a['inferred_status']} "
                        f"{basis}. Guideline: {a['recommendation'] or 'no recommendation text in rule'}")
        for d in res["drugs_without_pgx_rule"]:
            expl.append(f"{d}: no drug-gene rule exists in the platform's PGx knowledge; nothing can be said.")
        if not expl:
            expl.append("No pharmacogenomic alert was produced.")
        return {"label": "Medication introduction", "baseline": base, "scenario": scen, "comparison": [
            {"label": "Medications screened", "baseline": 0, "scenario": len(drugs)},
            {"label": "PGx alerts", "baseline": 0, "scenario": len(alerts)},
            {"label": "Critical / high", "baseline": 0, "scenario": res["summary"]["critical"] + res["summary"]["high"]},
        ], "diff": {"medication_screening": True}, "explanation": expl,
            "limitations": ["Rule-based drug-gene screening only. Clinical outcome, dose response and "
                            "adverse-event likelihood for this patient are NOT modelled."],
            "modification": {"drugs": drugs, "genotypes_used": known}}
