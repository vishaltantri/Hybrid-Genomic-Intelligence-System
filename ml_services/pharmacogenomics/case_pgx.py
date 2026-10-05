"""Phase 9: case-level pharmacogenomics.

Patient variants -> gene genotype -> diplotype -> predicted phenotype -> drug -> recommendation -> evidence.

Everything is derived from (a) alleles actually called in the patient's variant analysis and (b) the configured
guideline tables in ``data/seeds`` (``cpic_guidelines.csv``, ``pharmgkb_pairs.csv``, ``indian_af.csv``).
Nothing is inferred when a genotype is not available: the gene is reported as "PGx genotype unavailable".
The existing population-inference engine (``PGxEngine``) is reused unchanged.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ml_services.twin import twin_state as ts

SAFETY = ("Pharmacogenomic decision support. Clinical prescribing decisions require qualified clinician review.")
SOURCE_RULES = "Configured guideline table (data/seeds/cpic_guidelines.csv; CPIC-style rules, prototype data)"
SOURCE_PAIRS = "Configured drug-gene evidence table (data/seeds/pharmgkb_pairs.csv)"

STATUS_LABEL = {
    "poor_metabolizer": "Poor metabolizer", "intermediate_metabolizer": "Intermediate metabolizer",
    "normal_metabolizer": "Normal metabolizer", "rapid_metabolizer": "Rapid metabolizer",
    "ultrarapid_metabolizer": "Ultrarapid metabolizer", "deficient": "Deficient", "carrier": "Carrier",
}
STATUS_CODE = {"poor_metabolizer": "PM", "intermediate_metabolizer": "IM", "normal_metabolizer": "NM",
               "rapid_metabolizer": "RM", "ultrarapid_metabolizer": "UM", "deficient": "deficient",
               "carrier": "carrier"}
SEV_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "": 0}


class PgxCaseError(LookupError):
    pass


def _star(allele: str) -> str:
    """'CYP2C19*2' -> '*2'; named alleles (G6PD Mahidol) are returned unchanged."""
    return "*" + allele.split("*", 1)[1] if "*" in allele else allele


def _gene_of(rule_gene: str) -> List[str]:
    return [g.strip() for g in rule_gene.split("+") if g.strip()]


class CasePgx:
    def __init__(self, registry):
        self.registry = registry

    # ------------------------------ genotype ------------------------------

    def _gene_genotypes(self, variants: List[dict]) -> Dict[str, dict]:
        by_gene: Dict[str, List[dict]] = {}
        for v in variants:
            star = v.get("pgx_star_allele")
            if not star:
                continue
            gene = v.get("gene_symbol") or star.split("*")[0].split(" ")[0]
            by_gene.setdefault(gene, []).append(v)
        return {g: self._interpret_gene(g, vs) for g, vs in sorted(by_gene.items())}

    def _interpret_gene(self, gene: str, vs: List[dict]) -> dict:
        alleles = [{"allele": v["pgx_star_allele"], "star": _star(v["pgx_star_allele"]),
                    "function": v.get("pgx_function") or "Not documented", "zygosity": v.get("zygosity") or "Not documented",
                    "variant_id": v["variant_id"], "hgvs": v.get("hgvs_c") or v.get("hgvs") or None} for v in vs]
        zyg = [(a["zygosity"] or "").lower() for a in alleles]
        out = {"gene": gene, "alleles": alleles, "status": None, "phenotype": None, "diplotype": None,
               "diplotype_note": None, "phenotype_note": None, "x_linked": gene in ts._X_LINKED}

        # ---- diplotype: only what the call set supports; no phase is ever inferred ----
        if len(alleles) == 1 and zyg[0] == "homozygous":
            a = alleles[0]["star"]
            out["diplotype"] = f"{a}/{a}"
        elif len(alleles) == 1 and zyg[0] == "hemizygous":
            out["diplotype"] = f"{alleles[0]['star']} (hemizygous)"
        elif len(alleles) == 1 and zyg[0] == "heterozygous":
            out["diplotype"] = f"{alleles[0]['star']}/other"
            out["diplotype_note"] = ("Second allele not reported by the variant analysis (a reference *1 allele cannot be "
                                     "assumed from a variant list alone).")
        else:
            out["diplotype"] = None
            out["diplotype_note"] = "Diplotype/phase cannot be confidently determined from this call set."

        # ---- phenotype from the existing, allele-function based rule ----
        if len(alleles) == 1:
            a = alleles[0]
            status = ts.metabolizer_status(gene, a["function"], a["zygosity"])
            if status is None and gene == "CYP2C19" and (a["function"] or "").lower() == "gof":
                status = {"heterozygous": "rapid_metabolizer", "homozygous": "ultrarapid_metabolizer"}.get((a["zygosity"] or "").lower())
            if status:
                out["status"] = status
                out["phenotype"] = STATUS_LABEL[status]
                if a["zygosity"].lower() == "heterozygous" and "intermediate" in status:
                    out["phenotype_note"] = ("Inferred from one loss-of-function allele; the second allele is not reported, "
                                             "so this assumes the other allele is functional.")
            else:
                out["phenotype_note"] = (f"Phenotype not assigned: {a['allele']} has function '{a['function']}' with zygosity "
                                         f"'{a['zygosity']}'; assignment requires full diplotype activity scoring, which is not configured.")
        else:
            lof = [a for a in alleles if (a["function"] or "").lower() == "lof"]
            if len(lof) >= 2:
                out["phenotype_note"] = ("Multiple loss-of-function alleles reported; phase (cis vs trans) is unavailable, so the "
                                         "metabolizer phenotype cannot be confidently determined.")
            else:
                out["phenotype_note"] = "Phenotype cannot be confidently determined from the reported alleles."
        return out

    # ------------------------------ drug matrix ------------------------------

    def _rules_for(self, gene: str, status: Optional[str]):
        eng = self.registry.pgx
        code = STATUS_CODE.get(status or "")
        hits, other = [], []
        for r in eng.guidelines:
            if gene not in _gene_of(r["gene"]):
                continue
            (hits if code and (r.get("metabolizer_status") or "") == code else other).append(r)
        return hits, other

    def _pair(self, drug: str, gene: str) -> Optional[dict]:
        for p in self.registry.pgx.pairs:
            if p["drug"].lower() == drug.lower() and gene in _gene_of(p["gene"]):
                return p
        return None

    def _matrix(self, genotypes: Dict[str, dict], patient_id: str) -> List[dict]:
        rows: List[dict] = []
        saved = self._saved_evidence(patient_id)
        for gene, g in genotypes.items():
            hits, other = self._rules_for(gene, g["status"])
            seen = set()
            for r in hits:
                drug = r["drug"]
                seen.add(drug.lower())
                pair = self._pair(drug, gene)
                combo = _gene_of(r["gene"])
                rows.append({
                    "drug": drug, "drug_class": r.get("drug_class") or "Not documented",
                    "gene": gene, "genotype": g["diplotype"] or "Not determined", "phenotype": g["phenotype"],
                    "clinical_impact": r.get("phenotype") or None, "risk": r.get("severity_if_ignored") or "Not documented",
                    "recommendation": r.get("recommendation") or "Not documented",
                    "alternatives": [a.strip() for a in (r.get("alternatives") or "").split(";") if a.strip()],
                    "alternatives_source": SOURCE_RULES if r.get("alternatives") else None,
                    "evidence_level": (pair or {}).get("evidence_level") or "Not documented",
                    "evidence_note": (pair or {}).get("annotation_text") or None,
                    "sources": [SOURCE_RULES] + ([SOURCE_PAIRS] if pair else []),
                    "saved_evidence": [{k: v for k, v in e.items() if k != "text"} for e in saved
                                       if gene.lower() in e["text"].lower() or drug.lower() in e["text"].lower()],
                    "also_needs": [{"gene": x, "genotype": "Not analyzed"} for x in combo if x != gene] or None,
                    "status": "Recommendation configured",
                })
            for p in self.registry.pgx.pairs:
                if gene in _gene_of(p["gene"]) and p["drug"].lower() not in seen:
                    seen.add(p["drug"].lower())
                    rows.append({
                        "drug": p["drug"], "drug_class": None, "gene": gene, "genotype": g["diplotype"] or "Not determined",
                        "phenotype": g["phenotype"], "clinical_impact": p.get("annotation_text") or None, "risk": "Not documented",
                        "recommendation": None, "alternatives": [], "alternatives_source": None,
                        "evidence_level": p.get("evidence_level") or "Not documented", "evidence_note": p.get("annotation_text"),
                        "sources": [SOURCE_PAIRS], "saved_evidence": [], "also_needs": None,
                        "status": ("No configured recommendation for this phenotype" if g["phenotype"] else
                                   "No recommendation: phenotype not assigned"),
                    })
        rows.sort(key=lambda r: (-SEV_RANK.get(r["risk"], 0), r["drug"], r["gene"]))
        return rows

    def _saved_evidence(self, patient_id: str) -> List[dict]:
        from backend.app import store
        out = []
        for e in store.evidence_list(patient_id):
            rec = e.get("payload") or {}
            title = rec.get("title") or ""
            out.append({"title": title, "source": e.get("source"), "identifier": rec.get("pmid") or e.get("source_id"),
                        "text": f"{title} {rec.get('abstract') or ''} {e.get('note') or ''}"})
        return out

    # ------------------------------ population / HWE ------------------------------

    def _population(self, gene: str, g: dict, patient: dict) -> Optional[dict]:
        eng = self.registry.pgx
        if not any(r["gene"].upper() == gene.upper() for r in eng.af_rows):
            return None
        a0 = g["alleles"][0]["allele"]
        af = eng.allele_frequency(gene, a0, state=patient.get("state") or "")
        if af["source"] == "not_found":
            return None
        p = af["af"]
        hw = ts_hw(p, g["x_linked"], patient.get("sex") or "")
        return {"allele": af.get("variant") or a0, "allele_frequency": af["af"], "match": af["match"], "source": af["source"],
                "n_samples": af.get("n_samples") or "Not documented", "hwe_expected": {k: round(v, 4) for k, v in hw.items()},
                "note": ("Indian population context only. It describes how common the allele is in a reference cohort; it is "
                         "not this patient's genotype and not an individual risk estimate."),
                "hwe_interpretation": ("Expected Hardy-Weinberg genotype proportions from the reference allele frequency. "
                                       "A population-level expectation, not an individual diagnosis.")}

    def cohort_context(self, gene: str, allele: str) -> dict:
        """Aggregate (no patient identifiers) count of stored analyses that carry this allele."""
        het = hom = n = 0
        for a in self.registry.variants.list_analyses()[:200]:
            full = self.registry.variants.get_analysis(a["analysis_id"])
            n += 1
            for v in full["variants"]:
                if v.get("pgx_star_allele") == allele:
                    z = (v.get("zygosity") or "").lower()
                    hom += z in ("homozygous", "hemizygous")
                    het += z == "heterozygous"
        return {"analyses_scanned": n, "heterozygous": het, "homozygous_or_hemizygous": hom,
                "note": ("Counts of stored analyses reporting this allele. Wild-type individuals cannot be counted from sparse "
                         "variant lists, so an observed-vs-expected Hardy-Weinberg test is not performed.")}

    # ------------------------------ workspace ------------------------------

    def workspace(self, patient_id: str) -> dict:
        try:
            core = self.registry.twin.load_core(patient_id)
        except LookupError as ex:
            raise PgxCaseError(str(ex))
        patient, variants = core["patient"], core["variants"]
        genotypes = self._gene_genotypes(variants)
        if not core["analysis"]:
            return {"patient_id": patient_id, "available": False, "genes": [], "matrix": [], "safety": SAFETY,
                    "note": "PGx genotype unavailable: no variant analysis has been run for this case (Not analyzed)."}
        if not genotypes:
            return {"patient_id": patient_id, "available": False, "genes": [], "matrix": [], "safety": SAFETY,
                    "analysis_id": core["analysis"]["analysis_id"],
                    "note": "PGx genotype unavailable: the variant analysis reports no pharmacogene alleles for this case."}
        matrix = self._matrix(genotypes, patient_id)
        genes = []
        for gene, g in genotypes.items():
            pop = self._population(gene, g, patient)
            cohort = self.cohort_context(gene, g["alleles"][0]["allele"]) if len(g["alleles"]) == 1 else None
            genes.append({**g, "population": pop, "cohort": cohort})
        return {"patient_id": patient_id, "available": True, "analysis_id": core["analysis"]["analysis_id"],
                "state": patient.get("state"), "genes": genes, "matrix": matrix,
                "summary": {"genes": len(genes), "actionable": sum(1 for r in matrix if r["status"] == "Recommendation configured"),
                            "highest_risk": next((r["risk"] for r in matrix if r["status"] == "Recommendation configured"), None)},
                "safety": SAFETY, "sources": [SOURCE_RULES, SOURCE_PAIRS],
                "note": "Genotypes are taken from the case's variant analysis; no allele is inferred."}

    def drug(self, patient_id: str, name: str) -> dict:
        ws = self.workspace(patient_id)
        d = name.strip().lower()
        rows = [r for r in ws["matrix"] if r["drug"].lower() == d]
        eng = self.registry.pgx
        known = any(p["drug"].lower() == d for p in eng.pairs) or any(g["drug"].lower() == d for g in eng.guidelines)
        if not known:
            return {"patient_id": patient_id, "drug": name, "supported": False, "rows": [], "safety": SAFETY,
                    "note": "No PGx rule is configured for this drug (unsupported drug); this is not a statement that no interaction exists."}
        genes = sorted({g for r in eng.guidelines if r["drug"].lower() == d for g in _gene_of(r["gene"])} |
                       {g for p in eng.pairs if p["drug"].lower() == d for g in _gene_of(p["gene"])})
        have = {r["gene"] for r in rows}
        missing = [{"gene": g, "genotype": "PGx genotype unavailable"} for g in genes if g not in have]
        return {"patient_id": patient_id, "drug": name, "supported": True, "rows": rows, "genes_without_genotype": missing,
                "safety": SAFETY, "available": ws["available"], "note": ws.get("note")}

    # ------------------------------ integrations ------------------------------

    def report_section(self, patient_id: str) -> dict:
        ws = self.workspace(patient_id)
        if not ws["available"]:
            return {"available": False, "note": ws["note"]}
        return {"available": True, "genotypes": [{"gene": g["gene"], "diplotype": g["diplotype"], "phenotype": g["phenotype"],
                                                    "alleles": [a["allele"] for a in g["alleles"]], "notes": [n for n in (g["diplotype_note"], g["phenotype_note"]) if n]}
                                                   for g in ws["genes"]],
                "findings": [{k: r[k] for k in ("gene", "drug", "genotype", "phenotype", "risk", "recommendation", "evidence_level", "sources", "status")}
                             for r in ws["matrix"]],
                "limitations": ["Genotypes derive only from reported variants; unreported second alleles are not assumed.",
                                "Rules are configured prototype guideline tables; confirm with clinical PGx testing.", SAFETY]}

    def ai_context(self, patient_id: str) -> dict:
        ws = self.workspace(patient_id)
        lines = [f"PGX CONTEXT ({SAFETY})"]
        if not ws["available"]:
            lines.append(ws["note"])
        for g in ws.get("genes", []):
            lines.append(f"- {g['gene']}: alleles {', '.join(a['allele'] + ' (' + a['zygosity'] + ')' for a in g['alleles'])}; "
                         f"diplotype {g['diplotype'] or 'not determined'}; phenotype {g['phenotype'] or 'not assigned'}"
                         + (f"; note: {g['phenotype_note']}" if g["phenotype_note"] else ""))
        for r in ws.get("matrix", []):
            if r["status"] == "Recommendation configured":
                lines.append(f"- {r['drug']} / {r['gene']}: {r['risk']} risk; rule: {r['recommendation']} (evidence {r['evidence_level']})")
        lines.append("Do not invent recommendations beyond these configured rules.")
        return {"text": "\n".join(lines),
                "citations": [{"source_type": "pgx", "identifier": f"{patient_id}:pgx", "title": "Case pharmacogenomics workspace",
                               "summary": "Genotype-derived PGx findings from configured guideline tables", "reliability": "configured_rules"}],
                "summary": {"pgx": True}}


def ts_hw(p: float, x_linked: bool, sex: str) -> dict:
    from ml_services.pharmacogenomics.pgx_engine import hardy_weinberg
    return hardy_weinberg(p, x_linked=x_linked, sex=sex)
