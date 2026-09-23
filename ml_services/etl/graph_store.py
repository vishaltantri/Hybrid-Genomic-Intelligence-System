"""Unified knowledge-graph assembly + stores (Module 3).

Assembles nodes/edges from every ETL parser into one GraphData object, saves a
processed JSON snapshot, optionally pushes to Neo4j, and always provides a
NetworkX fallback so the rest of the platform never hard-depends on Neo4j.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Set

from ml_services.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER, PROCESSED_DIR, SEEDS_DIR
from ml_services.utils import read_csv_rows, read_json, write_json


class GraphData:
    """Container for typed nodes and edges with dedup by (type, id)."""

    def __init__(self) -> None:
        self.nodes: Dict[str, dict] = {}  # key = f"{type}::{id}"
        self.edges: List[dict] = []
        self._edge_keys: Set[tuple] = set()

    @staticmethod
    def key(node_type: str, node_id: str) -> str:
        return f"{node_type}::{node_id}"

    def add_node(self, node: dict) -> None:
        node = dict(node)
        nid = str(node.pop("id"))
        ntype = str(node.pop("type"))
        k = self.key(ntype, nid)
        if k in self.nodes:
            self.nodes[k].update({k2: v2 for k2, v2 in node.items() if v2 not in (None, "", [])})
        else:
            node["id"] = nid
            node["type"] = ntype
            self.nodes[k] = node

    def add_edge(self, src: str, dst: str, etype: str, src_type: str = "", dst_type: str = "", **attrs) -> None:
        k = (src, dst, etype)
        if k in self._edge_keys:
            return
        self._edge_keys.add(k)
        self.edges.append({"src": src, "dst": dst, "type": etype, "src_type": src_type, "dst_type": dst_type, "attrs": attrs})

    def node(self, node_type: str, node_id: str) -> Optional[dict]:
        return self.nodes.get(self.key(node_type, node_id))

    def neighbors(self, node_id: str, etype: Optional[str] = None) -> List[dict]:
        out = []
        for e in self.edges:
            if e["src"] == node_id and (etype is None or e["type"] == etype):
                n = self.nodes.get(self.key(e["dst_type"] or "", e["dst"]))
                if n:
                    out.append(n)
            elif e["dst"] == node_id and (etype is None or e["type"] == etype):
                n = self.nodes.get(self.key(e["src_type"] or "", e["src"]))
                if n:
                    out.append(n)
        return out

    def edges_from(self, node_id: str, etype: Optional[str] = None) -> List[dict]:
        return [e for e in self.edges if e["src"] == node_id and (etype is None or e["type"] == etype)]

    def edges_to(self, node_id: str, etype: Optional[str] = None) -> List[dict]:
        return [e for e in self.edges if e["dst"] == node_id and (etype is None or e["type"] == etype)]

    def by_type(self, node_type: str) -> List[dict]:
        return [n for n in self.nodes.values() if n["type"] == node_type]

    def dangling_references(self) -> List[dict]:
        """Edges whose endpoints are not declared nodes.

        The graph tolerates these (a name-only stub is often all a source file gives us), but
        a clean KG should have none — this is the hygiene check run by the test suite and by
        kg_build's self-report.
        """
        dangling = []
        for e in self.edges:
            for side, ntype_key, id_key in (("src", "src_type", "src"), ("dst", "dst_type", "dst")):
                ntype = e.get(ntype_key) or ""
                nid = e[id_key]
                if not ntype:
                    continue
                if self.key(ntype, nid) not in self.nodes:
                    dangling.append({"side": side, "type": ntype, "id": nid, "edge_type": e["type"]})
        return dangling

    def validate(self) -> dict:
        dangling = self.dangling_references()
        unknown_types = sorted({e["type"] for e in self.edges if not e.get("src_type") or not e.get("dst_type")})
        return {"n_nodes": len(self.nodes), "n_edges": len(self.edges),
                "n_dangling": len(dangling), "dangling": dangling[:25],
                "edges_without_declared_node_types": unknown_types,
                "ok": not dangling}

    def to_dict(self) -> dict:
        return {"nodes": list(self.nodes.values()), "edges": self.edges}

    @classmethod
    def from_dict(cls, d: dict) -> "GraphData":
        gd = cls()
        for n in d["nodes"]:
            gd.add_node(n)
        for e in d["edges"]:
            gd.add_edge(e["src"], e["dst"], e["type"], e.get("src_type", ""), e.get("dst_type", ""), **(e.get("attrs") or {}))
        return gd


def build_graph() -> GraphData:
    """Run every parser and assemble the full knowledge graph."""
    from ml_services.etl import clinvar_parser, hpo_parser, orphanet_parser, pgx_parser, population_parser

    gd = GraphData()

    # --- HPO ontology + disease annotations ---
    hpo = hpo_parser.run()
    for n in hpo["hpo_nodes"]:
        gd.add_node(n)
    for e in hpo["parent_edges"]:
        gd.add_edge(e["src"], e["dst"], "IS_A", "Hpo", "Hpo")
    for n in hpo["disease_nodes"]:
        gd.add_node(n)
    for e in hpo["disease_edges"]:
        gd.add_edge(e["src"], e["dst"], "HAS_PHENOTYPE", "Disease", "Hpo", **e["attrs"])

    # --- Orphanet diseases + gene-disease ---
    orphan = orphanet_parser.run()
    for n in orphan["disease_nodes"]:
        gd.add_node(n)
    for n in orphan["gene_nodes"]:
        gd.add_node(n)
    for e in orphan["gene_edges"]:
        gd.add_edge(e["src"], e["dst"], "ASSOCIATED_WITH", "Gene", "Disease", **e["attrs"])

    # --- ClinVar variants ---
    cv = clinvar_parser.run()
    for n in cv["variant_nodes"]:
        gd.add_node(n)
    for e in cv["in_gene_edges"]:
        # ClinVar is authoritative that the gene exists: create the Gene node when the
        # Orphanet gene table doesn't list it, otherwise the edge would dangle.
        if gd.node("Gene", e["dst"]) is None:
            gd.add_node({"id": e["dst"], "type": "Gene", "name": e["dst"], "source": "clinvar"})
        gd.add_edge(e["src"], e["dst"], "IN_GENE", "Variant", "Gene")
    for e in cv["variant_disease_edges"]:
        # NAME:: links resolved against disease names
        target_name = e["dst"].replace("NAME::", "").lower()
        match = next((d for d in gd.by_type("Disease") if d["name"].lower() == target_name), None)
        if match:
            gd.add_edge(e["src"], match["id"], "VARIANT_OF", "Variant", "Disease")

    # --- PGx drugs / pairs / CPIC ---
    pgx = pgx_parser.run()
    for n in pgx["drug_nodes"]:
        gd.add_node(n)
    for n in pgx["gene_nodes"]:
        gd.add_node(n)
    for p in pgx["pgx_pairs"]:
        gd.add_edge(p["drug"], p["gene"], "PGX_INTERACTS", "Drug", "Gene",
                    evidence=p["evidence_level"], allele=p["variant_or_allele"],
                    category=p["phenotype_category"], india_relevance=p["india_relevance"])

    # --- Indian population data ---
    pop = population_parser.run()
    for n in pop["community_nodes"]:
        gd.add_node(n)
    for n in pop["state_nodes"]:
        gd.add_node(n)
    for n in pop["lab_nodes"]:
        gd.add_node(n)
    for n in pop["specialist_nodes"]:
        gd.add_node(n)

    for af in pop["af_rows"]:
        gene = af["gene"]
        if gd.node("Gene", gene) is None:
            gd.add_node({"id": gene, "type": "Gene", "name": gene, "is_pgx": True})
        gd.add_node({"id": af["variant_or_allele"], "type": "AF", "gene": gene,
                     "af_indian": af["af_indian"], "af_sas": af["af_sas_gnomad"],
                     "af_global": af["af_global"], "ethnicity": af["ethnicity"],
                     "state_or_region": af["state_or_region"], "source": af["source"],
                     "n_samples": af["n_samples"]})
        # Edge id must match the node id above (raw variant label) or the reference dangles.
        gd.add_edge(gene, af["variant_or_allele"], "HAS_ALLELE", "Gene", "AF",
                    af_indian=af["af_indian"], ethnicity=af["ethnicity"],
                    state_or_region=af["state_or_region"])

    for c in pop["community_nodes"]:
        if c.get("founder_disease_id"):
            gd.add_edge(c["id"], c["founder_disease_id"], "FOUNDER_RISK", "Ethnicity", "Disease", note=c.get("founder_note", ""))
        for st in c.get("primary_states", []):
            gd.add_edge(c["id"], st, "PREVALENT_IN", "Ethnicity", "State")
        # carrier multiplier as edge attribute onto founder disease handled above

    for lab in pop["lab_nodes"]:
        if lab.get("state"):
            gd.add_edge(lab["id"], lab["state"], "LOCATED_IN", "Lab", "State")

    for doc in pop["specialist_nodes"]:
        if doc.get("state"):
            gd.add_edge(doc["id"], doc["state"], "LOCATED_IN", "Doctor", "State")

    # --- Indian synonym dictionary (Module 2 patent artifact) ---
    syn_path = SEEDS_DIR / "indian_synonyms.csv"
    if syn_path.exists():
        for r in read_csv_rows(syn_path):
            phrase = (r.get("phrase") or "").strip().lower()
            hpo_id = (r.get("hpo_id") or "").strip()
            if not phrase or not hpo_id:
                continue
            # The synonym dictionary may cite HPO terms outside the loaded ontology slice
            # (e.g. a newer hp.obo). Create a stub so the mapping edge never dangles; the
            # real definition arrives as soon as the full ontology is downloaded.
            if gd.node("Hpo", hpo_id) is None:
                gd.add_node({"id": hpo_id, "type": "Hpo", "name": r.get("hpo_name", hpo_id),
                             "source": "indian_synonym_dictionary_stub"})
            gd.add_node({"id": phrase, "type": "IndianSynonym", "language": r.get("language", ""),
                         "hpo_name": r.get("hpo_name", "")})
            gd.add_edge(phrase, hpo_id, "MAPS_TO", "IndianSynonym", "Hpo")

    # --- Drug list (broadens Drug nodes beyond PGx pairs) ---
    drugs_path = SEEDS_DIR / "drugs.csv"
    if drugs_path.exists():
        for r in read_csv_rows(drugs_path):
            name = (r.get("drug_name") or "").strip()
            if not name:
                continue
            gd.add_node({"id": name, "type": "Drug", "drug_class": r.get("drug_class", ""),
                         "pgx_flag": (r.get("pgx_flag") or "false").lower() == "true"})
            gene = (r.get("related_gene") or "").strip()
            if gene:
                gd.add_node({"id": gene, "type": "Gene", "name": gene, "is_pgx": True})
                gd.add_edge(name, gene, "PGX_INTERACTS", "Drug", "Gene", evidence="seed", allele="", category="", india_relevance="")

    return gd


def build_networkx(gd: GraphData):
    import networkx as nx

    g = nx.MultiDiGraph()
    for k, n in gd.nodes.items():
        g.add_node(k, **{kk: vv for kk, vv in n.items() if isinstance(vv, (str, int, float, bool))})
    for e in gd.edges:
        g.add_edge(GraphData.key(e["src_type"], e["src"]) if e["src_type"] else e["src"],
                   GraphData.key(e["dst_type"], e["dst"]) if e["dst_type"] else e["dst"],
                   key=e["type"], etype=e["type"], **{k: v for k, v in (e.get("attrs") or {}).items()
                                                       if isinstance(v, (str, int, float, bool))})
    return g


def push_neo4j(gd: GraphData, timeout_seconds: float = 3.0) -> bool:
    """Best-effort push to Neo4j; returns False (with no exception) when unavailable."""
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD),
                                      connection_timeout=timeout_seconds)
        driver.verify_connectivity()
    except Exception:
        return False

    def _esc(s):
        return str(s).replace("\\", "\\\\").replace('"', '\\"')

    with driver.session() as session:
        for ntype in {n["type"] for n in gd.nodes.values()}:
            session.run(f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{ntype}) REQUIRE n.id IS UNIQUE")
        for n in gd.nodes.values():
            props = ", ".join(f'{k}: "{_esc(v)}"' if isinstance(v, str) else f"{k}: {_jsonish(v)}"
                              for k, v in n.items() if k not in ("id", "type") and v not in (None, "", []))
            set_clause = (" SET n += {" + props + "}") if props else " SET n += {dummy: true}"
            session.run(f'MERGE (n:{n["type"]} {{id: "{_esc(n["id"])}"}})' + set_clause)
        for e in gd.edges:
            attrs = ", ".join(f'{k}: "{_esc(v)}"' if isinstance(v, str) else f"{k}: {_jsonish(v)}"
                              for k, v in (e.get("attrs") or {}).items() if v not in (None, ""))
            set_clause = f" SET r += {{" + attrs + "}" if attrs else ""
            session.run(
                f'MERGE (a:{e["src_type"]} {{id: "{_esc(e["src"])}"}}) '
                f'MERGE (b:{e["dst_type"]} {{id: "{_esc(e["dst"])}"}}) '
                f'MERGE (a)-[r:{e["type"]}]->(b)' + set_clause
            )
    driver.close()
    return True


def _jsonish(v):
    import json

    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (list, dict)):
        return json.dumps(v).replace('"', "'")
    return f'"{v}"'


def load_processed() -> Optional[GraphData]:
    path = PROCESSED_DIR / "kg.json"
    if not path.exists():
        return None
    return GraphData.from_dict(read_json(path))


def save_processed(gd: GraphData) -> None:
    write_json(PROCESSED_DIR / "kg.json", gd.to_dict())
