"""ClinVar-style variant parser (Modules 3/5).

Production: download clinvar weekly TSV variant_summary.txt.gz into
data/raw/clinvar/ and map columns (GeneSymbol, Name, VariationID, ClinicalSignificance,
 PhenotypeList). Falls back to data/seeds/clinvar_variants.csv.
"""
from __future__ import annotations

from typing import Dict, List

from ml_services.config import PROCESSED_DIR, RAW_DIR, SEEDS_DIR
from ml_services.utils import read_csv_rows

CLINVAR_PATHS = [RAW_DIR / "clinvar" / "variant_summary.csv", SEEDS_DIR / "clinvar_variants.csv"]


def _first_existing(paths):
    for p in paths:
        if p.exists():
            return p
    raise FileNotFoundError(f"None of these exist: {paths}")


def run() -> dict:
    path = _first_existing(CLINVAR_PATHS)
    rows = read_csv_rows(path)

    variant_nodes: Dict[str, dict] = {}
    in_gene_edges: List[dict] = []
    variant_disease_edges: List[dict] = []
    pgx_star_alleles: List[dict] = []

    for r in rows:
        gene = (r.get("gene_symbol") or "").strip()
        hgvs = (r.get("hgvs") or r.get("variant_id") or "").strip()
        vid = (r.get("variant_id") or hgvs or (r.get("clinvar_accession") or "")).strip()
        star = (r.get("pgx_star_allele") or "").strip()
        key = star or f"{gene}:{hgvs}" or vid
        if not key or key == ":":
            continue
        node = {
            "id": key,
            "type": "Variant",
            "gene": gene,
            "hgvs": hgvs,
            "clinvar_accession": (r.get("clinvar_accession") or "").strip(),
            "clinical_significance": (r.get("clinical_significance") or "").strip(),
            "disease_name": (r.get("disease_name") or "").strip(),
            "af_indian": _float(r.get("af_indian")),
            "af_sas": _float(r.get("af_sas")),
            "af_global": _float(r.get("af_global")),
            "pgx_star_allele": star,
            "pgx_function": (r.get("pgx_function") or "").strip(),
        }
        variant_nodes[key] = node
        if gene:
            in_gene_edges.append({"src": key, "dst": gene, "type": "IN_GENE", "attrs": {}})
        if star:
            pgx_star_alleles.append(
                {"gene": gene, "star_allele": star, "af_indian": _float(r.get("af_indian")), "function": node["pgx_function"]}
            )
        elif node["disease_name"]:
            variant_disease_edges.append({"src": key, "dst": f"NAME::{node['disease_name']}", "type": "VARIANT_OF", "attrs": {}})

    out = {
        "variant_nodes": list(variant_nodes.values()),
        "in_gene_edges": in_gene_edges,
        "variant_disease_edges": variant_disease_edges,
        "pgx_star_alleles": pgx_star_alleles,
    }
    return out


def _float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    result = run()
    print(f"ClinVar-style variants: {len(result['variant_nodes'])}")
