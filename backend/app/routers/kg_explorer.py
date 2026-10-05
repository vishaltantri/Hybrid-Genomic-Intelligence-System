"""Genomera Knowledge Graph Explorer API (Phase 6). Read-only; all traversal happens server-side with hard caps.

  GET /api/v1/kg/types                      node/edge types, limits, unsupported entity types
  GET /api/v1/kg/search?q=&types=&limit=    name / id / synonym search
  GET /api/v1/kg/node?key=Type::id          one node with degree breakdown
  GET /api/v1/kg/neighborhood?key=&depth=   bounded neighbourhood expansion
  GET /api/v1/kg/path?source=&target=       shortest paths (undirected)
  GET /api/v1/kg/case/{patient_id}          case-aware graph (one case only; needs clinical:read)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app import store
from backend.app.security import ROLE_PERMISSIONS, require
from backend.app.services import registry
from ml_services.graph_ai.explorer import GraphQueryError
from ml_services.twin.twin_service import TwinNotFound

router = APIRouter(prefix="/api/v1/kg", tags=["knowledge-graph"])


def _csv(v: Optional[str]):
    return [x.strip() for x in v.split(",") if x.strip()] if v else None


def _run(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except GraphQueryError as ex:
        raise HTTPException(status_code=422, detail=str(ex))
    except (LookupError, TwinNotFound) as ex:
        raise HTTPException(status_code=404, detail=str(ex))


@router.get("/types")
def kg_types(user: dict = Depends(require("kg:read"))):
    return registry.graph_explorer.types()


@router.get("/search")
def kg_search(q: str = Query(..., max_length=100), types: Optional[str] = Query(None, max_length=200),
              limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=5000),
              user: dict = Depends(require("kg:read"))):
    return _run(registry.graph_explorer.search, q, _csv(types), limit, offset)


@router.get("/node")
def kg_node(key: str = Query(..., max_length=200), user: dict = Depends(require("kg:read"))):
    return _run(registry.graph_explorer.get_node, key)


@router.get("/neighborhood")
def kg_neighborhood(key: str = Query(..., max_length=200), depth: int = Query(1, ge=1, le=3),
                    edge_types: Optional[str] = Query(None, max_length=300), node_types: Optional[str] = Query(None, max_length=300),
                    max_nodes: int = Query(60, ge=2, le=150), user: dict = Depends(require("kg:read"))):
    return _run(registry.graph_explorer.neighborhood, key, depth, _csv(edge_types), _csv(node_types), max_nodes)


@router.get("/path")
def kg_path(source: str = Query(..., max_length=200), target: str = Query(..., max_length=200),
            max_len: int = Query(4, ge=1, le=6), user: dict = Depends(require("kg:read"))):
    return _run(registry.graph_explorer.paths, source, target, max_len)


@router.get("/case/{patient_id}")
def kg_case(patient_id: str, user: dict = Depends(require("kg:read"))):
    perms = ROLE_PERMISSIONS.get(user["role"], [])
    if "*" not in perms and "clinical:read" not in perms:
        raise HTTPException(status_code=403, detail="role lacks permission 'clinical:read'")
    res = _run(registry.graph_explorer.case_graph, patient_id, store)
    store.audit(user["username"], "kg.case_graph", patient_id, f"nodes={len(res['nodes'])}")
    return res
