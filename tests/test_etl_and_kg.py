"""ETL + knowledge-graph tests (Module 3 data layer)."""
from __future__ import annotations

import pytest

from ml_services.etl import clinvar_parser, hpo_parser, orphanet_parser, pgx_parser, population_parser
from ml_services.etl.graph_store import GraphData, build_graph, build_networkx, save_processed


@pytest.fixture(scope="module")
def hpo():
    return hpo_parser.run()


@pytest.fixture(scope="module")
def graph():
    return build_graph()


def test_hpo_terms_parsed(hpo):
    assert len(hpo["hpo_nodes"]) >= 40
    assert all(t["id"].startswith("HP:") for t in hpo["hpo_nodes"])
    names = {t["name"] for t in hpo["hpo_nodes"]}
    assert "Jaundice" in names
    # Real HPO names HP:0001250 "Seizure"; the mini seed calls it "Seizures".
    assert any("Seizur" in n for n in names)
    # definitions were captured, not just IDs
    assert any(t["definition"] for t in hpo["hpo_nodes"])


def test_hpo_parent_edges(hpo):
    # The parent differs between the mini seed (HP:0000707) and the real ontology
    # (HP:0012638); what must hold in both is that HP:0001250 has a parent that
    # exists as a parsed HPO term.
    ids = {t["id"] for t in hpo["hpo_nodes"]}
    parents = {e["dst"] for e in hpo["parent_edges"] if e["src"] == "HP:0001250"}
    assert parents and parents <= ids


def test_hpoa_annotations(hpo):
    assert len(hpo["disease_edges"]) >= 60
    freqs = {e["attrs"]["frequency"] for e in hpo["disease_edges"]}
    assert any(f.startswith("HP:") for f in freqs)


def test_orphanet_diseases_and_genes():
    out = orphanet_parser.run()
    assert len(out["disease_nodes"]) >= 15
    ids = {d["id"] for d in out["disease_nodes"]}
    assert "ORPHA:915" in ids  # Wilson disease
    genes = {g["id"] for g in out["gene_nodes"]}
    assert {"ATP7B", "HBB", "CFTR"} <= genes
    assert any(g.get("is_pgx") for g in out["gene_nodes"])


def test_clinvar_variants():
    out = clinvar_parser.run()
    assert len(out["variant_nodes"]) >= 15
    sickle = [v for v in out["variant_nodes"] if "HbS" in (v["hgvs"] or "")]
    assert sickle and sickle[0]["af_indian"] > 0
    assert any(v["pgx_star_allele"] for v in out["variant_nodes"])


def test_pgx_parser():
    out = pgx_parser.run()
    assert len(out["pgx_pairs"]) >= 15
    assert len(out["cpic_guidelines"]) >= 10
    drugs = {d["id"] for d in out["drug_nodes"]}
    assert {"clopidogrel", "warfarin", "primaquine"} <= drugs
    g6pd = [p for p in out["pgx_pairs"] if p["gene"] == "G6PD"]
    assert g6pd and "G6PD" in g6pd[0]["india_relevance"]


def test_population_parser():
    out = population_parser.run()
    assert len(out["af_rows"]) >= 25
    assert len(out["state_nodes"]) >= 25
    tn = [s for s in out["state_nodes"] if s["id"] == "Tamil Nadu"][0]
    assert tn["consanguinity_rate"] > 20  # NFHS-5: highest in India
    assert any(c["id"] == "Gond" for c in out["community_nodes"])
    assert any(l["nabl_accredited"] for l in out["lab_nodes"])


def test_graph_has_all_node_types(graph):
    types = {n["type"] for n in graph.nodes.values()}
    assert {"Disease", "Gene", "Hpo", "Variant", "Drug", "Ethnicity", "State", "Lab",
            "Doctor", "IndianSynonym", "AF"} <= types


def test_graph_has_all_edge_types(graph):
    types = {e["type"] for e in graph.edges}
    assert {"HAS_PHENOTYPE", "IS_A", "ASSOCIATED_WITH", "IN_GENE", "VARIANT_OF",
            "PGX_INTERACTS", "FOUNDER_RISK", "PREVALENT_IN", "LOCATED_IN", "MAPS_TO",
            "HAS_ALLELE"} <= types


def test_graph_queries(graph):
    # Wilson disease has phenotypes, genes and (via community table) founder risk
    phenos = graph.edges_from("ORPHA:915", "HAS_PHENOTYPE")
    assert len(phenos) >= 4
    genes = [g["id"] for g in graph.neighbors("ORPHA:915", "ASSOCIATED_WITH")]
    assert "ATP7B" in genes
    synonyms = graph.edges_to("HP:0000952", "MAPS_TO")
    assert len(synonyms) >= 3  # piliya, aankhon ka peela hona, peeli aankhein


def test_graph_roundtrip(tmp_path, graph):
    gd = GraphData.from_dict(graph.to_dict())
    assert len(gd.nodes) == len(graph.nodes)
    nx_graph = build_networkx(gd)
    assert nx_graph.number_of_nodes() == len(graph.nodes)
    # MultiDiGraph keys edges by relation type, so parallel edges of the same type collapse:
    # compare against the count of unique (src, dst, type) triples instead.
    unique_edges = {(e["src"], e["dst"], e["type"]) for e in graph.edges}
    assert nx_graph.number_of_edges() == len(unique_edges)


def test_graph_has_no_dangling_edge_references(graph):
    """Every edge endpoint (where a node type is declared) must exist as a node.

    Without this check a typo like 'UP' instead of 'Uttar Pradesh' silently creates a
    phantom State node and a spurious risk edge.
    """
    validation = graph.validate()
    assert validation["ok"], f"dangling references: {validation['dangling']}"
    assert validation["n_dangling"] == 0


def test_edge_dedup_and_merge():
    gd = GraphData()
    gd.add_node({"id": "A", "type": "Disease", "name": "Alpha"})
    gd.add_node({"id": "A", "type": "Disease", "inheritance": "AR"})
    assert gd.node("Disease", "A")["name"] == "Alpha"
    assert gd.node("Disease", "A")["inheritance"] == "AR"
    gd.add_edge("A", "B", "REL")
    gd.add_edge("A", "B", "REL")
    assert len(gd.edges) == 1
