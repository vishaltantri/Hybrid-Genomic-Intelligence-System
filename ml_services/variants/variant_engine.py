"""Variant Analysis Engine (Phase 3B).

Integrates VCF parsing, normalization, annotation, ACMG evaluation, and prioritization
into a cohesive clinical analysis session.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple, Union

from ml_services.variants.acmg_engine import ACMGEngine
from ml_services.variants.annotator import VariantAnnotator
from ml_services.variants.prioritizer import PrioritizedVariant, VariantPrioritizer
from ml_services.variants.vcf_parser import VariantRecord, parse_vcf_content

logger = logging.getLogger("genomind.variants")


def allele_genotype(gt: Any, allele_index: int) -> str:
    """Normalise a sample GT to the state of ONE alt allele: '0/0', '0/1', '1/1' or 'unknown'.

    `allele_index` is the 0-based alt index of the record (multi-allelic sites are decomposed upstream), so
    the matching GT allele number is allele_index + 1. Missing calls ('.') are 'unknown', never reference.
    """
    if gt is None:
        return "unknown"
    alleles = [a for a in str(gt).replace("|", "/").split("/") if a != ""]
    if not alleles or any(a == "." for a in alleles):
        return "unknown"
    n = sum(1 for a in alleles if a == str(allele_index + 1))
    if len(alleles) == 1:           # haploid call (e.g. chrX/Y male, chrM)
        return "1/1" if n == 1 else "0/0"
    return {0: "0/0", 1: "0/1"}.get(n, "1/1")


class VariantEngine:
    """Core genomics engine driving the Genomera Variant Intelligence Workspace."""

    def __init__(self, graph: Optional[Any] = None):
        self.graph = graph
        self.annotator = VariantAnnotator()
        self.acmg_engine = ACMGEngine()
        self.prioritizer = VariantPrioritizer(graph=graph)
        # In-memory storage for interactive analysis sessions
        self._analyses: Dict[str, dict] = {}

    def set_graph(self, graph: Any):
        self.graph = graph
        self.prioritizer = VariantPrioritizer(graph=graph)

    def analyze_vcf(
        self,
        vcf_content: Union[str, bytes],
        filename: str = "sample.vcf",
        patient_id: Optional[str] = None,
        patient_hpo_ids: Optional[List[str]] = None,
        created_by: str = "clinician",
    ) -> dict:
        t0 = time.time()
        analysis_id = f"VCF-{uuid.uuid4().hex[:8].upper()}"

        # 1. Parse & Normalize VCF
        records, summary = parse_vcf_content(vcf_content)

        # 2. Annotate & ACMG evaluate each variant
        evaluated_pairs: List[Tuple[VariantRecord, Any, Any]] = []
        sample_genotypes: Dict[str, Dict[str, dict]] = {}
        for rec in records:
            # per-sample genotypes (all VCF samples), used by the pedigree module for trio/family analysis
            sample_genotypes[rec.variant_id] = {
                name: {"genotype": allele_genotype(d.get("GT"), rec.allele_index), "raw": d.get("GT"),
                       "depth": d.get("DP"), "gq": d.get("GQ")}
                for name, d in (rec.samples or {}).items()
            }
            ann = self.annotator.annotate(
                chrom=rec.norm_chrom,
                pos=rec.norm_pos,
                ref=rec.norm_ref,
                alt=rec.norm_alt,
                info_dict=rec.info,
            )
            acmg_res = self.acmg_engine.evaluate(ann, patient_hpos=patient_hpo_ids)
            evaluated_pairs.append((rec, ann, acmg_res))

        # 3. Prioritize variants
        prioritized = self.prioritizer.prioritize(evaluated_pairs, patient_hpo_ids=patient_hpo_ids)

        elapsed = round(time.time() - t0, 3)

        # QC and KPI metrics
        n_total = len(prioritized)
        n_pathogenic = sum(1 for v in prioritized if v.acmg_classification == "Pathogenic")
        n_likely_pathogenic = sum(1 for v in prioritized if v.acmg_classification == "Likely pathogenic")
        n_vus = sum(1 for v in prioritized if v.acmg_classification == "Uncertain significance")
        n_benign = sum(1 for v in prioritized if v.acmg_classification in ("Benign", "Likely benign"))
        n_pgx = sum(1 for v in prioritized if v.pgx_star_allele is not None)
        n_tier1 = sum(1 for v in prioritized if v.priority_tier.startswith("Tier 1"))

        qc_metrics = {
            "total_variants": n_total,
            "samples": summary["samples"],
            "sample_count": len(summary["samples"]),
            "is_multisample": summary["is_multisample"],
            "pathogenic_count": n_pathogenic,
            "likely_pathogenic_count": n_likely_pathogenic,
            "vus_count": n_vus,
            "benign_count": n_benign,
            "pgx_variant_count": n_pgx,
            "tier1_count": n_tier1,
            "duration_seconds": elapsed,
        }

        # Store session
        analysis_record = {
            "analysis_id": analysis_id,
            "filename": filename,
            "patient_id": patient_id,
            "patient_hpo_ids": patient_hpo_ids or [],
            "created_by": created_by,
            "timestamp": time.time(),
            "qc_metrics": qc_metrics,
            "variants": [asdict(v) for v in prioritized],
            "sample_genotypes": sample_genotypes,
        }
        self._analyses[analysis_id] = analysis_record
        self._persist(analysis_record)

        return analysis_record

    # Analyses are cached in memory for speed and persisted in the `variant_analyses` table (Phase 18) so they survive restarts.
    def _persist(self, record: dict) -> None:
        try:
            from backend.app import store
            store.save_analysis(record)
        except Exception:
            logger.exception("could not persist analysis %s; it is available in memory only", record.get("analysis_id"))

    def get_analysis(self, analysis_id: str) -> Optional[dict]:
        hit = self._analyses.get(analysis_id)
        if hit:
            return hit
        try:
            from backend.app import store
            hit = store.load_analysis(analysis_id)
        except Exception:
            logger.exception("could not read analysis %s from the database", analysis_id)
            hit = None
        if hit:
            self._analyses[analysis_id] = hit
        return hit

    def list_analyses(self) -> List[dict]:
        res = []
        merged = dict(self._analyses)
        try:
            from backend.app import store
            for s in store.list_analysis_summaries():
                if s["analysis_id"] not in merged:
                    merged[s["analysis_id"]] = s
        except Exception:
            logger.exception("could not list persisted analyses")
        for aid, item in merged.items():
            res.append({
                "analysis_id": aid,
                "filename": item["filename"],
                "patient_id": item["patient_id"],
                "timestamp": item["timestamp"],
                "qc_metrics": item["qc_metrics"],
                "created_by": item["created_by"],
            })
        res.sort(key=lambda x: x["timestamp"], reverse=True)
        return res
