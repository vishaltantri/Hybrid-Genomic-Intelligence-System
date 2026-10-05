"""Variant Prioritizer (Phase 3B).

Combines:
1. ACMG/AMP tier (Pathogenic > Likely pathogenic > VUS > Likely benign > Benign)
2. Phenotype similarity (patient HPO terms vs Orphanet disease gene phenotypes in KG)
3. Population frequency rarity in Indian cohorts (IndiGenomes + GenomeIndia)
4. Functional consequence impact (null > missense > synonymous)
5. Clinical significance from ClinVar

Generates a unified composite Priority Score (0-100) and ranking for clinical review.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ml_services.variants.acmg_engine import ACMGClassificationResult
from ml_services.variants.annotator import VariantAnnotation
from ml_services.variants.vcf_parser import VariantRecord


@dataclass
class PrioritizedVariant:
    rank: int
    variant_id: str
    chrom: str
    pos: int
    ref: str
    alt: str
    genotype: str
    zygosity: str
    depth: Optional[int]
    
    # Annotation
    gene_symbol: Optional[str]
    hgvs: Optional[str]
    cdna: Optional[str]
    protein: Optional[str]
    consequence: str
    exon: Optional[str]
    
    # Clinical & Knowledge Graph
    disease_id: Optional[str]
    disease_name: Optional[str]
    inheritance: Optional[str]
    clinvar_id: Optional[str]
    clinvar_significance: Optional[str]
    
    # Allele frequencies
    af_indian: Optional[float]
    af_sas: Optional[float]
    af_global: Optional[float]
    af_source: Optional[str]
    
    # In silico & PGx
    cadd_phred: Optional[float]
    revel_score: Optional[float]
    pgx_star_allele: Optional[str]
    pgx_function: Optional[str]
    
    # ACMG / AMP evaluation
    acmg_classification: str
    acmg_score: int
    criteria_met_pathogenic: List[str]
    criteria_met_benign: List[str]
    acmg_explanation: str
    all_criteria: List[Dict[str, Any]]
    
    # Composite prioritization
    priority_score: float             # 0 to 100
    priority_tier: str                # "Tier 1: High Clinical Actionability", "Tier 2: Candidate Variant", "Tier 3: Low Actionability"
    phenotype_match_score: float      # 0 to 100
    matched_hpo_terms: List[str]      # HPO IDs or names matching disease profile
    priority_rationale: List[str]     # Key clinical points explaining ranking


class VariantPrioritizer:
    """Ranks variants by blending ACMG criteria, Indian frequency rarity, and KG phenotype overlap."""

    def __init__(self, graph: Optional[Any] = None):
        self.graph = graph

    def prioritize(
        self,
        variants: List[Tuple[VariantRecord, VariantAnnotation, ACMGClassificationResult]],
        patient_hpo_ids: Optional[List[str]] = None,
    ) -> List[PrioritizedVariant]:
        patient_hpos = set(patient_hpo_ids or [])
        scored_items: List[PrioritizedVariant] = []

        for record, ann, acmg in variants:
            # 1. ACMG Component Score (0 - 45 pts)
            acmg_points = 0.0
            if acmg.classification == "Pathogenic":
                acmg_points = 45.0
            elif acmg.classification == "Likely pathogenic":
                acmg_points = 35.0
            elif acmg.classification == "Uncertain significance":
                acmg_points = 15.0
            elif acmg.classification == "Likely benign":
                acmg_points = 5.0
            else: # Benign
                acmg_points = 0.0

            # 2. Phenotype Match Component (0 - 30 pts)
            pheno_points = 0.0
            matched_hpos = []
            if patient_hpos and ann.disease_id and self.graph:
                # Look up disease phenotypes in Knowledge Graph
                disease_phenos = {
                    e["dst"] for e in self.graph.edges_from(ann.disease_id, "HAS_PHENOTYPE")
                }
                overlap = patient_hpos.intersection(disease_phenos)
                if overlap:
                    pheno_fraction = len(overlap) / max(len(patient_hpos), 1)
                    pheno_points = min(30.0, 10.0 + (pheno_fraction * 20.0))
                    matched_hpos = list(overlap)
                else:
                    # Partial credit if disease is causal for gene
                    pheno_points = 5.0
            elif patient_hpos and ann.disease_id:
                pheno_points = 15.0
                matched_hpos = list(patient_hpos)[:2]

            # 3. Population Rarity in India Component (0 - 15 pts)
            rarity_points = 0.0
            max_af = max([x for x in (ann.af_indian, ann.af_sas, ann.af_global) if x is not None], default=None)
            if max_af is None or max_af == 0.0:
                rarity_points = 15.0
            elif max_af < 0.0001:
                rarity_points = 13.0
            elif max_af < 0.001:
                rarity_points = 10.0
            elif max_af < 0.01:
                rarity_points = 5.0
            else:
                rarity_points = 0.0

            # 4. Consequence Severity (0 - 10 pts)
            cons_points = 0.0
            c_low = ann.consequence.lower()
            if any(x in c_low for x in ("stop_gained", "frameshift", "splice_donor", "splice_acceptor")):
                cons_points = 10.0
            elif "missense" in c_low or "inframe" in c_low:
                cons_points = 7.0
            elif "splice" in c_low:
                cons_points = 5.0
            elif "synonymous" in c_low:
                cons_points = 1.0

            # Total Priority Score (0 - 100)
            total_score = min(100.0, acmg_points + pheno_points + rarity_points + cons_points)

            # Actionability Tier
            if total_score >= 65.0:
                tier = "Tier 1: High Clinical Actionability"
            elif total_score >= 35.0:
                tier = "Tier 2: Candidate Variant"
            else:
                tier = "Tier 3: Low Actionability"

            # Clinical Rationale statements
            rationale: List[str] = []
            if acmg.classification in ("Pathogenic", "Likely pathogenic"):
                rationale.append(f"ACMG {acmg.classification}: Meets {', '.join(acmg.criteria_summary.get('met_pathogenic', []))}")
            if ann.clinical_significance:
                rationale.append(f"ClinVar record classified as {ann.clinical_significance}")
            if matched_hpos:
                rationale.append(f"Overlaps with {len(matched_hpos)} clinical HPO phenotype(s) of {ann.disease_name or ann.gene_symbol}")
            if rarity_points >= 10.0:
                rationale.append(f"Rare in Indian reference datasets (AF = {ann.af_indian if ann.af_indian is not None else 'Unobserved'})")
            if ann.pgx_star_allele:
                rationale.append(f"Pharmacogenomic allele: {ann.pgx_star_allele} ({ann.pgx_function or 'altered metabolism'})")

            # Format raw criteria for detail drawer
            criteria_dicts = [
                {
                    "code": c.code,
                    "category": c.category,
                    "applied_strength": c.applied_strength,
                    "status": c.status,
                    "description": c.description,
                    "evidence": c.evidence,
                    "source": c.source,
                }
                for c in acmg.criteria_met
            ]

            scored_items.append(PrioritizedVariant(
                rank=0,  # assigned after sorting
                variant_id=record.variant_id,
                chrom=record.norm_chrom,
                pos=record.norm_pos,
                ref=record.norm_ref,
                alt=record.norm_alt,
                genotype=record.genotype,
                zygosity=record.zygosity,
                depth=record.depth,
                gene_symbol=ann.gene_symbol,
                hgvs=ann.hgvs,
                cdna=ann.cdna,
                protein=ann.protein,
                consequence=ann.consequence,
                exon=ann.exon,
                disease_id=ann.disease_id,
                disease_name=ann.disease_name,
                inheritance=ann.inheritance,
                clinvar_id=ann.clinvar_id,
                clinvar_significance=ann.clinical_significance,
                af_indian=ann.af_indian,
                af_sas=ann.af_sas,
                af_global=ann.af_global,
                af_source=ann.af_source,
                cadd_phred=ann.cadd_phred,
                revel_score=ann.revel_score,
                pgx_star_allele=ann.pgx_star_allele,
                pgx_function=ann.pgx_function,
                acmg_classification=acmg.classification,
                acmg_score=acmg.acmg_score,
                criteria_met_pathogenic=acmg.criteria_summary.get("met_pathogenic", []),
                criteria_met_benign=acmg.criteria_summary.get("met_benign", []),
                acmg_explanation=acmg.rules_applied_explanation,
                all_criteria=criteria_dicts,
                priority_score=round(total_score, 1),
                priority_tier=tier,
                phenotype_match_score=round((pheno_points / 30.0) * 100, 1),
                matched_hpo_terms=matched_hpos,
                priority_rationale=rationale,
            ))

        # Sort descending by priority score
        scored_items.sort(key=lambda x: x.priority_score, reverse=True)

        # Assign 1-indexed ranks
        for i, item in enumerate(scored_items):
            item.rank = i + 1

        return scored_items


# ---------------------------------------------------------------------------
# Re-scoring helpers (Phase 3D Digital Twin scenarios)
#
# `VariantPrioritizer.prioritize` is the source of truth for the composite score. These
# helpers expose its ACMG and phenotype components so a scenario can re-score an already
# analysed variant when only the classification or the patient's HPO set changes. The
# rarity and consequence components do not depend on either input, so they are carried over
# from the stored score. tests/test_digital_twin.py asserts these helpers reproduce the
# stored scores exactly, so any change to `prioritize` that breaks parity fails loudly.
# ---------------------------------------------------------------------------

ACMG_POINTS = {
    "Pathogenic": 45.0,
    "Likely pathogenic": 35.0,
    "Uncertain significance": 15.0,
    "Likely benign": 5.0,
    "Benign": 0.0,
}


def tier_for_score(score: float) -> str:
    if score >= 65.0:
        return "Tier 1: High Clinical Actionability"
    if score >= 35.0:
        return "Tier 2: Candidate Variant"
    return "Tier 3: Low Actionability"


def phenotype_points(graph: Optional[Any], disease_id: Optional[str], patient_hpos: List[str]) -> float:
    """Phenotype-overlap component (0-30) exactly as computed in `prioritize`."""
    hpos = set(patient_hpos or [])
    if not (hpos and disease_id):
        return 0.0
    if graph:
        disease_phenos = {e["dst"] for e in graph.edges_from(disease_id, "HAS_PHENOTYPE")}
        overlap = hpos & disease_phenos
        if overlap:
            return min(30.0, 10.0 + (len(overlap) / max(len(hpos), 1)) * 20.0)
        return 5.0
    return 15.0


def rarity_points(af_indian: Optional[float], af_sas: Optional[float], af_global: Optional[float]) -> float:
    """Indian-population rarity component (0-15) exactly as computed in `prioritize`."""
    max_af = max([x for x in (af_indian, af_sas, af_global) if x is not None], default=None)
    if max_af is None or max_af == 0.0:
        return 15.0
    if max_af < 0.0001:
        return 13.0
    if max_af < 0.001:
        return 10.0
    if max_af < 0.01:
        return 5.0
    return 0.0


def consequence_points(consequence: str) -> float:
    """Functional-consequence component (0-10) exactly as computed in `prioritize`."""
    c_low = (consequence or "").lower()
    if any(x in c_low for x in ("stop_gained", "frameshift", "splice_donor", "splice_acceptor")):
        return 10.0
    if "missense" in c_low or "inframe" in c_low:
        return 7.0
    if "splice" in c_low:
        return 5.0
    if "synonymous" in c_low:
        return 1.0
    return 0.0


def composite_score(graph: Optional[Any], variant: Dict[str, Any], patient_hpos: List[str],
                    classification: Optional[str] = None) -> float:
    """Recompute a stored variant's composite priority score for an HPO set / ACMG class."""
    cls = classification or variant["acmg_classification"]
    total = (ACMG_POINTS.get(cls, 0.0)
             + phenotype_points(graph, variant.get("disease_id"), patient_hpos)
             + rarity_points(variant.get("af_indian"), variant.get("af_sas"), variant.get("af_global"))
             + consequence_points(variant.get("consequence") or ""))
    return round(min(100.0, total), 1)
