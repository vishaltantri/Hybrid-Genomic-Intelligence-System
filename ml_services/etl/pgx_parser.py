"""PharmGKB/ClinPGx + CPIC + DGIdb parser (Module 5).

Production: download PharmGKB relationships/clinical annotations TSVs into
data/raw/pharmgkb/, CPIC recommendations via api.cpicpgx.org, DGIdb interactions into
data/raw/dgidb/. Falls back to data/seeds/pharmgkb_pairs.csv and cpic_guidelines.csv.
"""
from __future__ import annotations

from typing import Dict, List

from ml_services.config import RAW_DIR, SEEDS_DIR
from ml_services.utils import read_csv_rows

PHARMGKB_PATHS = [RAW_DIR / "pharmgkb" / "pairs.csv", SEEDS_DIR / "pharmgkb_pairs.csv"]
CPIC_PATHS = [RAW_DIR / "cpic" / "guidelines.csv", SEEDS_DIR / "cpic_guidelines.csv"]
DGIDB_PATHS = [RAW_DIR / "dgidb" / "interactions.csv", SEEDS_DIR / "drug_gene_interactions.csv"]


def _first_existing(paths):
    for p in paths:
        if p.exists():
            return p
    return None


def run() -> dict:
    pgx_path = _first_existing(PHARMGKB_PATHS)
    cpic_path = _first_existing(CPIC_PATHS)
    dgidb_path = _first_existing(DGIDB_PATHS)

    drug_nodes: Dict[str, dict] = {}
    gene_nodes: Dict[str, dict] = {}
    pairs: List[dict] = []
    guidelines: List[dict] = []
    interactions: List[dict] = []

    if pgx_path:
        for r in read_csv_rows(pgx_path):
            drug = (r.get("drug") or "").strip()
            gene = (r.get("gene") or "").strip()
            if not drug or not gene:
                continue
            drug_nodes.setdefault(
                drug, {"id": drug, "type": "Drug", "drug_class": r.get("drug_class", ""), "pgx_flag": True}
            )
            gene_parts = gene.split("+") if "+" in gene else [gene]
            for g in gene_parts:
                gene_nodes.setdefault(g, {"id": g, "type": "Gene", "name": g, "is_pgx": True})
            pairs.append(
                {
                    "drug": drug,
                    "gene": gene,
                    "variant_or_allele": (r.get("variant_or_allele") or "").strip(),
                    "evidence_level": (r.get("evidence_level") or "").strip(),
                    "phenotype_category": (r.get("phenotype_category") or "").strip(),
                    "annotation": (r.get("annotation_text") or "").strip(),
                    "india_relevance": (r.get("india_relevance") or "").strip(),
                }
            )

    if cpic_path:
        for r in read_csv_rows(cpic_path):
            guidelines.append(
                {
                    "gene": (r.get("gene") or "").strip(),
                    "phenotype": (r.get("phenotype") or "").strip(),
                    "metabolizer_status": (r.get("metabolizer_status") or "").strip(),
                    "drug": (r.get("drug") or "").strip(),
                    "drug_class": (r.get("drug_class") or "").strip(),
                    "recommendation": (r.get("recommendation") or "").strip(),
                    "severity_if_ignored": (r.get("severity_if_ignored") or "").strip(),
                    "alternatives": (r.get("alternatives") or "").strip(),
                }
            )
            d = (r.get("drug") or "").strip()
            if d:
                drug_nodes.setdefault(
                    d, {"id": d, "type": "Drug", "drug_class": r.get("drug_class", ""), "pgx_flag": True}
                )

    if dgidb_path:
        for r in read_csv_rows(dgidb_path):
            interactions.append(
                {
                    "drug": (r.get("drug_name") or "").strip(),
                    "gene": (r.get("gene_symbol") or "").strip(),
                    "score": (r.get("score") or "").strip(),
                }
            )

    return {
        "drug_nodes": list(drug_nodes.values()),
        "gene_nodes": list(gene_nodes.values()),
        "pgx_pairs": pairs,
        "cpic_guidelines": guidelines,
        "dgidb_interactions": interactions,
    }


if __name__ == "__main__":
    result = run()
    print(
        f"PGx pairs: {len(result['pgx_pairs'])}, CPIC guidelines: {len(result['cpic_guidelines'])}, "
        f"drugs: {len(result['drug_nodes'])}, DGIdb interactions: {len(result['dgidb_interactions'])}"
    )
