"""Phase 24 demo mode API. Normal authentication and permissions apply; there is no demo login and no bypass.

  GET  /api/v1/demo/status   banner, notice, and per-step real state of the caller's synthetic case
  POST /api/v1/demo/seed     build the synthetic case with the real services (idempotent)
  POST /api/v1/demo/reset    remove only the caller's demo cases (admin: all demo cases)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.app import demo
from backend.app.security import require
from backend.app.services import registry

router = APIRouter(prefix="/api/v1/demo", tags=["demo"])
Auth = Depends(require("demo:manage"))


def _run(fn, user):
    try:
        return fn(registry, user)
    except demo.DemoError as ex:
        raise HTTPException(status_code=ex.status, detail=str(ex))


@router.get("/status")
def get_status(user: dict = Auth):
    return _run(demo.status, user)


@router.post("/seed")
def seed(user: dict = Auth):
    return _run(demo.seed, user)


@router.post("/reset")
def reset(user: dict = Auth):
    return _run(demo.reset, user)
