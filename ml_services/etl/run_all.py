"""Run all ETL parsers sequentially (thin orchestration over the parsers).

Usage: .venv/bin/python -m ml_services.etl.run_all
"""
from __future__ import annotations

from ml_services.etl import clinvar_parser, hpo_parser, orphanet_parser, pgx_parser, population_parser


def main() -> int:
    h = hpo_parser.run()
    print(f"[hpo]        terms={len(h['hpo_nodes'])} is_a={len(h['parent_edges'])} annotations={len(h['disease_edges'])}")
    o = orphanet_parser.run()
    print(f"[orphanet]   diseases={len(o['disease_nodes'])} genes={len(o['gene_nodes'])} assoc={len(o['gene_edges'])}")
    c = clinvar_parser.run()
    print(f"[clinvar]    variants={len(c['variant_nodes'])} star_alleles={len(c['pgx_star_alleles'])}")
    p = pgx_parser.run()
    print(f"[pgx]        pairs={len(p['pgx_pairs'])} cpic={len(p['cpic_guidelines'])} drugs={len(p['drug_nodes'])}")
    pop = population_parser.run()
    print(f"[population] af_rows={len(pop['af_rows'])} communities={len(pop['community_nodes'])} "
          f"states={len(pop['state_nodes'])} labs={len(pop['lab_nodes'])} specialists={len(pop['specialist_nodes'])}")
    print("All ETL parsers OK. Run `python -m ml_services.etl.kg_build` to assemble the graph.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
