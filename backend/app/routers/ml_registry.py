"""Phase 19 read-only model registry API. Serves files written by `python -m scripts.ml_benchmark`; never computes or invents metrics.

  GET /api/v1/ml/registry     model list, status, default flags, measured metrics
  GET /api/v1/ml/benchmark    full benchmark with caveats
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends

from backend.app.security import require

router = APIRouter(prefix="/api/v1/ml", tags=["ml"])
Auth = Depends(require("analytics:read"))
MODELS_DIR = Path(__file__).resolve().parents[3] / "models"


def _load(name: str) -> dict:
    p = MODELS_DIR / name
    if not p.exists():
        return {"available": False, "reason": "Not generated - run `python -m scripts.ml_benchmark`."}
    try:
        return {"available": True, **json.loads(p.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return {"available": False, "reason": "File unreadable."}


@router.get("/registry")
def registry(user: dict = Auth):
    return _load("registry.json")


@router.get("/benchmark")
def benchmark(user: dict = Auth):
    return _load("benchmark.json")
