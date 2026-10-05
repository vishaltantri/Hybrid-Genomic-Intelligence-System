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
from backend.app.security import ROLE_PERMISSIONS, current_user, require
from backend.app.services import registry
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


class ChatResponseOut(BaseModel):
    conversation_id: str
    response: str
    citations: List[Dict[str, Any]]
    intent: str
    context_summary: Optional[Dict[str, Any]] = None


@router.post("/chat", response_model=ChatResponseOut)
def chat_sync(payload: ChatMessageIn, user: dict = Depends(require("assistant:chat"))):
    """Synchronous chat endpoint with complete evidence citations and grounding."""
    username = user.get("username", "clinician")
    twin_ctx = _twin_context(payload, user)
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
def chat_stream(payload: ChatMessageIn, user: dict = Depends(require("assistant:chat"))):
    """Server-Sent Events streaming chat endpoint."""
    username = user.get("username", "clinician")
    twin_ctx = _twin_context(payload, user)
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
