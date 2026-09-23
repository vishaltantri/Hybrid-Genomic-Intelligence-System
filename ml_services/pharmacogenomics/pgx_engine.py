"""Module 5: Pharmacogenomics Risk Alert Engine.

Patent claim #4: population-stratified pharmacogenomic risk inference *without*
genetic testing — inferring drug-gene risk from state + community + prescribed drugs.

Chain of reasoning
------------------
1. Allele frequency for the variant in the patient's state/ethnicity (IndiGenomes /
   GenomeIndia / gnomAD-SAS merged table).
2. Hardy-Weinberg -> probability of each genotype (wild-type / het / homozygous or
   hemizygous) -> probability of each metabolizer phenotype (CPIC definitions).
3. CPIC guideline lookup -> risk severity + recommendation + alternatives.
4. If an actual genotype/lab result is supplied (e.g. uploaded PGx panel), it
   overrides the inferred distribution entirely.

Outputs are explicitly probabilistic: "given your state and community, your chance of
being a CYP2C19 poor/intermediate metabolizer is X% — this drug may not work".
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ml_services.config import SEEDS_DIR
from ml_services.etl.population_parser import _first_existing  # reuse path helper
from ml_services.utils import read_csv_rows

AF_PATHS = ["indian_af.csv"]
PHARMGKB = SEEDS_DIR / "pharmgkb_pairs.csv"
CPIC = SEEDS_DIR / "cpic_guidelines.csv"
DRUGS = SEEDS_DIR / "drugs.csv"

SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}

# States map to the biogeographic/linguistic groupings used by IndiGenomes/GenomeIndia so a
# patient's state can be resolved against region-level allele frequencies.
STATE_TO_REGION = {
    "Tamil Nadu": "South India", "Kerala": "South India", "Karnataka": "South India",
    "Andhra Pradesh": "South India", "Telangana": "South India", "Puducherry": "South India",
    "Lakshadweep": "South India", "Andaman and Nicobar Islands": "South India",
    "Maharashtra": "Central India tribal", "Madhya Pradesh": "Central India tribal",
    "Chhattisgarh": "Central India tribal", "Odisha": "Central India tribal",
    "Jharkhand": "Central India tribal", "Goa": "South India",
    "Punjab": "North India", "Haryana": "North India", "Delhi": "North India",
    "Himachal Pradesh": "North India", "Uttarakhand": "North India",
    "Uttar Pradesh": "North India", "Bihar": "North India", "Rajasthan": "North India",
    "Jammu and Kashmir": "North India", "Ladakh": "North India", "Chandigarh": "North India",
    "Gujarat": "North India", "Dadra and Nagar Haveli and Daman and Diu": "North India",
    "Assam": "Northeast India", "Arunachal Pradesh": "Northeast India",
    "Manipur": "Northeast India", "Meghalaya": "Northeast India",
    "Mizoram": "Northeast India", "Nagaland": "Northeast India", "Tripura": "Northeast India",
    "Sikkim": "Northeast India", "West Bengal": "East India",
}

# Which grouped labels in the AF table correspond to which state (used for the tribal belt)
HIGH_TRIBAL_STATES = {"Chhattisgarh", "Odisha", "Jharkhand", "Madhya Pradesh", "Maharashtra"}


def hardy_weinberg(p: float, x_linked: bool = False, sex: str = "") -> Dict[str, float]:
    """Genotype distribution from allele frequency p (p = risk allele frequency)."""
    q = 1.0 - p
    if x_linked:
        if (sex or "").upper().startswith("F"):
            # females: homozygous deficient (p^2), carrier (2pq), wild type (q^2)
            return {"hom_risk": p * p, "het": 2 * p * q, "hom_wildtype": q * q}
        # males (default for X-linked screening): hemizygous
        return {"hemizygous_risk": p, "hemizygous_wildtype": q}
    return {"hom_risk": p * p, "het": 2 * p * q, "hom_wildtype": q * q}


class PGxEngine:
    def __init__(self):
        self.af_rows = read_csv_rows(_first_existing([SEEDS_DIR / p for p in AF_PATHS]))
        self.pairs = read_csv_rows(PHARMGKB)
        self.guidelines = read_csv_rows(CPIC)
        self.drugs = {r["drug_name"].lower(): r for r in read_csv_rows(DRUGS)}
        self.gene_drug_index: Dict[str, List[dict]] = {}
        for p in self.pairs:
            for g in p["gene"].split("+"):
                self.gene_drug_index.setdefault(g.strip(), []).append(p)
        for g in self.guidelines:
            for gg in g["gene"].split("+"):
                self.gene_drug_index.setdefault(gg.strip(), []).append(g)

    # ------------------------------ allele frequency ------------------------------

    def allele_frequency(self, gene: str, variant: str = "", state: str = "", ethnicity: str = "") -> dict:
        """Find the best-matching AF row: exact state > ethnicity > pan-Indian.

        Combined gene strings such as "CYP2C9+CYP4F2" fall back to the first member gene.
        """
        candidates = [r for r in self.af_rows if r["gene"].upper() == gene.upper()]
        if not candidates and "+" in gene:
            first = gene.split("+")[0].strip()
            candidates = [r for r in self.af_rows if r["gene"].upper() == first.upper()]
        if variant:
            near = [r for r in candidates if variant.lower() in (r["variant_or_allele"] or "").lower()
                    or (r["variant_or_allele"] or "").lower() in variant.lower()]
            if near:
                candidates = near
        if not candidates:
            return {"af": 0.0, "source": "not_found", "n_samples": "", "match": "none"}
        # 1) exact state/region text in the AF table
        if state:
            for r in candidates:
                if state.lower() in (r.get("state_or_region") or "").lower():
                    return {"af": float(r["af_indian"] or 0), "source": r.get("source", ""),
                            "n_samples": r.get("n_samples", ""), "match": "state",
                            "variant": r["variant_or_allele"], "ethnicity": r.get("ethnicity", "")}
            # 2) resolve the state to its biogeographic region (IndiGenomes/GenomeIndia grouping)
            region = STATE_TO_REGION.get(state)
            if region:
                for r in candidates:
                    if (r.get("state_or_region") or "").lower() == region.lower():
                        return {"af": float(r["af_indian"] or 0), "source": r.get("source", ""),
                                "n_samples": r.get("n_samples", ""), "match": "region",
                                "resolved_region": region, "variant": r["variant_or_allele"],
                                "ethnicity": r.get("ethnicity", "")}
            if state in HIGH_TRIBAL_STATES:
                for r in candidates:
                    if "tribal" in (r.get("ethnicity") or "").lower():
                        return {"af": float(r["af_indian"] or 0), "source": r.get("source", ""),
                                "n_samples": r.get("n_samples", ""), "match": "tribal_belt",
                                "variant": r["variant_or_allele"], "ethnicity": r.get("ethnicity", "")}
        if ethnicity:
            for r in candidates:
                if ethnicity.lower() in (r.get("ethnicity") or "").lower():
                    return {"af": float(r["af_indian"] or 0), "source": r.get("source", ""),
                            "n_samples": r.get("n_samples", ""), "match": "ethnicity",
                            "variant": r["variant_or_allele"], "ethnicity": r.get("ethnicity", "")}
        pan = [r for r in candidates if "pan-indian" in (r.get("ethnicity") or "").lower()]
        row = (pan or candidates)[0]
        return {"af": float(row["af_indian"] or 0), "source": row.get("source", ""),
                "n_samples": row.get("n_samples", ""), "match": "pan_indian",
                "variant": row["variant_or_allele"], "ethnicity": row.get("ethnicity", "")}

    # ------------------------------ phenotype inference ------------------------------

    def infer_metabolizer_probabilities(self, gene: str, state: str = "", ethnicity: str = "",
                                        variant: str = "", x_linked: bool = False, sex: str = "") -> dict:
        af = self.allele_frequency(gene, variant, state, ethnicity)
        p = af["af"]
        hw = hardy_weinberg(p, x_linked=x_linked, sex=sex)
        if x_linked:
            affected = hw["hom_risk"] if (sex or "").upper().startswith("F") else hw["hemizygous_risk"]
            carrier = hw.get("het", 0.0)
            probs = {"deficient": round(affected, 4), "carrier": round(carrier, 4),
                     "normal": round(max(0.0, 1 - affected - carrier), 4)}
        else:
            # LoF risk allele: hom_risk -> poor metabolizer; het -> intermediate
            probs = {
                "poor_metabolizer": round(hw["hom_risk"], 4),
                "intermediate_metabolizer": round(hw["het"], 4),
                "normal_metabolizer": round(hw["hom_wildtype"], 4),
            }
        return {"gene": gene, **af, "genotype_distribution": hw, "phenotype_probabilities": probs}

    # ------------------------------ alerting ------------------------------

    def check_drugs(self, drugs: List[str], state: str = "", ethnicity: str = "",
                    known_genotypes: Optional[Dict[str, str]] = None, age: Optional[int] = None,
                    sex: str = "") -> dict:
        """Screen a prescription list against PGx rules for this patient's inferred population."""
        known_genotypes = known_genotypes or {}
        alerts: List[dict] = []
        uninvolved: List[str] = []

        for drug in drugs:
            d_lower = drug.strip().lower()
            rule_matches = [g for gene, rows in self.gene_drug_index.items() for g in rows
                            if (g.get("drug", "") or "").lower() == d_lower]
            if not rule_matches:
                uninvolved.append(drug)
                continue

            for rule in rule_matches:
                gene = (rule.get("gene") or "").strip()
                if not gene:
                    continue
                x_linked = gene.upper() in {"G6PD"}
                inference = self.infer_metabolizer_probabilities(
                    gene, state=state, ethnicity=ethnicity, x_linked=x_linked, sex=sex
                )
                probs = inference["phenotype_probabilities"]

                # If genotype is known, collapse the distribution onto the truth
                known = known_genotypes.get(gene) or known_genotypes.get(drug)
                if known:
                    probs = {k: (1.0 if k == known else 0.0) for k in probs}
                    inference["assumption"] = "known_genotype_override"
                else:
                    inference["assumption"] = "inferred_from_population"

                risk_status, risk_prob = self._riskiest_status(gene, probs, x_linked)
                severity = rule.get("severity_if_ignored") or self._default_severity(gene, risk_status)
                if severity is None:
                    continue

                alerts.append({
                    "drug": drug,
                    "gene": gene,
                    "inferred_status": risk_status,
                    "probability_of_risk_status": round(risk_prob, 4),
                    "phenotype_probabilities": probs,
                    "allele_frequency": inference["af"],
                    "af_match": inference["match"],
                    "af_source": inference.get("source", ""),
                    "evidence_level": rule.get("evidence_level", ""),
                    "severity": severity,
                    "recommendation": rule.get("recommendation", "") or rule.get("annotation", ""),
                    "alternatives": [a.strip() for a in (rule.get("alternatives") or "").split(";") if a.strip()],
                    "alternative_drugs_not_affected": self._alternatives_for(gene),
                    "patient_explanation_hi": self._explain_hi(drug, gene, risk_status, risk_prob, state),
                    "assumption": inference["assumption"],
                })

        # One alert per (drug, gene): keep the most severe, then highest probability
        deduped: Dict[tuple, dict] = {}
        for a in alerts:
            key = (a["drug"].lower(), a["gene"])
            cur = deduped.get(key)
            if cur is None or (SEVERITY_ORDER.get(a["severity"], 0), a["probability_of_risk_status"]) > (
                    SEVERITY_ORDER.get(cur["severity"], 0), cur["probability_of_risk_status"]):
                deduped[key] = a
        alerts = list(deduped.values())
        alerts.sort(key=lambda a: (SEVERITY_ORDER.get(a["severity"], 0), a["probability_of_risk_status"]), reverse=True)
        return {
            "patient": {"state": state, "ethnicity": ethnicity, "age": age, "sex": sex,
                        "known_genotypes": known_genotypes},
            "alerts": alerts,
            "drugs_without_pgx_rule": uninvolved,
            "summary": self._summary(alerts),
            "disclaimer": ("Population-level inference only. Confirm with PGx testing before changing therapy. "
                           "Allele frequencies are literature-derived estimates for prototype use."),
        }

    def _riskiest_status(self, gene: str, probs: Dict[str, float], x_linked: bool):
        if x_linked:
            deficient = probs.get("deficient", 0.0)
            carrier = probs.get("carrier", 0.0)
            if deficient >= carrier:
                return ("deficient", deficient)
            return ("carrier", carrier)
        pm = probs.get("poor_metabolizer", 0.0)
        im = probs.get("intermediate_metabolizer", 0.0)
        if pm >= im:
            return ("poor_metabolizer", pm)
        return ("intermediate_metabolizer", im)

    def _default_severity(self, gene: str, status: str) -> Optional[str]:
        if "poor" in status or status == "deficient":
            return "high"
        if "intermediate" in status:
            return "medium"
        return "low"

    def _alternatives_for(self, gene: str) -> List[str]:
        alts = []
        for g in self.guidelines:
            if g["gene"].split("+")[0].strip() == gene and g.get("alternatives"):
                alts.extend(a.strip() for a in g["alternatives"].split(";") if a.strip())
        return sorted(set(alts))

    def _explain_hi(self, drug: str, gene: str, status: str, prob: float, state: str) -> str:
        status_hi = {"poor_metabolizer": "धीमे metaboliser (PM)",
                     "intermediate_metabolizer": "मध्यम metaboliser (IM)",
                     "normal_metabolizer": "सामान्य metaboliser (NM)",
                     "carrier": "वाहक (carrier)",
                     "deficient": "G6PD कमी"}.get(status, status)
        state_part = f"{state} में" if state else "भारतीय आबादी में"
        return (f"{state_part} {gene} का यह रूप लगभग {prob*100:.0f}% लोगों में पाया जाता है। "
                f"आपके लिए {drug} देने पर जोखिम {status_hi} हो सकता है — "
                f"डॉक्टर से वैकल्पिक दवा की सलाह लें। (यह अनुमानित जोखिम है, जीन जाँच से पुष्टि करें।)")

    def _summary(self, alerts: List[dict]) -> dict:
        counts = {}
        for a in alerts:
            counts[a["severity"]] = counts.get(a["severity"], 0) + 1
        return {
            "total_alerts": len(alerts),
            "critical": counts.get("critical", 0),
            "high": counts.get("high", 0),
            "medium": counts.get("medium", 0),
            "low": counts.get("low", 0),
            "headline": ("No pharmacogenomic alerts for this prescription."
                         if not alerts else
                         f"{counts.get('critical', 0)} critical and {counts.get('high', 0)} high-severity "
                         f"drug-gene alerts for this patient profile."),
        }

    def drug_gene_table(self) -> List[dict]:
        """Coverage table for dashboards: gene -> drugs -> Indian AF."""
        rows = []
        seen = set()
        for gene in sorted(self.gene_drug_index):
            af = self.allele_frequency(gene)
            for g in self.gene_drug_index[gene]:
                drug = g.get("drug", "")
                key = (gene, drug)
                if key in seen or not drug:
                    continue
                seen.add(key)
                rows.append({
                    "gene": gene,
                    "drug": drug,
                    "evidence_level": g.get("evidence_level", ""),
                    "af_indian": af["af"],
                    "india_note": g.get("india_relevance", ""),
                    "severity": g.get("severity_if_ignored", ""),
                })
        return rows


if __name__ == "__main__":
    engine = PGxEngine()
    demo = engine.check_drugs(
        ["clopidogrel", "warfarin", "codeine", "primaquine", "paracetamol"],
        state="Andhra Pradesh", ethnicity="Dravidian", age=58,
    )
    print(demo["summary"]["headline"])
    for a in demo["alerts"]:
        print(f"  [{a['severity']:8s}] {a['drug']:14s} / {a['gene']:12s} "
              f"{a['inferred_status']:26s} p={a['probability_of_risk_status']:.3f} "
              f"(AF={a['allele_frequency']:.3f}, {a['af_match']})")
    print("\nHindi patient explanation (top alert):")
    print(" ", demo["alerts"][0]["patient_explanation_hi"] if demo["alerts"] else "n/a")
    print(f"\nCoverage rows: {len(engine.drug_gene_table())}")
