"""Read-only exploration layer over the existing ``GraphData`` knowledge graph (Phase 6).

No second graph engine: every node/edge returned here comes from ``registry.graph`` or, for the
case-aware view, from stored data of exactly one patient (twin core, pedigree, saved evidence).
Nodes are addressed by an unambiguous key ``"<Type>::<id>"``.
"""
from __future__ import annotations

import re
from collections import deque
from typing import Dict, Iterable, List, Optional, Set, Tuple

MAX_NODES = 150          # hard cap on any returned subgraph
MAX_DEPTH = 3
MAX_PATH_LEN = 6
SEARCH_LIMIT = 50

# Entity types the platform genuinely holds. Pathway has no data source, so it is declared unsupported.
UNSUPPORTED_TYPES = {"Pathway": "No pathway source is loaded in this knowledge graph."}
CASE_TYPES = ("Patient", "Phenotype", "Variant", "Gene", "Disease", "FamilyMember", "Publication")


class GraphQueryError(ValueError):
    pass


def _key(n: dict) -> str:
    return f'{n["type"]}::{n["id"]}'


def _label(n: dict) -> str:
    return str(n.get("name") or n.get("label") or n["id"])


def _node_out(n: dict, extra: Optional[dict] = None) -> dict:
    props = {k: v for k, v in n.items() if k not in ("id", "type") and v not in (None, "", [])}
    out = {"key": _key(n), "id": n["id"], "type": n["type"], "label": _label(n), "props": props}
    if extra:
        out.update(extra)
    return out


def _edge_out(e: dict) -> dict:
    s, t = f'{e["src_type"]}::{e["src"]}', f'{e["dst_type"]}::{e["dst"]}'
    return {"id": f'{s}|{e["type"]}|{t}', "source": s, "target": t, "type": e["type"], "attrs": e.get("attrs") or {}}


def parse_key(key: str) -> Tuple[str, str]:
    if not isinstance(key, str) or "::" not in key or len(key) > 200:
        raise GraphQueryError("node key must look like 'Type::id'")
    t, i = key.split("::", 1)
    if not t or not i:
        raise GraphQueryError("node key must look like 'Type::id'")
    return t, i


class GraphExplorer:
    def __init__(self, registry):
        self.registry = registry

    @property
    def g(self):
        return self.registry.graph

    # ------------------------------------------------------------------ meta
    def types(self) -> dict:
        nodes: Dict[str, int] = {}
        edges: Dict[str, int] = {}
        for n in self.g.nodes.values():
            nodes[n["type"]] = nodes.get(n["type"], 0) + 1
        for e in self.g.edges:
            edges[e["type"]] = edges.get(e["type"], 0) + 1
        return {"node_types": nodes, "edge_types": edges, "unsupported": UNSUPPORTED_TYPES,
                "case_node_types": list(CASE_TYPES), "limits": {"max_nodes": MAX_NODES, "max_depth": MAX_DEPTH}}

    def get_node(self, key: str) -> dict:
        t, i = parse_key(key)
        n = self.g.node(t, i)
        if not n:
            raise LookupError(f"node {key} not found")
        self.g._build_indexes()
        by_edge: Dict[str, int] = {}
        for e in self.g._out_index.get(i, []) + self.g._in_index.get(i, []):
            by_edge[e["type"]] = by_edge.get(e["type"], 0) + 1
        out = _node_out(n, {"degree": sum(by_edge.values()), "degree_by_edge_type": by_edge})
        out["neighbors_preview"] = [{"key": _key(x), "label": _label(x), "type": x["type"]} for x in self.g.neighbors(i)[:12]]
        return out

    # ---------------------------------------------------------------- search
    def search(self, q: str, types: Optional[Iterable[str]] = None, limit: int = 20, offset: int = 0) -> dict:
        q = (q or "").strip()
        if len(q) < 2:
            raise GraphQueryError("query must be at least 2 characters")
        if len(q) > 100:
            raise GraphQueryError("query too long")
        limit = max(1, min(limit, SEARCH_LIMIT))
        tset = set(types) if types else None
        ql = q.lower()
        scored: List[Tuple[int, str, dict]] = []
        for n in self.g.nodes.values():
            if tset and n["type"] not in tset:
                continue
            nid, name = str(n["id"]).lower(), _label(n).lower()
            syn = " ".join(str(s) for s in (n.get("synonyms") or [])).lower()
            if ql == nid or ql == name:
                s = 0
            elif nid.startswith(ql) or name.startswith(ql):
                s = 1
            elif ql in name or ql in nid:
                s = 2
            elif syn and ql in syn:
                s = 3
            else:
                continue
            scored.append((s, name, n))
        scored.sort(key=lambda r: (r[0], r[1]))
        page = scored[offset:offset + limit]
        return {"query": q, "total": len(scored), "offset": offset, "limit": limit,
                "results": [_node_out(n, {"match": ["exact", "prefix", "substring", "synonym"][s]}) for s, _, n in page]}

    # ---------------------------------------------------------- neighbourhood
    def neighborhood(self, key: str, depth: int = 1, edge_types: Optional[Iterable[str]] = None,
                     node_types: Optional[Iterable[str]] = None, max_nodes: int = 60) -> dict:
        t, i = parse_key(key)
        if not self.g.node(t, i):
            raise LookupError(f"node {key} not found")
        depth = max(1, min(depth, MAX_DEPTH))
        max_nodes = max(2, min(max_nodes, MAX_NODES))
        et, nt = set(edge_types or ()), set(node_types or ())
        self.g._build_indexes()
        seen: Dict[str, int] = {key: 0}
        edges: Dict[str, dict] = {}
        frontier = [(t, i)]
        truncated = False
        for d in range(1, depth + 1):
            nxt = []
            for ct, ci in frontier:
                for e in self.g._out_index.get(ci, []) + self.g._in_index.get(ci, []):
                    if et and e["type"] not in et:
                        continue
                    oid, otype = (e["dst"], e["dst_type"]) if e["src"] == ci else (e["src"], e["src_type"])
                    if nt and otype not in nt:
                        continue
                    ok = f"{otype}::{oid}"
                    if ok not in seen:
                        if len(seen) >= max_nodes:
                            truncated = True
                            continue
                        if not self.g.node(otype, oid):
                            continue
                        seen[ok] = d
                        nxt.append((otype, oid))
                    eo = _edge_out(e)
                    if eo["source"] in seen and eo["target"] in seen:
                        edges[eo["id"]] = eo
            frontier = nxt
        # include edges between already-collected nodes (so the picture is not artificially sparse)
        for k in list(seen):
            kt, ki = parse_key(k)
            for e in self.g._out_index.get(ki, []):
                eo = _edge_out(e)
                if (not et or e["type"] in et) and eo["source"] in seen and eo["target"] in seen:
                    edges[eo["id"]] = eo
        nodes = [_node_out(self.g.nodes[k], {"depth": d}) for k, d in seen.items() if k in self.g.nodes]
        return {"center": key, "depth": depth, "nodes": nodes, "edges": list(edges.values()),
                "truncated": truncated, "max_nodes": max_nodes}

    # ------------------------------------------------------------------ paths
    def paths(self, src: str, dst: str, max_len: int = 4, limit: int = 3) -> dict:
        st, si = parse_key(src)
        dt, di = parse_key(dst)
        for t, i, k in ((st, si, src), (dt, di, dst)):
            if not self.g.node(t, i):
                raise LookupError(f"node {k} not found")
        max_len = max(1, min(max_len, MAX_PATH_LEN))
        limit = max(1, min(limit, 5))
        self.g._build_indexes()
        # BFS distances from src, then enumerate shortest paths along distance-increasing edges
        def nbrs(k):
            ct, ci = parse_key(k)
            for e in self.g._out_index.get(ci, []) + self.g._in_index.get(ci, []):
                oid, otype = (e["dst"], e["dst_type"]) if e["src"] == ci else (e["src"], e["src_type"])
                ok = f"{otype}::{oid}"
                if self.g.node(otype, oid):
                    yield ok, e

        dist = {src: 0}
        q = deque([src])
        while q:
            cur = q.popleft()
            if dist[cur] >= max_len or cur == dst:
                continue
            for ok, _ in nbrs(cur):
                if ok not in dist:
                    dist[ok] = dist[cur] + 1
                    q.append(ok)
        found: List[List[Tuple[str, Optional[dict]]]] = []
        if dst in dist:
            def walk(cur, path):
                if len(found) >= limit:
                    return
                if cur == dst:
                    found.append(path)
                    return
                for ok, e in nbrs(cur):
                    if dist.get(ok) == dist[cur] + 1 and dist[ok] <= dist[dst]:
                        walk(ok, path + [(ok, e)])
            walk(src, [(src, None)])
        out = []
        for p in found:
            ks = [k for k, _ in p]
            out.append({"length": len(p) - 1, "nodes": [_node_out(self.g.nodes[k]) for k in ks],
                        "edges": [_edge_out(e) for _, e in p[1:]]})
        return {"source": src, "target": dst, "max_len": max_len, "paths": out,
                "status": "found" if out else "no_path",
                "message": None if out else f"No path of length ≤ {max_len} connects these nodes in the knowledge graph."}

    # -------------------------------------------------------------- case graph
    def case_graph(self, patient_id: str, store) -> dict:
        """Graph of ONE case. Only that patient's stored data plus the KG nodes those data point to."""
        core = self.registry.twin.load_core(patient_id)  # raises TwinNotFound for an unknown case
        patient = core["patient"]
        g = self.g
        nodes: Dict[str, dict] = {}
        edges: Dict[str, dict] = {}
        case_key = f"Patient::{patient_id}"
        nodes[case_key] = {"key": case_key, "id": patient_id, "type": "Patient", "label": f"Case {patient_id}",
                           "props": {"state": patient.get("state"), "sex": patient.get("sex"),
                                     "age_years": patient.get("age_years")}, "case": True}

        def add_edge(s, t, typ, **attrs):
            eid = f"{s}|{typ}|{t}"
            edges[eid] = {"id": eid, "source": s, "target": t, "type": typ, "attrs": attrs}

        def add_kg(n: dict, **extra):
            k = _key(n)
            nodes.setdefault(k, _node_out(n, extra))
            return k

        for h in core["hpo_ids"]:
            n = g.node("Hpo", h)
            if n:
                k = add_kg(n, case=True)
                add_edge(case_key, k, "HAS_PHENOTYPE")
        gene_syms: Set[str] = set()
        for v in core["variants"]:
            vid = v.get("variant_id")
            if not vid:
                continue
            vk = f"CaseVariant::{vid}"
            nodes[vk] = {"key": vk, "id": vid, "type": "Variant", "label": v.get("hgvs") or vid, "case": True,
                         "props": {"gene": v.get("gene_symbol"), "classification": v.get("acmg_classification"),
                                   "zygosity": v.get("zygosity"), "consequence": v.get("consequence")}}
            add_edge(case_key, vk, "HAS_VARIANT")
            gs = v.get("gene_symbol")
            if gs and g.node("Gene", gs):
                gene_syms.add(gs)
                add_edge(vk, add_kg(g.node("Gene", gs), case=True), "IN_GENE")
        # candidate diseases: only those the KG links to a case phenotype or gene (ranked by overlap)
        overlap: Dict[str, int] = {}
        for h in core["hpo_ids"]:
            for e in g.edges_to(h, "HAS_PHENOTYPE"):
                overlap[e["src"]] = overlap.get(e["src"], 0) + 1
        for gs in gene_syms:
            for e in g.edges_to(gs, "ASSOCIATED_WITH") + g.edges_from(gs, "ASSOCIATED_WITH"):
                d = e["src"] if e["src_type"] == "Disease" else e["dst"]
                overlap[d] = overlap.get(d, 0) + 3
        for did, score in sorted(overlap.items(), key=lambda kv: -kv[1])[:8]:
            dn = g.node("Disease", did)
            if not dn:
                continue
            dk = add_kg(dn, case_overlap=score)
            for e in g.edges_from(did, "HAS_PHENOTYPE"):
                pk = f"Hpo::{e['dst']}"
                if pk in nodes:
                    add_edge(dk, pk, "HAS_PHENOTYPE")
            for e in g.edges_to(did, "ASSOCIATED_WITH") + g.edges_from(did, "ASSOCIATED_WITH"):
                gid = e["src"] if e["src_type"] == "Gene" else e["dst"]
                if f"Gene::{gid}" in nodes:
                    add_edge(dk, f"Gene::{gid}", "ASSOCIATED_WITH")
        # family members of THIS case's pedigree
        for m in store.ped_list_members(patient_id):
            mk = f"FamilyMember::{patient_id}:{m['member_id']}"
            nodes[mk] = {"key": mk, "id": m["member_id"], "type": "FamilyMember", "label": m["label"], "case": True,
                         "props": {"relation": m.get("relation_to_proband"), "affected": m.get("affected"),
                                   "synthetic": bool(m.get("synthetic"))}}
            add_edge(case_key, mk, "HAS_RELATIVE")
        # saved literature for this case
        for ev in store.evidence_list(patient_id):
            pay = ev.get("payload") or {}
            pk = f"Publication::{ev['source']}:{ev['source_id']}"
            nodes[pk] = {"key": pk, "id": f"{ev['source']}:{ev['source_id']}", "type": "Publication", "case": True,
                         "label": (pay.get("title") or ev["source_id"])[:90], "props": {"source": ev["source"], "pmid": pay.get("pmid")}}
            vk = f"CaseVariant::{ev['variant_id']}" if ev.get("variant_id") else case_key
            add_edge(pk, vk if vk in nodes else case_key, "SUPPORTS")
        counts: Dict[str, int] = {}
        for n in nodes.values():
            counts[n["type"]] = counts.get(n["type"], 0) + 1
        return {"patient_id": patient_id, "nodes": list(nodes.values())[:MAX_NODES * 2], "edges": list(edges.values()),
                "counts": counts,
                "notes": ["Only data stored for this case is shown; Pathway nodes are not available (no data source).",
                          "Disease nodes are KG candidates that share a phenotype or gene with the case, not diagnoses."]}

    def ai_context(self, key: str) -> dict:
        n = self.get_node(key)
        nb = self.neighborhood(key, depth=1, max_nodes=25)
        lines = [f"KNOWLEDGE GRAPH NODE {key} ({n['type']}): {n['label']}"]
        for e in nb["edges"][:25]:
            lines.append(f"- {e['source']} --{e['type']}--> {e['target']}")
        if nb["truncated"]:
            lines.append("(neighbourhood truncated)")
        return {"text": "\n".join(lines),
                "citations": [{"source_type": "knowledge_graph", "identifier": key, "title": n["label"],
                               "summary": f"{n['degree']} relations", "reliability": "curated knowledge graph"}],
                "summary": {"kg": {"node": key, "degree": n["degree"]}}}
