"""Genomera Clinical NLP API (Phase 5), a structuring layer over the existing NER and HPO mapper.

  GET  /api/v1/nlp/capabilities  supported / unsupported entity labels
  POST /api/v1/nlp/analyze       full analysis: entities, assertion, experiencer, onset, severity, normalisation, summary
  POST /api/v1/nlp/entities      entities only (no summary)
  POST /api/v1/nlp/normalize     map phrases to HPO with candidate lists (existing HPOMapper)
Nothing is written to a case; confirmed findings are imported through the Phenotype workspace.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.app import store
from backend.app.security import require
from backend.app.services import registry
from ml_services.nlp.clinical_text import MAX_TEXT, SUPPORTED_LABELS, UNSUPPORTED_LABELS

router = APIRouter(prefix="/api/v1/nlp", tags=["nlp"])
_RATE = defaultdict(deque)
RATE_LIMIT = 60


def _limit(user: dict) -> None:
    q, now = _RATE[user["username"]], time.monotonic()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many NLP requests; wait a minute and retry")
    q.append(now)


class TextIn(BaseModel):
    text: str = Field(..., max_length=MAX_TEXT)
    patient_id: Optional[str] = None


class NormalizeIn(BaseModel):
    phrases: List[str] = Field(..., min_length=1, max_length=50)
    top_k: int = Field(default=3, ge=1, le=10)


def _check(body: TextIn) -> str:
    text = body.text.replace("\x00", "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Text is empty")
    if body.patient_id and not store.get_patient(body.patient_id):
        raise HTTPException(status_code=404, detail="Case not found")
    return text


@router.get("/capabilities")
def capabilities(user: dict = Depends(require("clinical:write"))):
    return {"supported_labels": SUPPORTED_LABELS, "unsupported_labels": UNSUPPORTED_LABELS, "max_chars": MAX_TEXT,
            "ner_backend": type(registry.ner).__name__, "assertion": "rule-based (negation, uncertainty, history, family)"}


@router.post("/analyze")
def analyze(body: TextIn, user: dict = Depends(require("clinical:write"))):
    _limit(user)
    text = _check(body)
    result = registry.clinical_text.analyze(text)
    store.audit(user["username"], "nlp.analyze", body.patient_id or "", f"{len(text)} chars, {len(result['entities'])} entities")
    return result


@router.post("/entities")
def entities(body: TextIn, user: dict = Depends(require("clinical:write"))):
    _limit(user)
    text = _check(body)
    result = registry.clinical_text.analyze(text)
    store.audit(user["username"], "nlp.entities", body.patient_id or "", f"{len(result['entities'])} entities")
    return {"entities": result["entities"], "counts": result["counts"]}


@router.post("/normalize")
def normalize(body: NormalizeIn, user: dict = Depends(require("clinical:write"))):
    _limit(user)
    out = []
    for ph in body.phrases:
        ph = ph.strip()[:200]
        if not ph:
            continue
        ranked = registry.hpo_mapper.map_phrase(ph, top_k=body.top_k)
        top = ranked[0]["score"] if ranked else 0
        out.append({"phrase": ph,
                    "candidates": [{"hpo_id": r["hpo_id"], "name": r.get("hpo_name"), "score": round(float(r["score"]), 3),
                                    "source": r.get("source")} for r in ranked],
                    "status": "mapped" if top >= 0.6 else ("needs_review" if top >= 0.35 else "unmapped")})
    store.audit(user["username"], "nlp.normalize", "", f"{len(out)} phrases")
    return {"results": out}
