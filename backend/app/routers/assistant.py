"""Genomera AI Assistant API Router (Phase 3C).

Endpoints:
- POST /api/v1/assistant/chat: Synchronous chat response with citations and context summary.
- POST /api/v1/assistant/chat/stream: Server-Sent Events (SSE) streaming chat response.
- GET  /api/v1/assistant/conversations/{conversation_id}: Retrieve conversation history.
- DELETE /api/v1/assistant/conversations/{conversation_id}: Clear conversation history.
- GET  /api/v1/assistant/context: Pre-flight context inspection for current case/patient.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.app import store
from backend.app.hardening import analysis_visible, has_perm, rate_limit
from backend.app.security import ROLE_PERMISSIONS, current_user, require
from backend.app.services import registry
from ml_services.assistant.context_retriever import NO_VISIBLE_ANALYSIS
from ml_services.pedigree.service import PedigreeNotFound
from ml_services.twin.twin_service import TwinNotFound

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])


def _twin_context(payload: "ChatMessageIn", user: dict) -> Optional[dict]:
    """Twin grounding for the assistant. Requires the same permission as the Twin API itself."""
    if not (payload.include_twin or payload.twin_scenario_id):
        return None
    if not payload.patient_id:
        raise HTTPException(status_code=422, detail="Select a patient to use Digital Twin context")
    perms = ROLE_PERMISSIONS.get(user["role"], [])
    if "*" not in perms and "twin:read" not in perms:
        raise HTTPException(status_code=403, detail=f"role {user['role']!r} lacks permission 'twin:read'")
    try:
        return registry.twin.assistant_context(payload.patient_id, user["username"], payload.twin_scenario_id,
                                               payload.analysis_id)
    except TwinNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _pedigree_context(payload: "ChatMessageIn", user: dict) -> Optional[dict]:
    """Pedigree grounding (members, genotypes, computed inheritance/segregation). Needs `pedigree:read`."""
    if not (payload.include_pedigree or payload.pedigree_variant_key):
        return None
    if not payload.patient_id:
        raise HTTPException(status_code=422, detail="Select a case to use pedigree context")
    perms = ROLE_PERMISSIONS.get(user["role"], [])
    if "*" not in perms and "pedigree:read" not in perms:
        raise HTTPException(status_code=403, detail=f"role {user['role']!r} lacks permission 'pedigree:read'")
    try:
        return registry.pedigree.ai_context(payload.patient_id, payload.pedigree_variant_key)
    except PedigreeNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _evidence_context(payload: "ChatMessageIn", user: dict) -> Optional[dict]:
    """Real PubMed retrieval (never invented). Needs `evidence:read`; unavailable/empty results are stated to the model."""
    if not payload.include_evidence:
        return None
    perms = ROLE_PERMISSIONS.get(user["role"], [])
    if "*" not in perms and "evidence:read" not in perms:
        raise HTTPException(status_code=403, detail=f"role {user['role']!r} lacks permission 'evidence:read'")
    query = (payload.evidence_query or payload.message).strip()[:200]
    return registry.evidence.ai_context(query, gene=payload.evidence_gene, analysis_id=payload.analysis_id)


def _graph_context(payload: "ChatMessageIn", user: dict) -> Optional[dict]:
    """Neighbourhood of one selected knowledge-graph node, read server-side."""
    if not payload.graph_node:
        return None
    perms = ROLE_PERMISSIONS.get(user["role"], [])
    if "*" not in perms and "kg:read" not in perms:
        raise HTTPException(status_code=403, detail=f"role {user['role']!r} lacks permission 'kg:read'")
    try:
        return registry.graph_explorer.ai_context(payload.graph_node)
    except (ValueError, LookupError) as ex:
        raise HTTPException(status_code=422, detail=str(ex))


def _dx_context(payload: "ChatMessageIn", user: dict) -> Optional[dict]:
    """Diagnosis Intelligence workspace for one case (differential, supporting / missing findings, evidence quality)."""
    if not payload.include_diagnosis_intel or not payload.patient_id:
        return None
    perms = ROLE_PERMISSIONS.get(user["role"], [])
    if "*" not in perms and "diagnosis:run" not in perms:
        raise HTTPException(status_code=403, detail=f"role {user['role']!r} lacks permission 'diagnosis:run'")
    try:
        ctx = registry.diagnosis_intel.ai_context(payload.patient_id)
    except LookupError as ex:
        raise HTTPException(status_code=404, detail=str(ex))
    return {**ctx, "summary": {"diagnosis_intel": True}}


def _repro_context(payload: "ChatMessageIn", user: dict) -> Optional[dict]:
    """Case reproductive-genetics workspace (calculated probabilities only)."""
    if not payload.include_repro or not payload.patient_id:
        return None
    perms = ROLE_PERMISSIONS.get(user["role"], [])
    if "*" not in perms and "reproductive:read" not in perms:
        raise HTTPException(status_code=403, detail=f"role {user['role']!r} lacks permission 'reproductive:read'")
    try:
        return registry.repro.ai_context(payload.patient_id)
    except LookupError as ex:
        raise HTTPException(status_code=404, detail=str(ex))
    except ValueError as ex:
        return {"text": f"REPRODUCTIVE GENETICS CONTEXT: not available ({ex})", "citations": [], "summary": {"reproductive": False}}


def _pgx_context(payload: "ChatMessageIn", user: dict) -> Optional[dict]:
    """Case PGx workspace (genotype, phenotype, configured drug rules)."""
    if not payload.include_pgx or not payload.patient_id:
        return None
    perms = ROLE_PERMISSIONS.get(user["role"], [])
    if "*" not in perms and "pgx:read" not in perms:
        raise HTTPException(status_code=403, detail=f"role {user['role']!r} lacks permission 'pgx:read'")
    try:
        return registry.case_pgx.ai_context(payload.patient_id)
    except LookupError as ex:
        raise HTTPException(status_code=404, detail=str(ex))


def _nlp_context(payload: "ChatMessageIn", user: dict) -> Optional[dict]:
    """Structured reading of clinician-supplied free text (present / absent / possible / family), computed server-side."""
    if not payload.clinical_text:
        return None
    perms = ROLE_PERMISSIONS.get(user["role"], [])
    if "*" not in perms and "clinical:write" not in perms:
        raise HTTPException(status_code=403, detail=f"role {user['role']!r} lacks permission 'clinical:write'")
    return registry.clinical_text.ai_context(payload.clinical_text)


def _extra_context(payload: "ChatMessageIn", user: dict) -> Optional[dict]:
    """Merge Digital Twin, pedigree and literature grounding (any combination)."""
    parts = [c for c in (_twin_context(payload, user), _pedigree_context(payload, user), _evidence_context(payload, user), _nlp_context(payload, user), _graph_context(payload, user), _dx_context(payload, user), _pgx_context(payload, user), _repro_context(payload, user)) if c]
    if not parts:
        return None
    return {"text": "\n\n".join(c["text"] for c in parts),
            "citations": [x for c in parts for x in c["citations"]],
            "summary": {k: v for c in parts for k, v in c["summary"].items()}}




def _scope(patient_id: Optional[str], analysis_id: Optional[str], user: dict) -> Optional[str]:
    """Enforce object-level access for assistant grounding; returns the analysis id the retriever may use."""
    if patient_id and not has_perm(user, "clinical:read"):
        raise HTTPException(status_code=403, detail=f"role {user['role']!r} lacks permission 'clinical:read'")
    if analysis_id:
        a = registry.variants.get_analysis(analysis_id)
        if a and not analysis_visible(user, a):
            raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found")
        return analysis_id
    all_analyses = registry.variants.list_analyses()
    if not all_analyses:
        return None                      # nothing exists anywhere: retriever's demo-trio behaviour is unchanged
    mine = [a for a in all_analyses if analysis_visible(user, a)]
    return mine[0]["analysis_id"] if mine else NO_VISIBLE_ANALYSIS


class ChatMessageIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: Optional[str] = None
    patient_id: Optional[str] = None
    analysis_id: Optional[str] = None
    selected_variant_id: Optional[str] = None
    active_hpo_ids: Optional[List[str]] = Field(default_factory=list)
    mode: str = Field(default="clinical", description="'clinical' or 'patient_friendly'")
    language: str = Field(default="en", description="'en' or 'hi'")
    include_twin: bool = Field(default=False, description="Ground the answer in the patient's Digital Twin")
    twin_scenario_id: Optional[str] = Field(default=None, description="Also ground in this Twin scenario result")
    include_pedigree: bool = Field(default=False, description="Ground the answer in the case's pedigree analysis")
    clinical_text: Optional[str] = Field(default=None, max_length=8000, description="Free text to analyse with the clinical NLP layer")
    graph_node: Optional[str] = Field(default=None, max_length=200, description="Knowledge-graph node key (Type::id) to ground the answer on")
    include_repro: bool = Field(default=False, description="Ground the answer in the case reproductive workspace")
    include_pgx: bool = Field(default=False, description="Ground the answer in the case PGx workspace")
    include_diagnosis_intel: bool = Field(default=False, description="Ground the answer in the Diagnosis Intelligence workspace for patient_id")
    include_evidence: bool = Field(default=False, description="Retrieve real PubMed literature before answering")
    evidence_query: Optional[str] = Field(default=None, max_length=200, description="Literature query (defaults to the message)")
    evidence_gene: Optional[str] = Field(default=None, max_length=20)
    pedigree_variant_key: Optional[str] = Field(default=None, description="Variant (e.g. chr13:51943246:C>G) to analyse in the family")


class ChatResponseOut(BaseModel):
    conversation_id: str
    response: str
    citations: List[Dict[str, Any]]
    intent: str
    context_summary: Optional[Dict[str, Any]] = None


@router.post("/chat", response_model=ChatResponseOut)
def chat_sync(payload: ChatMessageIn, user: dict = Depends(require("assistant:chat")), _rl: None = Depends(rate_limit("ai"))):
    """Synchronous chat endpoint with complete evidence citations and grounding."""
    username = user.get("username", "clinician")
    payload.analysis_id = _scope(payload.patient_id, payload.analysis_id, user)
    twin_ctx = _extra_context(payload, user)
    conv_id = registry.assistant.get_or_create_conversation(payload.conversation_id, username)

    result = registry.assistant.chat_sync(
        query=payload.message,
        conversation_id=conv_id,
        username=username,
        patient_id=payload.patient_id,
        analysis_id=payload.analysis_id,
        selected_variant_id=payload.selected_variant_id,
        active_hpo_ids=payload.active_hpo_ids,
        mode=payload.mode,
        language=payload.language,
        extra_context=twin_ctx,
    )

    store.audit(username, "assistant.chat", payload.patient_id or "", f"intent={result.get('intent')}")
    return ChatResponseOut(**result)


@router.post("/chat/stream")
def chat_stream(payload: ChatMessageIn, user: dict = Depends(require("assistant:chat")), _rl: None = Depends(rate_limit("ai"))):
    """Server-Sent Events streaming chat endpoint."""
    username = user.get("username", "clinician")
    payload.analysis_id = _scope(payload.patient_id, payload.analysis_id, user)
    twin_ctx = _extra_context(payload, user)
    conv_id = registry.assistant.get_or_create_conversation(payload.conversation_id, username)

    generator = registry.assistant.chat_stream(
        query=payload.message,
        conversation_id=conv_id,
        username=username,
        patient_id=payload.patient_id,
        analysis_id=payload.analysis_id,
        selected_variant_id=payload.selected_variant_id,
        active_hpo_ids=payload.active_hpo_ids,
        mode=payload.mode,
        language=payload.language,
        extra_context=twin_ctx,
    )

    store.audit(username, "assistant.chat_stream", payload.patient_id or "", f"mode={payload.mode}")

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, user: dict = Depends(require("assistant:chat"))):
    """Fetch persistent conversation messages."""
    username = user.get("username", "clinician")
    conv = registry.assistant.get_conversation_history(conversation_id, username)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found or access denied")
    return conv


@router.delete("/conversations/{conversation_id}")
def clear_conversation(conversation_id: str, user: dict = Depends(require("assistant:chat"))):
    """Clear conversation history."""
    username = user.get("username", "clinician")
    ok = registry.assistant.clear_conversation(conversation_id, username)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found or access denied")
    return {"status": "cleared", "conversation_id": conversation_id}


@router.get("/context")
def inspect_context(
    patient_id: Optional[str] = Query(default=None),
    analysis_id: Optional[str] = Query(default=None),
    user: dict = Depends(require("assistant:chat")),
):
    """Pre-flight check of available clinical context for user interface indicators."""
    analysis_id = _scope(patient_id, analysis_id, user)
    retrieved = registry.assistant.retriever.retrieve(
        query="Case context summary inspection",
        patient_id=patient_id,
        analysis_id=analysis_id,
    )
    return {
        "context_summary": retrieved.context_summary,
        "citations_available": len(retrieved.citations),
        "has_sufficient_context": retrieved.has_sufficient_context,
    }
