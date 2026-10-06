"""Module 3/4/7 endpoints: differential diagnosis and explainability."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.app import store
from backend.app.models import DiagnosisRequest
from backend.app.security import require
from backend.app.services import registry

router = APIRouter(prefix="/api/v1", tags=["diagnosis"])


def _resolve_hpo(payload: DiagnosisRequest) -> list:
    if payload.hpo_ids:
        return payload.hpo_ids
    if payload.text:
        from ml_services.nlp.llm_symptoms import assisted_profile
        return assisted_profile(registry, payload.text)["hpo_ids"]
    raise HTTPException(status_code=400, detail="provide either hpo_ids or text")


@router.post("/diagnosis")
def diagnose(payload: DiagnosisRequest, user: dict = Depends(require("diagnosis:run"))):
    """Module 4: top-k differential diagnosis with Indian population priors + uncertainty."""
    hpo_ids = _resolve_hpo(payload)
    context = {"state": payload.state, "community": payload.community, "sex": payload.sex}
    result = registry.diagnosis.diagnose(hpo_ids, context, top_k=payload.top_k, explain=payload.explain)
    store.add_event_for_case(payload.patient_id, "diagnosis", result)
    store.audit(user["username"], "diagnosis.run", payload.patient_id or "", f"n_hpo={len(hpo_ids)}")
    return result


@router.post("/xai/explain")
def explain(payload: DiagnosisRequest, user: dict = Depends(require("xai:read"))):
    """Module 7: full multi-layer explanation bundle for the leading differential."""
    hpo_ids = payload.hpo_ids
    if not hpo_ids and payload.text:
        hpo_ids = _resolve_hpo(payload)          # same phenotype reading as the diagnosis the explanation belongs to
    bundle = registry.xai.explain(text=payload.text or "",
                                  hpo_ids=hpo_ids,
                                  patient_context={"state": payload.state, "community": payload.community,
                                                   "sex": payload.sex},
                                  top_k=max(3, payload.top_k), lang="en")
    return bundle


@router.get("/diseases/{disease_id}")
def disease_detail(disease_id: str, user: dict = Depends(require("kg:read"))):
    graph = registry.graph
    node = graph.node("Disease", disease_id)
    if not node:
        raise HTTPException(status_code=404, detail="disease not in knowledge graph")
    phenotypes = [{"hpo_id": e["dst"], "frequency": (e.get("attrs") or {}).get("frequency", ""),
                   "name": (graph.node("Hpo", e["dst"]) or {}).get("name", e["dst"])}
                  for e in graph.edges_from(disease_id, "HAS_PHENOTYPE")]
    genes = [g["id"] for g in graph.neighbors(disease_id, "ASSOCIATED_WITH")]
    founders = [{"community": e["src"], "note": (e.get("attrs") or {}).get("note", "")}
                for e in graph.edges_to(disease_id, "FOUNDER_RISK")]
    return {"disease": node, "phenotypes": phenotypes, "genes": genes, "founder_risk": founders}


@router.get("/kg/stats")
def kg_stats(user: dict = Depends(require("kg:read"))):
    graph = registry.graph
    node_types, edge_types = {}, {}
    for n in graph.nodes.values():
        node_types[n["type"]] = node_types.get(n["type"], 0) + 1
    for e in graph.edges:
        edge_types[e["type"]] = edge_types.get(e["type"], 0) + 1
    return {"nodes": node_types, "edges": edge_types,
            "total_nodes": len(graph.nodes), "total_edges": len(graph.edges)}
