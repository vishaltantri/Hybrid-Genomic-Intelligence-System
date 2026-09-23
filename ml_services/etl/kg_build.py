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
