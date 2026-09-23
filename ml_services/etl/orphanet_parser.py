"""Orphanet-style rare disease + gene-disease parser (Modules 3/4/6).

Production: download Orphadata product files (en_product6 gene-disease, en_product4
prevalence, nomenclature) into data/raw/orphanet/ and adapt column mapping here.
Falls back to data/seeds/orphanet_*.csv.
"""
from __future__ import annotations

from typing import Dict, List

from ml_services.config import PROCESSED_DIR, RAW_DIR, SEEDS_DIR
from ml_services.utils import read_csv_rows

DISEASE_PATHS = [RAW_DIR / "orphanet" / "rare_diseases.csv", SEEDS_DIR / "orphanet_rare_diseases.csv"]
GENE_PATHS = [RAW_DIR / "orphanet" / "gene_disease.csv", SEEDS_DIR / "orphanet_gene_disease.csv"]


def _first_existing(paths):
    for p in paths:
        if p.exists():
            return p
    raise FileNotFoundError(f"None of these exist: {paths}")


def run() -> dict:
    dpath, gpath = _first_existing(DISEASE_PATHS), _first_existing(GENE_PATHS)
    drows = read_csv_rows(dpath)
    grows = read_csv_rows(gpath)

    disease_nodes = []
    for r in drows:
        disease_nodes.append(
            {
                "id": r["disease_id"].strip(),
                "type": "Disease",
                "name": r["disease_name"].strip(),
                "inheritance": r.get("inheritance", ""),
                "prevalence_per_100k": float(r["prevalence_per_100k"] or 0),
                "onset": r.get("onset", ""),
                "india_note": r.get("india_note", ""),
                "source": "orphanet",
            }
        )

    gene_nodes: Dict[str, dict] = {}
    gene_edges: List[dict] = []
    pgx_gene_nodes: Dict[str, dict] = {}
    for r in grows:
        sym = r["gene_symbol"].strip()
        disease_id = r["disease_id"].strip()
        if disease_id:
            gene_nodes.setdefault(
                sym, {"id": sym, "type": "Gene", "name": r.get("gene_name", sym), "is_pgx": False}
            )
            gene_edges.append(
                {"src": sym, "dst": disease_id, "type": "ASSOCIATED_WITH", "attrs": {"confidence": r.get("confidence", ""), "assoc": r.get("association_type", "")}}
            )
        elif r.get("association_type") == "PGx":
            pgx_gene_nodes.setdefault(sym, {"id": sym, "type": "Gene", "name": r.get("gene_name", sym), "is_pgx": True})

    # Merge PGx-only gene nodes (don't overwrite causal ones)
    for sym, node in pgx_gene_nodes.items():
        if sym in gene_nodes:
            gene_nodes[sym]["is_pgx"] = True
        else:
            gene_nodes[sym] = node

    out = {"disease_nodes": disease_nodes, "gene_nodes": list(gene_nodes.values()), "gene_edges": gene_edges}
    return out


if __name__ == "__main__":
    result = run()
    print(f"Orphanet diseases: {len(result['disease_nodes'])}, genes: {len(result['gene_nodes'])}")
