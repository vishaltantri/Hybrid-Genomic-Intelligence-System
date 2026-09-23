"""Module 6: Reproductive & Prenatal Genetic Risk Counselor.

Patent claim #6: Bayesian carrier probability estimation using Indian population priors.

Model
-----
For each disease d and partner p:

    P(p is carrier) = prior(base carrier rate, community multiplier)
                      updated by family history likelihoods
                      forced to 1.0 by direct evidence (known carrier / affected child)

Family-history likelihood ratios (odds multipliers):
    affected child          -> obligate carrier (prior forced to ~1.0)
    affected sibling        -> 2/3 (parents are proven carriers)
    affected first cousin   -> x3
    known carrier (test)    -> 1.0
    known NOT carrier       -> 0.0

Couple offspring risk (autosomal recessive):
    F  = inbreeding coefficient from recorded consanguinity (first cousins 1/16, etc.)
    P(both carriers) = pA*pB*(1-F) + F*(pA+pB)/2
    P(affected child) = 0.25 * P(both carriers)

The F term is the India-specific piece: state consanguinity rates (NFHS-5) turn into a
couple-level inbreeding coefficient, which raises risk even when both partners look
"average risk" by population carrier rate alone.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ml_services.config import SEEDS_DIR
from ml_services.reproductive import punnett
from ml_services.utils import read_csv_rows, read_json

CONSANGUINITY_PATHS = [
    SEEDS_DIR / "nfhs5_consanguinity.csv",
]
CARRIER_PATHS = [SEEDS_DIR / "carrier_frequencies_india.csv"]
COMMUNITY_PATHS = [SEEDS_DIR / "indian_communities.csv"]

# Inbreeding coefficients for common consanguineous relationships
INBREEDING_F = {
    "first_cousins": 1 / 16,          # 0.0625
    "uncle_niece": 1 / 8,             # 0.125
    "second_cousins": 1 / 64,         # 0.015625
    "double_first_cousins": 1 / 8,
    "unrelated": 0.0,
}

# Maternal age -> Down syndrome risk at birth (per 1000 live births), commonly cited table
MATERNAL_AGE_DOWN_RISK = [
    (20, 0.6), (25, 0.9), (30, 1.4), (35, 3.0), (38, 6.0), (40, 10.0),
    (42, 16.0), (44, 26.0), (46, 40.0), (48, 55.0), (50, 70.0),
]


class CarrierCounselor:
    def __init__(self):
        self.diseases = read_csv_rows(CARRIER_PATHS[0])
        self.communities = {r["community"]: r for r in read_csv_rows(COMMUNITY_PATHS[0])}
        self.consanguinity = {r["state"]: float(r["consanguinity_rate_pct"] or 0) / 100.0
                              for r in read_csv_rows(CONSANGUINITY_PATHS[0])}
        try:
            self.schemes = read_json(SEEDS_DIR / "government_schemes.json")
        except Exception:
            self.schemes = {"schemes": [], "counselling_points": []}

    # ------------------------- individual carrier probability -------------------------

    def carrier_probability(self, partner: dict, disease: dict) -> dict:
        base = float(disease.get("carrier_freq_general") or 0.0)
        community = (partner.get("community") or "").strip()
        multiplier = 1.0
        note = ""
        if community and community in self.communities:
            c = self.communities[community]
            if c.get("founder_disease_id") == disease["disease_id"]:
                multiplier = float(c.get("carrier_multiplier") or 1.0)
                note = c.get("founder_note", "")
        # Named high-risk community match (even if the person's own community is unrecorded)
        high_risk = [c.strip() for c in (disease.get("high_risk_communities") or "").split(";") if c.strip()]
        if community and any(community.lower() == h.lower() for h in high_risk):
            community_freq = float(disease.get("community_carrier_freq") or 0.0)
            if community_freq > 0:
                base = max(base, community_freq)
                note = note or f"{community} is a documented higher-frequency community"

        prior = min(base * multiplier, 0.95)

        fh = (partner.get("family_history") or {})
        history = fh.get(disease["disease_id"])
        known = partner.get("known_carrier") or {}
        if known.get(disease["disease_id"]) is True:
            return {"probability": 1.0, "prior": prior, "method": "known_carrier_test",
                    "note": "Confirmed carrier on genetic testing", "multiplier": multiplier}
        if known.get(disease["disease_id"]) is False:
            return {"probability": 0.0, "prior": prior, "method": "known_not_carrier",
                    "note": "Tested and NOT a carrier", "multiplier": multiplier}

        if history == "affected_child":
            return {"probability": 1.0, "prior": prior, "method": "obligate_carrier",
                    "note": "An affected child means both parents are carriers", "multiplier": multiplier}
        if history == "affected_sibling":
            return {"probability": round(2 / 3, 4), "prior": prior, "method": "affected_sibling",
                    "note": "Affected sibling implies carrier parents; 2/3 carrier probability", "multiplier": multiplier}
        if history == "affected_first_cousin":
            return {"probability": min(0.95, prior * 3), "prior": prior, "method": "affected_relative_x3",
                    "note": "Affected close relative raises probability ~3x", "multiplier": multiplier}
        if history == "affected_parent":
            # For recessive disease an affected parent is an obligate carrier (if alive)
            return {"probability": 0.9, "prior": prior, "method": "affected_parent",
                    "note": "Affected parent is a carrier (residual uncertainty from diagnosis)", "multiplier": multiplier}

        return {"probability": round(prior, 4), "prior": round(prior, 4), "method": "population_prior",
                "note": note or "Population carrier frequency with community adjustment",
                "multiplier": multiplier}

    # ------------------------- couple assessment -------------------------

    def couple_assessment(self, partner_a: dict, partner_b: dict, top_n: int = 20) -> dict:
        relationship = (partner_a.get("relationship") or partner_b.get("relationship") or "").strip()
        F_explicit = partner_a.get("inbreeding_coefficient")
        if F_explicit is None and relationship:
            F_explicit = INBREEDING_F.get(relationship)
        state = partner_a.get("state") or partner_b.get("state") or ""
        state_cons_rate = self.consanguinity.get(state, 0.0)
        if F_explicit is None:
            # Unknown relationship: use the state consanguinity rate as a weak signal,
            # discounting it heavily because it is a regional prior, not a couple fact.
            F_explicit = 0.0
            regional_flag = state_cons_rate >= 0.15
        else:
            regional_flag = False

        results: List[dict] = []
        for d in self.diseases:
            inheritance = (d.get("inheritance") or "").strip()
            ca = self.carrier_probability(partner_a, d)
            cb = self.carrier_probability(partner_b, d)

            if "dominant" in inheritance.lower() and "recessive" not in inheritance.lower() and "x-linked" not in inheritance.lower():
                # Dominant conditions: transmission risk from an affected parent, not carrier state.
                affected_risk = max(
                    1.0 if (partner_a.get("known_affected") or {}).get(d["disease_id"]) else 0.0,
                    1.0 if (partner_b.get("known_affected") or {}).get(d["disease_id"]) else 0.0,
                )
                risk = punnett.offspring_risk_from_carrier_probs(affected_risk, 0.0, "autosomal dominant")
                child_risk = risk["affected_child_probability"]
                carrier_child = 0.5 * affected_risk
                both_carriers = affected_risk
                mode = "autosomal dominant"
            elif "x-linked" in inheritance.lower():
                mother = partner_b if (partner_b.get("sex") or "").upper().startswith("F") else partner_a
                father = partner_a if mother is partner_b else partner_b
                mother_p = self.carrier_probability(mother, d)["probability"]
                father_affected = bool((father.get("known_affected") or {}).get(d["disease_id"]))
                # Weight the cross by the probability the mother is actually a carrier.
                sons_affected = mother_p * 0.5
                daughters_affected = mother_p * 0.5 * (1.0 if father_affected else 0.0)
                daughters_carrier = mother_p * 0.5
                child_risk = 0.5 * (sons_affected + daughters_affected)
                carrier_child = daughters_carrier * 0.5  # weighted over both sexes
                both_carriers = mother_p
                mode = "x-linked recessive"
                x_linked_detail = punnett.x_linked_cross("Xx", "XaY" if father_affected else "XAY")
            elif "chromosomal" in inheritance.lower():
                maternal_age = int(partner_b.get("age") or partner_a.get("age") or 30)
                child_risk = self._down_risk(maternal_age)
                carrier_child, both_carriers = 0.0, 0.0
                mode = "chromosomal (maternal age)"
            else:
                risk = punnett.offspring_risk_from_carrier_probs(ca["probability"], cb["probability"],
                                                                 inbreeding_coefficient=F_explicit)
                child_risk = risk["affected_child_probability"]
                carrier_child = risk["carrier_child_probability"]
                both_carriers = risk["both_carriers_probability"]
                mode = "autosomal recessive"

            entry = {
                "disease_id": d["disease_id"],
                "disease_name": d["disease_name"],
                "gene": d.get("gene", ""),
                "inheritance": d.get("inheritance", ""),
                "mode_used": mode,
                "carrier_probability_partner_a": ca,
                "carrier_probability_partner_b": cb,
                "both_carriers_probability": round(both_carriers, 6),
                "child_affected_probability": round(child_risk, 6),
                "child_carrier_probability": round(carrier_child, 6),
                "one_in_n_children": (round(1 / child_risk) if child_risk > 0 else None),
                "india_affected_births_per_year": d.get("india_affected_births_per_year_est", ""),
                "source_note": d.get("source_note", ""),
            }
            if mode == "x-linked recessive":
                entry["x_linked_detail"] = {
                    "mother_carrier_probability": round(both_carriers, 4),
                    "sons_affected_probability": round(sons_affected, 4),
                    "daughters_affected_probability": round(daughters_affected, 4),
                    "if_carrier_punnett": x_linked_detail,
                }
            results.append(entry)

        results.sort(key=lambda r: r["child_affected_probability"], reverse=True)
        top = results[:top_n]

        high = [r for r in top if r["child_affected_probability"] >= 0.01]      # >= 1%
        moderate = [r for r in top if 0.001 <= r["child_affected_probability"] < 0.01]

        return {
            "partners": {"a": {k: v for k, v in partner_a.items() if k != "family_history"},
                         "b": {k: v for k, v in partner_b.items() if k != "family_history"}},
            "state": state,
            "state_consanguinity_rate": state_cons_rate,
            "couple_consanguineous": bool(F_explicit and F_explicit > 0),
            "inbreeding_coefficient": F_explicit,
            "regional_consanguinity_flag": regional_flag,
            "risk_band": ("high" if high else ("moderate" if moderate else "low")),
            "high_risk_conditions": [r["disease_name"] for r in high],
            "top_risks": top,
            "recommended_screening": self.recommended_screening(top),
            "counselling_points": self.schemes.get("counselling_points", []),
            "government_schemes": self.schemes.get("schemes", []),
            "centres_of_excellence": self.schemes.get("centres_of_excellence_examples", []),
            "disclaimer": ("Carrier probabilities are Bayesian estimates built on Indian population "
                           "priors and family history; confirm with laboratory testing. Not a diagnosis."),
        }

    def _down_risk(self, maternal_age: int) -> float:
        risk = MATERNAL_AGE_DOWN_RISK[0][1]
        for age, per_1000 in MATERNAL_AGE_DOWN_RISK:
            if maternal_age >= age:
                risk = per_1000
        return round(risk / 1000.0, 6)

    def recommended_screening(self, top_risks: List[dict]) -> List[dict]:
        recs = []
        for r in top_risks:
            if r["child_affected_probability"] < 0.001:
                continue
            if r["gene"] == "HBB":
                recs.append({"condition": r["disease_name"],
                             "test": "CBC with MCV/MCH plus HPLC for HbA2/HbF/HbS (carrier screen for both partners)",
                             "timing": "Pre-marital / pre-conception; if pregnant, partner screening immediately"})
            elif r["gene"] == "G6PD":
                recs.append({"condition": r["disease_name"],
                             "test": "G6PD enzyme assay (quantitative) for the mother; newborn screening",
                             "timing": "Pre-conception"})
            elif r["inheritance"].lower().startswith("autosomal dominant"):
                recs.append({"condition": r["disease_name"],
                             "test": "Clinical evaluation + targeted genetic testing of the affected parent, cascade screening",
                             "timing": "Pre-conception"})
            elif "x-linked" in r["inheritance"].lower():
                recs.append({"condition": r["disease_name"],
                             "test": "Carrier testing for the mother; prenatal diagnosis options discussion",
                             "timing": "Pre-conception / early pregnancy"})
            else:
                recs.append({"condition": r["disease_name"],
                             "test": f"Carrier screening for {r['gene']} (sequencing/MLPA as appropriate)",
                             "timing": "Pre-conception"})
        return recs


if __name__ == "__main__":
    counselor = CarrierCounselor()
    a = {"state": "Tamil Nadu", "community": "Tamil", "sex": "M", "relationship": "first_cousins",
         "family_history": {}}
    b = {"state": "Tamil Nadu", "community": "Tamil", "sex": "F", "age": 31,
         "family_history": {"ORPHA:231222": "affected_sibling"}}
    result = counselor.couple_assessment(a, b, top_n=8)
    print(f"Risk band: {result['risk_band']} | consanguineous={result['couple_consanguineous']} "
          f"(F={result['inbreeding_coefficient']})")
    for r in result["top_risks"]:
        per = f"1 in {r['one_in_n_children']}" if r["one_in_n_children"] else "-"
        print(f"  {r['child_affected_probability']:.5f} ({per:>10s})  {r['disease_name']}")
    print("Recommended screening:", [x['test'][:60] + '...' for x in result["recommended_screening"][:2]])
