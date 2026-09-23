"""Punnett square simulator (Module 6).

Supports autosomal recessive, autosomal dominant and X-linked recessive crosses,
plus probability-based crosses when parent genotypes are unknown (risk from carrier
frequency), and a Monte-Carlo cross-check used by the test suite.
"""
from __future__ import annotations

import random
from typing import Dict, List, Tuple

ALLELES = ("A", "a")  # A = wild type (dominant), a = disease allele


def gametes(genotype: str) -> List[str]:
    if len(genotype) != 2:
        raise ValueError(f"genotype must be two alleles, got {genotype!r}")
    return [genotype[0], genotype[1]]


def punnett_square(father: str, mother: str) -> Dict:
    """Cross two diploid genotypes -> grid + genotype/phenotype distribution."""
    fg, mg = gametes(father), gametes(mother)
    grid = [[f + m for m in mg] for f in fg]
    flat = [g for row in grid for g in row]
    counts: Dict[str, int] = {}
    for g in flat:
        counts["".join(sorted(g, key=lambda a: (a != "A", a)))] = counts.get(
            "".join(sorted(g, key=lambda a: (a != "A", a))), 0
        ) + 1
    total = len(flat)
    genotypes = {k: round(v / total, 4) for k, v in counts.items()}
    phenotypes = {
        "affected": round(sum(v for k, v in counts.items() if "aa" in k) / total, 4),
        "carrier": round(sum(v for k, v in counts.items() if k == "Aa") / total, 4),
        "unaffected_non_carrier": round(counts.get("AA", 0) / total, 4),
    }
    return {"father": father, "mother": mother, "grid": grid, "genotypes": genotypes, "phenotypes": phenotypes}


def x_linked_cross(mother: str, father: str = "XAY") -> Dict:
    """Simplified X-linked recessive cross.

    mother in {XX, Xx, xx}; father in {XAY (unaffected), XaY / xY (affected)}.
    Comparison is case-sensitive: the affected male allele is spelled lowercase `a`/`x`.
    Returns affected probabilities split by child sex (the clinically relevant output).
    """
    mother_carrier_status = {"XX": "wildtype", "Xx": "carrier", "xx": "affected"}.get(mother, "unknown")
    father_affected = father.strip() in ("xY", "XaY")

    # Sons receive the father's Y, so their risk depends only on the mother's X.
    if mother == "XX":
        sons_affected = 0.0
    elif mother == "Xx":
        sons_affected = 0.5
    elif mother == "xx":
        sons_affected = 1.0
    else:
        sons_affected = 0.0

    # Daughters receive one X from each parent.
    if mother == "xx":
        daughters_affected = 1.0 if father_affected else 0.0
        daughters_carrier = 0.0 if father_affected else 1.0
    elif mother == "Xx":
        daughters_affected = 0.5 if father_affected else 0.0
        daughters_carrier = 0.5 if not father_affected else 0.5
    else:  # mother XX
        daughters_affected = 0.0
        daughters_carrier = 1.0 if father_affected else 0.0
    return {
        "mode": "X-linked recessive",
        "mother": mother,
        "mother_status": mother_carrier_status,
        "father": father,
        "sons_affected_probability": sons_affected,
        "daughters_affected_probability": daughters_affected,
        "daughters_carrier_probability": daughters_carrier,
    }


AR_CARRIER_X_CARRIER = punnett_square("Aa", "Aa")


def offspring_risk_from_carrier_probs(p_a: float, p_b: float, mode: str = "autosomal recessive",
                                      inbreeding_coefficient: float = 0.0) -> Dict[str, float]:
    """Offspring risk when each parent's carrier probability is uncertain.

    Autosomal recessive:
        P(both carriers) = pA*pB*(1-F) + F*(pA+pB)/2      (F = inbreeding coefficient)
        P(affected child) = 0.25 * P(both carriers)
    The F term models consanguinity: in an inbred union the second partner may carry the
    same ancestral allele, so risk rises even when population carrier rates are modest.
    """
    if mode == "autosomal dominant":
        # p_x here means "probability parent is affected (or will transmit)"
        p_affected_parent = max(p_a, p_b)
        return {
            "both_carriers_probability": round(p_affected_parent, 4),
            "affected_child_probability": round(0.5 * p_affected_parent, 4),
            "carrier_child_probability": 0.0,
            "mode_note": "Dominant: 50% transmission risk per pregnancy if a parent is affected.",
        }
    both = p_a * p_b * (1 - inbreeding_coefficient) + inbreeding_coefficient * ((p_a + p_b) / 2)
    both = min(max(both, 0.0), 1.0)
    affected = 0.25 * both
    carrier_child = 0.5 * both
    return {
        "both_carriers_probability": round(both, 4),
        "affected_child_probability": round(affected, 4),
        "carrier_child_probability": round(carrier_child, 4),
        "unaffected_child_probability": round(1 - affected - carrier_child, 4),
        "inbreeding_coefficient": inbreeding_coefficient,
        "mode_note": "Autosomal recessive: 25% of children affected when both parents are carriers.",
    }


def simulate_offspring(p_a: float, p_b: float, n: int = 20000, seed: int = 5, inbreeding_coefficient: float = 0.0) -> Dict[str, float]:
    """Monte-Carlo cross-check of offspring_risk_from_carrier_probs."""
    analytic = offspring_risk_from_carrier_probs(p_a, p_b, "autosomal recessive", inbreeding_coefficient)
    rng = random.Random(seed)
    affected = 0
    for _ in range(n):
        carrier_a = rng.random() < p_a
        if rng.random() < inbreeding_coefficient:
            # identical-by-descent event: partner shares carrier_a's ancestral allele
            carrier_b = carrier_a
        else:
            carrier_b = rng.random() < p_b
        if carrier_a and carrier_b and rng.random() < 0.25:
            affected += 1
    empirical = affected / n
    return {
        "analytic_affected_probability": analytic["affected_child_probability"],
        "simulated_affected_probability": round(empirical, 4),
        "n_simulations": n,
        "abs_difference": round(abs(empirical - analytic["affected_child_probability"]), 4),
    }


if __name__ == "__main__":
    print("Carrier x carrier:", AR_CARRIER_X_CARRIER["phenotypes"], AR_CARRIER_X_CARRIER["grid"])
    print("Unknown carriers (2% each):", offspring_risk_from_carrier_probs(0.02, 0.02))
    print("First cousins (F=0.0625):", offspring_risk_from_carrier_probs(0.02, 0.02, inbreeding_coefficient=0.0625))
    print("Simulation check:", simulate_offspring(0.2, 0.2))
    print("X-linked carrier mother (healthy father):", x_linked_cross("Xx"))
    print("X-linked carrier mother (affected father):", x_linked_cross("Xx", "XaY"))
