"""Build the India rare-disease knowledge graph (Module 3).

Usage:
    .venv/bin/python -m ml_services.etl.kg_build

Writes data/processed/kg.json and pushes to Neo4j when reachable
(docker compose up neo4j), otherwise reports NetworkX-only mode.
"""
from __future__ import annotations

import time

from ml_services.etl.graph_store import build_graph, build_networkx, push_neo4j, save_processed


def main() -> int:
    t0 = time.time()
    gd = build_graph()

    # Link diseases that share a canonical name across sources (hpoa annotates under
    # OMIM:/DECIPHER:, our seed + Orphanet data under ORPHA:) so phenotype evidence
    # pools into one node instead of splitting a disease across namespaces.
    by_name: dict = {}
    same_as = []
    for n in gd.nodes.values():
        if n["type"] == "Disease" and n.get("name"):
            by_name.setdefault(n["name"].strip().lower(), []).append(n["id"])
    from ml_services.etl.graph_store import canonical_disease_root

    for ids in by_name.values():
        if 1 < len(ids) <= 6:  # skip pathological over-shared names
            root = canonical_disease_root(ids, gd)
            for other in ids:
                if other != root:
                    same_as.append({"src": root, "dst": other, "type": "SAME_AS", "attrs": {}})
    for e in same_as:
        gd.add_edge(e["src"], e["dst"], "SAME_AS")

    save_processed(gd)

    counts = {}
    for n in gd.nodes.values():
        counts[n["type"]] = counts.get(n["type"], 0) + 1
    edge_counts = {}
    for e in gd.edges:
        edge_counts[e["type"]] = edge_counts.get(e["type"], 0) + 1

    print("Nodes:")
    for k in sorted(counts):
        print(f"  {k:14s} {counts[k]:5d}")
    print("Edges:")
    for k in sorted(edge_counts):
        print(f"  {k:18s} {edge_counts[k]:5d}")

    validation = gd.validate()
    if validation["ok"]:
        print("Validation: no dangling edge references.")
    else:
        print(f"Validation: {validation['n_dangling']} dangling edge reference(s) — "
              f"e.g. {validation['dangling'][:3]}")

    ok = push_neo4j(gd)
    if ok:
        print("Neo4j: pushed successfully (bolt://localhost:7687).")
    else:
        g = build_networkx(gd)
        print(f"Neo4j: not reachable — using NetworkX fallback ({g.number_of_nodes()} nodes, {g.number_of_edges()} edges).")

    print(f"KG snapshot saved to data/processed/kg.json in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
