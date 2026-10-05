"""Phase 10: Reproductive Genetics workspace.

Couple (two real pedigree members) -> recorded genotypes -> carrier status -> inheritance -> Mendelian probability
-> Punnett -> Bayesian prior/posterior -> Monte Carlo -> scenarios.

All probabilities come from the existing engines (``CarrierCounselor``, ``punnett``) or from a transparent
simulation of the same model. Nothing is shown for inheritance patterns the engine cannot model.
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional

from ml_services.pedigree import analysis as pa
from ml_services.reproductive import punnett

SAFETY = ("Calculated genetic probability, not a clinical outcome prediction. Results depend on the recorded genotypes and "
          "stated assumptions; discuss them with a clinician or genetic counselor.")
SUPPORTED = ("autosomal recessive", "autosomal dominant", "x-linked recessive")
STATUS_LABEL = {"carrier": "Carrier", "not_carrier": "Not a carrier", "affected": "Affected", "unknown": "Carrier status cannot be determined"}


class ReproError(ValueError):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def supported_mode(inheritance: str) -> Optional[str]:
    """Map a disease inheritance string to a modelled pattern, or None when the engine cannot model it."""
    i = (inheritance or "").lower()
    if "mitochond" in i or "multifactor" in i or "x-linked dominant" in i or "chromosomal" in i:
        return None
    if "x-linked" in i:
        return "x-linked recessive"
    if "recessive" in i:
        return "autosomal recessive"
    if "dominant" in i:
        return "autosomal dominant"
    return None


def wilson(k: int, n: int, z: float = 1.96) -> List[float]:
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def punnett_grid(a: str, b: str) -> dict:
    """Dynamic autosomal Punnett square with per-cell probability and phenotype label."""
    sq = punnett.punnett_square(a, b)
    cells = []
    for i, row in enumerate(sq["grid"]):
        cells.append([{"genotype": "".join(sorted(g, key=lambda x: (x != "A", x))), "probability": 0.25} for g in row])
    return {"parent_a": a, "parent_b": b, "gametes_a": punnett.gametes(a), "gametes_b": punnett.gametes(b), "cells": cells,
            "genotype_probabilities": sq["genotypes"], "outcome_probabilities": sq["phenotypes"]}


class ReproWorkspace:
    def __init__(self, registry):
        self.registry = registry

    # ------------------------------ couple ------------------------------

    def members(self, pid: str) -> dict:
        fam = self.registry.pedigree.family(pid)
        ms = [{"member_id": m["member_id"], "label": fam.label(m["member_id"]), "sex": m["sex"], "affected": m["affected"],
               "is_proband": bool(m.get("is_proband"))} for m in fam.members.values()]
        default = None
        if fam.proband:
            pr = fam.g.parents.get(fam.proband["member_id"], [])
            if len(pr) >= 2:
                default = {"partner_a": pr[0], "partner_b": pr[1]}
        return {"patient_id": pid, "members": ms, "default_couple": default,
                "note": None if ms else "No pedigree recorded for this case. Add family members in Pedigree to select a couple."}

    def _carrier_table(self, fam, mid: str) -> dict:
        rows = []
        for vkey, meta in fam.variants.items():
            if not meta.get("gene"):
                continue
            st = fam.state(mid, vkey)
            rows.append({"gene": meta["gene"], "variant_key": vkey, "classification": meta.get("classification"),
                         "genotype_state": st if st != "unknown" else "Not documented",
                         "carrier": True if pa.is_carrier(st) else (False if st != "unknown" else None)})
        m = fam.members[mid]
        return {"member_id": mid, "label": fam.label(mid), "sex": m["sex"], "affected": m["affected"], "variants": rows,
                "note": None if rows else "No variants are registered in this pedigree: carrier status cannot be determined."}

    @staticmethod
    def _status(partner: dict, did: str) -> str:
        if (partner.get("known_affected") or {}).get(did):
            return "affected"
        kc = (partner.get("known_carrier") or {})
        if kc.get(did) is True:
            return "carrier"
        if kc.get(did) is False:
            return "not_carrier"
        return "unknown"

    def _punnett_for(self, mode: str, sa: str, sb: str, partner_a: dict, partner_b: dict) -> Optional[dict]:
        if mode == "autosomal recessive":
            g = {"affected": "aa", "carrier": "Aa", "not_carrier": "AA"}
            if sa not in g or sb not in g:
                return None
            return {"mode": mode, **punnett_grid(g[sa], g[sb])}
        if mode == "autosomal dominant":
            if "affected" not in (sa, sb):
                return None
            g = {"affected": "Aa", "not_carrier": "AA", "carrier": "Aa"}
            if sa not in g or sb not in g:
                return None
            return {"mode": mode, "assumption": "An affected parent is assumed heterozygous (A = unaffected allele, a = disease allele).",
                    **punnett_grid(g[sa], g[sb])}
        if mode == "x-linked recessive":
            mother_is_b = (partner_b.get("sex") or "").upper().startswith("F")
            mom, dad = (partner_b, partner_a) if mother_is_b else (partner_a, partner_b)
            sm = sb if mother_is_b else sa
            sd = sa if mother_is_b else sb
            if (mom.get("sex") or "").upper()[:1] != "F" or sm == "unknown" or sd not in ("affected", "not_carrier"):
                return None
            mg = {"affected": "xx", "carrier": "Xx", "not_carrier": "XX"}[sm]
            return {"mode": mode, **punnett.x_linked_cross(mg, "XaY" if sd == "affected" else "XAY")}
        return None

    # ------------------------------ analysis ------------------------------

    def analyze(self, pid: str, partner_a: Optional[str] = None, partner_b: Optional[str] = None) -> dict:
        try:
            ctx = self.registry.pedigree.reproductive_context(pid, partner_a, partner_b)
        except LookupError:
            raise
        except ValueError as ex:  # includes PedigreeError (no proband / parents not recorded)
            raise ReproError(str(ex))
        fam = self.registry.pedigree.family(pid)
        pa_in, pb_in = ctx["partner_inputs"]["a"], ctx["partner_inputs"]["b"]
        ids = [p["member_id"] for p in ctx["partners"]]
        assessment = ctx["assessment"]
        risks = []
        for r in assessment["top_risks"]:
            mode = supported_mode(r["inheritance"])
            did = r["disease_id"]
            sa, sb = self._status(pa_in, did), self._status(pb_in, did)
            row = {"disease_id": did, "disease_name": r["disease_name"], "gene": r["gene"], "inheritance": r["inheritance"],
                   "supported": mode is not None, "carrier_status": {"partner_a": STATUS_LABEL[sa], "partner_b": STATUS_LABEL[sb]},
                   "evidence_query": f"{r['gene']} {r['disease_name']}".strip(),
                   "supporting_variants": [v["variant_key"] for t in (self._carrier_table(fam, i) for i in ids) for v in t["variants"]
                                           if v["gene"] == r["gene"] and v["carrier"]]}
            if mode is None:
                row.update({"note": ("Inheritance pattern not supported for a probability calculation "
                                     f"({r['inheritance']}); no risk is shown."), "probabilities": None, "bayesian": None, "punnett": None})
                risks.append(row)
                continue
            ca, cb = r["carrier_probability_partner_a"], r["carrier_probability_partner_b"]
            row["mode"] = mode
            row["probabilities"] = {"both_carriers": r["both_carriers_probability"], "child_affected": r["child_affected_probability"],
                                    "child_carrier": r["child_carrier_probability"], "one_in_n": r["one_in_n_children"]}
            row["bayesian"] = {"partner_a": self._bayes(ca), "partner_b": self._bayes(cb),
                               "note": "Prior and posterior are the counselor's computed values; the update is rule-based, so no separate likelihood is reported."}
            row["punnett"] = self._punnett_for(mode, sa, sb, pa_in, pb_in)
            if row["punnett"] is None:
                row["punnett_note"] = "Punnett square unavailable: parental genotypes are not both determined (Not analyzed)."
            risks.append(row)
        saved = self._saved_evidence(pid)
        for r in risks:
            r["saved_evidence"] = [e for e in saved if r["gene"].lower() in e["text"].lower() or r["disease_name"].lower() in e["text"].lower()]
            for e in r["saved_evidence"]:
                e.pop("text", None)
        return {"patient_id": pid, "available": True, "partners": [self._carrier_table(fam, i) for i in ids],
                "relationship_from_pedigree": ctx["relationship_from_pedigree"], "inbreeding_coefficient": assessment["inbreeding_coefficient"],
                "risk_band": assessment["risk_band"], "risks": risks, "screening": assessment["recommended_screening"],
                "assumptions": ["Carrier probabilities use Indian population priors adjusted for community, recorded genotypes and family history.",
                                "Genotypes come from the pedigree's recorded values; unrecorded genotypes are treated as unknown, never as normal.",
                                "Autosomal recessive, autosomal dominant and X-linked recessive patterns are modelled; others are not."],
                "safety": SAFETY, "partner_inputs": ctx["partner_inputs"]}

    @staticmethod
    def _bayes(c: dict) -> dict:
        return {"prior": c.get("prior"), "posterior": c.get("probability"), "update_basis": c.get("method"), "note": c.get("note"),
                "likelihood": "Not separately computed (rule-based update)"}

    def _saved_evidence(self, pid: str) -> List[dict]:
        from backend.app import store
        out = []
        for e in store.evidence_list(pid):
            rec = e.get("payload") or {}
            out.append({"title": rec.get("title") or "", "source": e.get("source"), "identifier": rec.get("pmid") or e.get("source_id"),
                        "text": f"{rec.get('title') or ''} {rec.get('abstract') or ''} {e.get('note') or ''}"})
        return out

    # ------------------------------ dynamic Punnett ------------------------------

    @staticmethod
    def punnett(a: str, b: str) -> dict:
        return {**punnett_grid(a, b), "safety": SAFETY}

    # ------------------------------ Monte Carlo ------------------------------

    @staticmethod
    def monte_carlo(p_a: float, p_b: float, n: int = 20000, seed: int = 5, inbreeding: float = 0.0) -> dict:
        if not (0.0 <= p_a <= 1.0 and 0.0 <= p_b <= 1.0 and 0.0 <= inbreeding <= 0.5):
            raise ReproError("Probabilities must be between 0 and 1 and the inbreeding coefficient between 0 and 0.5.")
        if not (1000 <= n <= 200000):
            raise ReproError("Simulation count must be between 1,000 and 200,000.")
        rng = random.Random(seed)
        c = {"affected": 0, "carrier": 0, "unaffected_non_carrier": 0}
        for _ in range(n):
            carrier_a = rng.random() < p_a
            carrier_b = carrier_a if rng.random() < inbreeding else rng.random() < p_b
            # each carrier parent transmits the disease allele with probability 1/2
            ta = carrier_a and rng.random() < 0.5
            tb = carrier_b and rng.random() < 0.5
            alleles = int(ta) + int(tb)
            c["affected" if alleles == 2 else "carrier" if alleles == 1 else "unaffected_non_carrier"] += 1
        analytic = punnett.offspring_risk_from_carrier_probs(p_a, p_b, "autosomal recessive", inbreeding)
        return {"mode": "autosomal recessive", "n_simulations": n, "seed": seed, "inputs": {"p_a": p_a, "p_b": p_b, "inbreeding_coefficient": inbreeding},
                "counts": c, "distribution": {k: round(v / n, 4) for k, v in c.items()},
                "affected_ci95": wilson(c["affected"], n), "analytic_affected_probability": analytic["affected_child_probability"],
                "existing_engine_check": punnett.simulate_offspring(p_a, p_b, n=n, seed=seed, inbreeding_coefficient=inbreeding),
                "assumptions": ["Each partner is a carrier with the given probability; carriers transmit the disease allele with probability 1/2.",
                                "Inbreeding is modelled as identity-by-descent with the stated coefficient.",
                                "Simulation estimates a probability distribution; it is not a guarantee for any pregnancy."],
                "safety": SAFETY}

    def monte_carlo_for_case(self, pid: str, disease_id: str, partner_a: Optional[str], partner_b: Optional[str], n: int, seed: int) -> dict:
        res = self.analyze(pid, partner_a, partner_b)
        row = next((r for r in res["risks"] if r["disease_id"] == disease_id), None)
        if not row:
            raise LookupError(f"Condition '{disease_id}' is not among this couple's assessed conditions")
        if row.get("mode") != "autosomal recessive":
            raise ReproError("Monte Carlo is available only for autosomal recessive conditions in this couple's assessment.")
        pa_, pb_ = row["bayesian"]["partner_a"]["posterior"], row["bayesian"]["partner_b"]["posterior"]
        return {"disease_id": disease_id, "disease_name": row["disease_name"],
                **self.monte_carlo(float(pa_), float(pb_), n, seed, float(res["inbreeding_coefficient"] or 0.0))}

    # ------------------------------ scenarios ------------------------------

    def scenario(self, pid: str, disease_id: str, status_a: str, status_b: str, partner_a: Optional[str], partner_b: Optional[str]) -> dict:
        base = self.analyze(pid, partner_a, partner_b)
        row = next((r for r in base["risks"] if r["disease_id"] == disease_id), None)
        if not row:
            raise LookupError(f"Condition '{disease_id}' is not among this couple's assessed conditions")
        if not row["supported"]:
            raise ReproError(row["note"])
        inp = {k: {**v, "known_carrier": dict(v.get("known_carrier") or {}), "known_affected": dict(v.get("known_affected") or {})}
               for k, v in base["partner_inputs"].items()}
        for key, st in (("a", status_a), ("b", status_b)):
            kc, ka = inp[key]["known_carrier"], inp[key]["known_affected"]
            kc.pop(disease_id, None)
            ka.pop(disease_id, None)
            if st == "carrier":
                kc[disease_id] = True
            elif st == "not_carrier":
                kc[disease_id] = False
            elif st == "affected":
                ka[disease_id] = True
                kc[disease_id] = True
        res = self.registry.counselor.couple_assessment(inp["a"], inp["b"], top_n=100)
        new = next(r for r in res["top_risks"] if r["disease_id"] == disease_id)
        mode = row["mode"]
        sa, sb = self._status(inp["a"], disease_id), self._status(inp["b"], disease_id)
        return {"disease_id": disease_id, "disease_name": row["disease_name"], "mode": mode,
                "scenario": {"partner_a": STATUS_LABEL[sa], "partner_b": STATUS_LABEL[sb]},
                "baseline": row["probabilities"],
                "result": {"both_carriers": new["both_carriers_probability"], "child_affected": new["child_affected_probability"],
                          "child_carrier": new["child_carrier_probability"], "one_in_n": new["one_in_n_children"]},
                "punnett": self._punnett_for(mode, sa, sb, inp["a"], inp["b"]),
                "note": "What-if only: the recorded pedigree is not changed.", "safety": SAFETY}

    # ------------------------------ patient-friendly / integrations ------------------------------

    def explain(self, pid: str, disease_id: str, partner_a: Optional[str], partner_b: Optional[str]) -> dict:
        res = self.analyze(pid, partner_a, partner_b)
        row = next((r for r in res["risks"] if r["disease_id"] == disease_id), None)
        if not row:
            raise LookupError(f"Condition '{disease_id}' is not among this couple's assessed conditions")
        if not row["supported"]:
            return {"disease_id": disease_id, "available": False, "note": row["note"], "safety": SAFETY}
        p = row["probabilities"]
        known = [f"{t['label']}: {row['carrier_status']['partner_a' if i == 0 else 'partner_b'].lower()}" for i, t in enumerate(res["partners"])]
        return {"disease_id": disease_id, "available": True, "sections": {
            "what_we_know": f"For {row['disease_name']} ({row['inheritance'].lower()}), the recorded information is: " + "; ".join(known) + ".",
            "what_the_calculation_means": (f"Based on these inputs, the calculated chance that a child is affected is {round(p['child_affected'] * 100, 2)}%"
                                           + (f" (about 1 in {p['one_in_n']})" if p["one_in_n"] else "") + f", and the chance a child is a carrier is {round(p['child_carrier'] * 100, 2)}%. "
                                           "This is a probability for each pregnancy, not a prediction for any one child."),
            "what_remains_uncertain": "Any genotype that was not recorded is treated as unknown, so the figure uses population averages for that person. Testing can change the result.",
            "discuss_with_clinician": "Please discuss these results, carrier testing and the available options with a clinician or genetic counselor."},
            "safety": SAFETY}

    def report_section(self, pid: str, partner_a: Optional[str] = None, partner_b: Optional[str] = None) -> dict:
        try:
            res = self.analyze(pid, partner_a, partner_b)
        except (ReproError, LookupError) as ex:
            return {"available": False, "note": str(ex)}
        return {"available": True, "partners": [{"label": p["label"], "variants": p["variants"]} for p in res["partners"]],
                "risks": [{k: r.get(k) for k in ("disease_name", "gene", "inheritance", "carrier_status", "probabilities", "supported", "note")}
                          for r in res["risks"] if r["supported"] and r["probabilities"] and r["probabilities"]["child_affected"] > 0][:8],
                "risk_band": res["risk_band"], "assumptions": res["assumptions"], "limitations": [SAFETY]}

    def ai_context(self, pid: str) -> dict:
        res = self.analyze(pid)
        lines = [f"REPRODUCTIVE GENETICS CONTEXT ({SAFETY})",
                 "Partners: " + "; ".join(f"{p['label']} ({len(p['variants'])} registered variants)" for p in res["partners"])]
        for r in res["risks"][:5]:
            if r["supported"] and r["probabilities"] and r["probabilities"]["child_affected"] > 0:
                p = r["probabilities"]
                b = r["bayesian"]
                lines.append(f"- {r['disease_name']} ({r['inheritance']}): partner A {r['carrier_status']['partner_a']} "
                             f"(prior {b['partner_a']['prior']}, posterior {b['partner_a']['posterior']}); partner B {r['carrier_status']['partner_b']} "
                             f"(prior {b['partner_b']['prior']}, posterior {b['partner_b']['posterior']}); child affected {p['child_affected']}, carrier {p['child_carrier']}")
        lines.append("Explain only these calculated values; do not state certainty or make decisions.")
        return {"text": "\n".join(lines), "citations": [{"source_type": "reproductive", "identifier": f"{pid}:repro", "title": "Case reproductive genetics workspace",
                                                         "summary": "Calculated Mendelian/Bayesian probabilities from the pedigree", "reliability": "calculated"}],
                "summary": {"reproductive": True}}
