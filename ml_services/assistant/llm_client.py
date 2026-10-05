"""Internal AI Provider Client for Genomera Assistant (Phase 3C).

Calls the internal configured cloud inference endpoint via HTTPX.
NEVER leaks provider headers, provider names, or API keys to responses or frontends.
Provides synchronous and streaming completion generators.
"""
from __future__ import annotations

import json
from typing import AsyncGenerator, Dict, Generator, List, Optional

import httpx

from ml_services.config import GROQ_API_KEY, GROQ_MODEL

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"


FALLBACK_MODELS = [
    GROQ_MODEL,
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
]


class LLMClient:
    """Internal client communicating with the configured LLM backend."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or GROQ_API_KEY
        self.model = model or GROQ_MODEL

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and len(self.api_key.strip()) > 10)

    def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        """Non-streaming text generation with automatic model fallback."""
        if not self.is_configured:
            return (
                "The internal AI service is currently in offline baseline mode. "
                "Clinical context and evidence retrieval remain fully functional."
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Try models in order (primary -> fallbacks)
        models_to_try = [self.model] + [m for m in FALLBACK_MODELS if m != self.model]

        for mod in models_to_try:
            payload = {
                "model": mod,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            }
            try:
                with httpx.Client(timeout=25.0) as client:
                    res = client.post(GROQ_ENDPOINT, headers=headers, json=payload)
                    if res.status_code == 200:
                        data = res.json()
                        choice = data.get("choices", [{}])[0]
                        message = choice.get("message", {})
                        content = message.get("content") or ""
                        if not content and "reasoning" in message:
                            content = message.get("reasoning") or ""
                        if content:
                            return content.strip()
                    elif res.status_code in (500, 502, 503, 504, 404, 429):
                        continue
            except Exception:
                continue

        return (
            "Genomera AI Assistant is temporarily experiencing high cloud inference demand. "
            "Your clinical case context and evidence citations are preserved. Please retry your inquiry in a moment."
        )

    def stream_generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> Generator[str, None, None]:
        """Streaming text generation with automatic model fallback."""
        if not self.is_configured:
            yield "The Genomera AI Assistant is currently running without an active inference key. Verified case context and citations are presented."
            return

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        models_to_try = [self.model] + [m for m in FALLBACK_MODELS if m != self.model]

        for mod in models_to_try:
            payload = {
                "model": mod,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            }
            try:
                with httpx.Client(timeout=35.0) as client:
                    with client.stream("POST", GROQ_ENDPOINT, headers=headers, json=payload) as response:
                        if response.status_code == 200:
                            emitted_any = False
                            for line in response.iter_lines():
                                if not line:
                                    continue
                                if line.startswith("data: "):
                                    data_str = line[6:].strip()
                                    if data_str == "[DONE]":
                                        break
                                    try:
                                        chunk = json.loads(data_str)
                                        choices = chunk.get("choices", [])
                                        if choices:
                                            delta = choices[0].get("delta", {})
                                            token = delta.get("content")
                                            if token:
                                                emitted_any = True
                                                yield token
                                    except Exception:
                                        continue
                            if emitted_any:
                                return
                        elif response.status_code in (500, 502, 503, 504, 404, 429):
                            continue
            except Exception:
                continue

        yield "The assistant is temporarily experiencing high inference demand. Your verified clinical evidence citations remain active."

