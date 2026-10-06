"""Assistant Service Orchestrator for Genomera (Phase 3C).

Binds:
- Intent detection
- Clinical Context retrieval across live Diagnosis, Variants, HPO, and Knowledge Graph
- Guardrails and prompt injection defenses
- Multilingual and Patient-Friendly formatting
- LLM inference client
- Session state and conversation persistence
- Server-Sent Events (SSE) streaming formatting
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict
from typing import Any, Dict, Generator, List, Optional

from ml_services.assistant.context_retriever import ContextRetriever, RetrievedContext
from ml_services.assistant.guardrails import check_prompt_injection, format_assistant_prompt
from ml_services.assistant.intent_classifier import detect_intent
from ml_services.assistant.llm_client import LLMClient


class AssistantService:
    """Core orchestration engine for Genomera AI Assistant."""

    def __init__(self, services_registry: Any, llm_client: Optional[LLMClient] = None):
        self.registry = services_registry
        self.retriever = ContextRetriever(services_registry)
        self.llm = llm_client or LLMClient()
        # In-memory conversation stores keyed by conversation_id
        # Structure: {conversation_id: {"user": str, "messages": List[dict], "context": dict, "created_at": float}}
        self._conversations: Dict[str, dict] = {}

    @staticmethod
    def _merge_extra_context(retrieved: RetrievedContext, extra: Optional[dict]) -> None:
        """Append caller-supplied grounding (e.g. the Digital Twin) to the retrieved context."""
        if not extra:
            return
        from ml_services.assistant.context_retriever import Citation

        retrieved.retrieved_data_text = (retrieved.retrieved_data_text + "\n\n" + extra["text"]).strip()
        retrieved.citations.extend(Citation(**c) for c in extra.get("citations", []))
        retrieved.context_summary.update(extra.get("summary", {}))
        retrieved.context_summary["citations_count"] = len(retrieved.citations)
        retrieved.has_sufficient_context = True

    @staticmethod
    def _finalise(text: str, retrieved: RetrievedContext, citations_list: List[dict]):
        """Output guardrail: drop specifics that are not in the context, and state plainly when requested literature was not retrieved."""
        from ml_services.assistant.orchestrator import verify_answer
        context = retrieved.patient_context_text + chr(10) + retrieved.retrieved_data_text
        cleaned, flags = verify_answer(text, context, [c.get("identifier", "") for c in citations_list])
        lit = (retrieved.context_summary or {}).get("literature")
        if lit and lit != "retrieved":
            cleaned += chr(10) * 2 + "No supporting evidence was retrieved."
        return cleaned, [f for f in flags if f["type"] != "provider_reference"] + [f for f in flags if f["type"] == "provider_reference"]

    def get_or_create_conversation(self, conversation_id: Optional[str], username: str) -> str:
        if conversation_id and conversation_id in self._conversations:
            conv = self._conversations[conversation_id]
            if conv.get("user") == username or username == "admin":
                return conversation_id

        new_id = f"CONV-{uuid.uuid4().hex[:10].upper()}"
        self._conversations[new_id] = {
            "conversation_id": new_id,
            "user": username,
            "messages": [],
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        return new_id

    def get_conversation_history(self, conversation_id: str, username: str) -> Optional[dict]:
        conv = self._conversations.get(conversation_id)
        if not conv:
            return None
        if conv["user"] != username and username != "admin":
            return None
        return conv

    def clear_conversation(self, conversation_id: str, username: str) -> bool:
        conv = self._conversations.get(conversation_id)
        if conv and (conv["user"] == username or username == "admin"):
            conv["messages"] = []
            conv["updated_at"] = time.time()
            return True
        return False

    def chat_stream(
        self,
        query: str,
        conversation_id: str,
        username: str,
        patient_id: Optional[str] = None,
        analysis_id: Optional[str] = None,
        selected_variant_id: Optional[str] = None,
        active_hpo_ids: Optional[List[str]] = None,
        mode: str = "clinical",
        language: str = "en",
        extra_context: Optional[dict] = None,
    ) -> Generator[str, None, None]:
        """Server-Sent Events generator streaming JSON payloads to frontend."""
        # 1. Guardrails check
        injection_warning = check_prompt_injection(query)
        if injection_warning:
            conv = self._conversations.get(conversation_id)
            if conv:
                conv["messages"].append({"role": "user", "content": query, "timestamp": time.time()})
                conv["messages"].append({
                    "role": "assistant",
                    "content": injection_warning,
                    "timestamp": time.time(),
                    "citations": [],
                })
            
            yield f"data: {json.dumps({'type': 'content', 'delta': injection_warning})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'citations': []})}\n\n"
            return

        # 2. Retrieve targeted clinical context
        retrieved: RetrievedContext = self.retriever.retrieve(
            query=query,
            patient_id=patient_id,
            analysis_id=analysis_id,
            selected_variant_id=selected_variant_id,
            active_hpo_ids=active_hpo_ids,
            language=language,
            mode=mode,
        )
        self._merge_extra_context(retrieved, extra_context)

        # 3. Format citations for payload
        citations_list = [asdict(c) for c in retrieved.citations]
        yield f"data: {json.dumps({'type': 'citations', 'citations': citations_list, 'context_summary': retrieved.context_summary})}\n\n"

        # 4. Fetch session history
        conv = self._conversations.get(conversation_id)
        history_msgs = conv["messages"] if conv else []

        # 5. Format system and user prompt with injection boundaries
        messages = format_assistant_prompt(
            user_query=query,
            patient_context_text=retrieved.patient_context_text,
            retrieved_data_text=retrieved.retrieved_data_text,
            conversation_history=history_msgs,
            mode=mode,
            language=language,
        )

        # 6. Stream tokens from LLM client
        full_response_text = []
        for token in self.llm.stream_generate(messages):
            full_response_text.append(token)
            yield f"data: {json.dumps({'type': 'content', 'delta': token})}\n\n"

        # 7. Persist interaction in conversation history (after the output guardrail; the client replaces the streamed text if corrected)
        assembled_content = "".join(full_response_text)
        corrected, verification = self._finalise(assembled_content, retrieved, citations_list)
        if corrected != assembled_content:
            assembled_content = corrected
            yield f"data: {json.dumps({'type': 'correction', 'content': corrected, 'flags': verification})}\n\n"
        if conv:
            conv["messages"].append({
                "role": "user",
                "content": query,
                "timestamp": time.time(),
            })
            conv["messages"].append({
                "role": "assistant",
                "content": assembled_content,
                "timestamp": time.time(),
                "citations": citations_list,
                "intent": retrieved.intent,
            })
            conv["updated_at"] = time.time()

        yield f"data: {json.dumps({'type': 'done', 'citations': citations_list})}\n\n"

    def chat_sync(
        self,
        query: str,
        conversation_id: str,
        username: str,
        patient_id: Optional[str] = None,
        analysis_id: Optional[str] = None,
        selected_variant_id: Optional[str] = None,
        active_hpo_ids: Optional[List[str]] = None,
        mode: str = "clinical",
        language: str = "en",
        extra_context: Optional[dict] = None,
    ) -> dict:
        """Synchronous chat endpoint for non-streaming clients or automated tests."""
        injection_warning = check_prompt_injection(query)
        if injection_warning:
            return {
                "conversation_id": conversation_id,
                "response": injection_warning,
                "citations": [],
                "intent": "INJECTION_ATTEMPT",
            }

        retrieved: RetrievedContext = self.retriever.retrieve(
            query=query,
            patient_id=patient_id,
            analysis_id=analysis_id,
            selected_variant_id=selected_variant_id,
            active_hpo_ids=active_hpo_ids,
            language=language,
            mode=mode,
        )
        self._merge_extra_context(retrieved, extra_context)

        conv = self._conversations.get(conversation_id)
        history_msgs = conv["messages"] if conv else []

        messages = format_assistant_prompt(
            user_query=query,
            patient_context_text=retrieved.patient_context_text,
            retrieved_data_text=retrieved.retrieved_data_text,
            conversation_history=history_msgs,
            mode=mode,
            language=language,
        )

        response_text = self.llm.generate(messages)
        citations_list = [asdict(c) for c in retrieved.citations]
        response_text, verification = self._finalise(response_text, retrieved, citations_list)

        if conv:
            conv["messages"].append({"role": "user", "content": query, "timestamp": time.time()})
            conv["messages"].append({
                "role": "assistant",
                "content": response_text,
                "timestamp": time.time(),
                "citations": citations_list,
                "intent": retrieved.intent,
            })
            conv["updated_at"] = time.time()

        return {
            "conversation_id": conversation_id,
            "response": response_text,
            "citations": citations_list,
            "intent": retrieved.intent,
            "context_summary": retrieved.context_summary,
            "verification": verification,
        }
